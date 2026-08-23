# Copyright (c) 2026, ALYF GmbH and contributors
# For license information, please see license.txt

"""The tax audit data package, filled with this company's books.

Every table declared here is written twice: once as data and once into the
index that describes it. Both come from the same declaration, so the package
cannot describe itself wrongly.

Two things a Betriebspruefer looks for first are answered per booking rather
than as a separate document: who entered it, and when it became unchangeable.
The first is the document's own author. The second is derived from the
lockdown covering the posting date -- which is the honest answer, because
that is the moment the entry actually stopped being changeable.
"""

import io
import zipfile
from datetime import date

import frappe
from frappe import _
from frappe.utils import flt, getdate

from erpnext_germany.bookkeeping.account_sheet import contra_accounts
from erpnext_germany.bookkeeping.gobd import (
	ALPHANUMERIC,
	DATE,
	NUMERIC,
	Column,
	Table,
	build_index,
	to_csv,
)

INDEX_FILE = "index.xml"

# A fixed timestamp for every entry in the archive. Without it two exports of
# the same books would differ in their bytes, and "repeatable with an
# identical result" is an acceptance criterion, not a nicety.
ARCHIVE_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def get_tables() -> list[Table]:
	"""What the package contains, in the order it is meant to be read."""
	return [
		Table(
			"buchungsjournal",
			"Buchungsjournal",
			(
				Column("voucher_no", "Belegnummer"),
				Column("voucher_type", "Belegart"),
				Column("posting_date", "Buchungsdatum", DATE),
				Column("document_number", "Belegfeld 1"),
				Column("document_number_2", "Belegfeld 2"),
				Column("account_number", "Konto"),
				Column("account", "Kontobezeichnung"),
				Column("against", "Gegenkonto"),
				Column("debit", "Soll", NUMERIC),
				Column("credit", "Haben", NUMERIC),
				Column("remarks", "Buchungstext"),
				Column("party_type", "Personenkontoart"),
				Column("party", "Personenkonto"),
				Column("cost_center", "Kostenstelle"),
				Column("entered_by", "Erfasser"),
				Column("entered_on", "Erfassungsdatum", DATE),
				Column("locked_on", "Festschreibedatum", DATE),
				Column("locked_by", "Festgeschrieben von"),
				Column("reversal_of", "Generalumkehr zu"),
			),
		),
		Table(
			"konten",
			"Kontenbeschriftungen",
			(
				Column("account_number", "Konto"),
				Column("account_name", "Bezeichnung"),
				Column("account_label", "Hausbezeichnung"),
				Column("root_type", "Kontenklasse"),
				Column("account_type", "Kontoart"),
				Column("tax_key", "Steuerschluessel"),
				Column("disabled", "Gesperrt"),
			),
		),
		Table(
			"debitoren",
			"Debitoren",
			(
				Column("party", "Konto"),
				Column("name_1", "Name"),
				Column("tax_id", "Steuernummer"),
				Column("vat_id", "USt-IdNr"),
				Column("disabled", "Gesperrt"),
			),
		),
		Table(
			"kreditoren",
			"Kreditoren",
			(
				Column("party", "Konto"),
				Column("name_1", "Name"),
				Column("tax_id", "Steuernummer"),
				Column("vat_id", "USt-IdNr"),
				Column("disabled", "Gesperrt"),
			),
		),
		Table(
			"anlagenverzeichnis",
			"Anlagenverzeichnis",
			(
				Column("asset", "Anlage"),
				Column("asset_name", "Bezeichnung"),
				Column("purchase_date", "Anschaffungsdatum", DATE),
				Column("gross_purchase_amount", "Anschaffungswert", NUMERIC),
				Column("available_for_use_date", "Nutzung ab", DATE),
				Column("status", "Status"),
			),
		),
		Table(
			"belegverknuepfungen",
			"Belegverknuepfungen",
			(
				Column("voucher_type", "Belegart"),
				Column("voucher_no", "Belegnummer"),
				Column("file_name", "Dateiname"),
				Column("file_id", "Belegkennung"),
			),
		),
		Table(
			"festschreibungen",
			"Festschreibungsprotokoll",
			(
				Column("lockdown", "Festschreibung"),
				Column("locked_up_to", "Festgeschrieben bis", DATE),
				Column("locked_on", "Festgeschrieben am", DATE),
				Column("locked_by", "Festgeschrieben von"),
			),
		),
		Table(
			"aenderungshistorie",
			"Aenderungshistorie",
			(
				Column("voucher_type", "Belegart"),
				Column("voucher_no", "Belegnummer"),
				Column("changed_on", "Geaendert am", DATE),
				Column("changed_by", "Geaendert von"),
				Column("change", "Aenderung", ALPHANUMERIC),
			),
		),
	]


@frappe.whitelist()
def export(company: str, fiscal_year: str) -> str:
	"""Build the package and file it with the company.

	Filed rather than handed straight to the browser, so that what was given
	to an auditor can be shown again later. Repeating the export produces the
	same bytes, so a second copy is provably the same package.
	"""
	frappe.only_for(("Accounts Manager", "Auditor", "System Manager"))

	from_date, to_date = fiscal_year_range(fiscal_year)
	archive = build_package(company, fiscal_year, from_date, to_date)

	file = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"GoBD {company} {fiscal_year}.zip",
			"attached_to_doctype": "Company",
			"attached_to_name": company,
			"content": archive,
			"decode": False,
			"is_private": 1,
		}
	).insert()

	return file.file_url


def build_package(company: str, fiscal_year: str, from_date: date, to_date: date) -> bytes:
	"""Every table plus the index, as one archive."""
	tables = get_tables()
	rows = collect(company, from_date, to_date)

	buffer = io.BytesIO()
	with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
		description = _("Fiscal year {0}, {1} to {2}").format(fiscal_year, from_date, to_date)
		write(archive, INDEX_FILE, build_index(company, description, tables))
		for table in tables:
			write(archive, table.file_name, to_csv(table, rows[table.name]))

	return buffer.getvalue()


def write(archive: zipfile.ZipFile, name: str, content: str):
	"""One entry, stamped with a fixed date so two exports match byte for byte."""
	info = zipfile.ZipInfo(name, date_time=ARCHIVE_TIMESTAMP)
	info.compress_type = zipfile.ZIP_DEFLATED
	archive.writestr(info, content.encode("utf-8"))


def collect(company: str, from_date: date, to_date: date) -> dict[str, list[dict]]:
	journal = get_journal(company, from_date, to_date)
	vouchers = {(row["voucher_type"], row["voucher_no"]) for row in journal}

	return {
		"buchungsjournal": journal,
		"konten": get_accounts(company),
		"debitoren": get_parties("Customer"),
		"kreditoren": get_parties("Supplier"),
		"anlagenverzeichnis": get_assets(company, to_date),
		"belegverknuepfungen": get_attachments(vouchers),
		"festschreibungen": get_lockdowns(company),
		"aenderungshistorie": get_changes(vouchers),
	}


# --- the tables -------------------------------------------------------------


def get_journal(company: str, from_date: date, to_date: date) -> list[dict]:
	"""Every ledger entry of the year, with who entered it and when it was locked.

	Cancelled entries are in it. An audit package that quietly leaves out what
	was taken back is worth less than none: the taking back is exactly what a
	Betriebspruefer wants to see.
	"""
	entries = frappe.get_all(
		"GL Entry",
		filters={"company": company, "posting_date": ("between", [from_date, to_date])},
		fields=[
			"name",
			"posting_date",
			"account",
			"against",
			"debit_in_account_currency as debit",
			"credit_in_account_currency as credit",
			"remarks",
			"party_type",
			"party",
			"cost_center",
			"voucher_type",
			"voucher_no",
			"owner",
			"creation",
			"is_cancelled",
		],
		order_by="posting_date asc, creation asc, name asc",
	)

	accounts = {
		row.name: row
		for row in frappe.get_all(
			"Account", filters={"company": company}, fields=["name", "account_number", "account_name"]
		)
	}
	lockdowns = get_lockdown_dates(company)
	documents = get_document_numbers(entries)

	rows = []
	for entry in entries:
		account = accounts.get(entry.account) or frappe._dict()
		locked_on, locked_by = lockdown_for(lockdowns, entry.posting_date)
		document = documents.get(entry.voucher_no) or frappe._dict()
		rows.append(
			{
				"voucher_no": entry.voucher_no,
				"voucher_type": entry.voucher_type,
				"posting_date": entry.posting_date,
				"document_number": document.get("bill_no"),
				"document_number_2": document.get("cheque_no"),
				"account_number": account.get("account_number"),
				"account": account.get("account_name") or entry.account,
				"against": contra_accounts(entry.against),
				"debit": flt(entry.debit),
				"credit": flt(entry.credit),
				"remarks": entry.remarks,
				"party_type": entry.party_type,
				"party": entry.party,
				"cost_center": entry.cost_center,
				"entered_by": entry.owner,
				"entered_on": entry.creation,
				"locked_on": locked_on,
				"locked_by": locked_by,
				"reversal_of": document.get("general_reversal_of"),
			}
		)

	return rows


def get_accounts(company: str) -> list[dict]:
	return [
		{
			"account_number": row.account_number,
			"account_name": row.account_name,
			"account_label": row.account_label,
			"root_type": row.root_type,
			"account_type": row.account_type,
			"tax_key": row.tax_key,
			"disabled": _("Yes") if row.disabled else _("No"),
		}
		for row in frappe.get_all(
			"Account",
			filters={"company": company, "is_group": 0},
			fields=[
				"account_number",
				"account_name",
				"account_label",
				"root_type",
				"account_type",
				"tax_key",
				"disabled",
			],
			order_by="account_number asc, name asc",
		)
	]


def get_parties(party_type: str) -> list[dict]:
	name_field = "customer_name" if party_type == "Customer" else "supplier_name"
	return [
		{
			"party": row.name,
			"name_1": row.get(name_field),
			"tax_id": row.tax_id,
			"vat_id": row.tax_id,
			"disabled": _("Yes") if row.disabled else _("No"),
		}
		for row in frappe.get_all(
			party_type,
			fields=["name", name_field, "tax_id", "disabled"],
			order_by="name asc",
		)
	]


def get_assets(company: str, to_date: date) -> list[dict]:
	if not frappe.db.exists("DocType", "Asset"):
		return []

	return [
		{
			"asset": row.name,
			"asset_name": row.asset_name,
			"purchase_date": row.purchase_date,
			"gross_purchase_amount": flt(row.gross_purchase_amount),
			"available_for_use_date": row.available_for_use_date,
			"status": row.status,
		}
		for row in frappe.get_all(
			"Asset",
			filters={"company": company, "docstatus": ("<", 2), "purchase_date": ("<=", to_date)},
			fields=[
				"name",
				"asset_name",
				"purchase_date",
				"gross_purchase_amount",
				"available_for_use_date",
				"status",
			],
			order_by="name asc",
		)
	]


def get_attachments(vouchers: set[tuple[str, str]]) -> list[dict]:
	"""Which document belongs to which booking.

	The file's own name is the identifier: it is unique, it is stable, and it
	is what the file is called in the archive an auditor gets alongside this.
	"""
	if not vouchers:
		return []

	types = sorted({voucher_type for voucher_type, _name in vouchers})
	names = sorted({name for _type, name in vouchers})
	files = frappe.get_all(
		"File",
		filters={"attached_to_doctype": ("in", types), "attached_to_name": ("in", names)},
		fields=["name", "file_name", "attached_to_doctype", "attached_to_name"],
		order_by="attached_to_name asc, name asc",
	)

	return [
		{
			"voucher_type": file.attached_to_doctype,
			"voucher_no": file.attached_to_name,
			"file_name": file.file_name,
			"file_id": file.name,
		}
		for file in files
		if (file.attached_to_doctype, file.attached_to_name) in vouchers
	]


def get_lockdowns(company: str) -> list[dict]:
	return [
		{
			"lockdown": row.name,
			"locked_up_to": row.locked_up_to,
			"locked_on": row.creation,
			"locked_by": row.owner,
		}
		for row in frappe.get_all(
			"Ledger Lockdown",
			filters={"company": company},
			fields=["name", "locked_up_to", "creation", "owner"],
			order_by="locked_up_to asc",
		)
	]


def get_changes(vouchers: set[tuple[str, str]]) -> list[dict]:
	"""What was changed on a posted document after it was posted."""
	if not vouchers:
		return []

	names = sorted({name for _type, name in vouchers})
	types = sorted({voucher_type for voucher_type, _name in vouchers})
	versions = frappe.get_all(
		"Version",
		filters={"ref_doctype": ("in", types), "docname": ("in", names)},
		fields=["ref_doctype", "docname", "creation", "owner", "data"],
		order_by="docname asc, creation asc",
	)

	return [
		{
			"voucher_type": version.ref_doctype,
			"voucher_no": version.docname,
			"changed_on": version.creation,
			"changed_by": version.owner,
			"change": version.data,
		}
		for version in versions
		if (version.ref_doctype, version.docname) in vouchers
	]


# --- what the journal is built from -----------------------------------------


def get_document_numbers(entries: list[frappe._dict]) -> dict[str, frappe._dict]:
	"""Document fields and reversal link of the Journal Entries in the year."""
	names = sorted({entry.voucher_no for entry in entries if entry.voucher_type == "Journal Entry"})
	if not names:
		return {}

	return {
		row.name: row
		for row in frappe.get_all(
			"Journal Entry",
			filters={"name": ("in", names)},
			fields=["name", "bill_no", "cheque_no", "general_reversal_of"],
		)
	}


def get_lockdown_dates(company: str) -> list[tuple]:
	"""The lockdowns of the company, oldest first, as (up to, when, who)."""
	return [
		(getdate(row.locked_up_to), row.creation, row.owner)
		for row in frappe.get_all(
			"Ledger Lockdown",
			filters={"company": company},
			fields=["locked_up_to", "creation", "owner"],
			order_by="locked_up_to asc",
		)
	]


def lockdown_for(lockdowns: list[tuple], posting_date) -> tuple:
	"""When an entry stopped being changeable, and who made it so.

	The first lockdown that reaches this posting date, because that is the one
	that closed it. Entries in a period nobody has closed yet carry nothing --
	which is the truth about them.
	"""
	posting_date = getdate(posting_date)
	for locked_up_to, locked_on, locked_by in lockdowns:
		if posting_date <= locked_up_to:
			return (locked_on, locked_by)

	return (None, None)


def fiscal_year_range(fiscal_year: str) -> tuple[date, date]:
	dates = frappe.get_cached_value(
		"Fiscal Year", fiscal_year, ["year_start_date", "year_end_date"], as_dict=True
	)
	if not dates:
		frappe.throw(_("Fiscal Year {0} not found").format(fiscal_year))

	return (getdate(dates.year_start_date), getdate(dates.year_end_date))
