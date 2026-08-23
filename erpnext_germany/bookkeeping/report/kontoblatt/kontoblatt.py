# Copyright (c) 2026, ALYF GmbH and contributors
# For license information, please see license.txt

"""The Kontoblatt: one account, every movement, and the balance after each.

This is where every evaluation in this app ends up. A figure in a BWA or a
Summen- und Saldenliste is only worth as much as the ability to ask what it
is made of, and the answer has to be the account read the way a bookkeeper
reads it: date, document number, contra account, text, debit, credit, and the
running balance that shows where an account started going wrong.

The line also says whether a document was filed with the booking, so the paper
behind a figure is one click away rather than a search in a folder.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

from erpnext_germany.bookkeeping.account_search import account_label
from erpnext_germany.bookkeeping.account_sheet import (
	DOCUMENT_NUMBER_FIELDS,
	Movement,
	contra_accounts,
	document_number,
	in_natural_direction,
	running_balances,
)
from erpnext_germany.bookkeeping.ledger import get_cost_centers
from erpnext_germany.bookkeeping.reversal import net_of_reversals


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.account:
		frappe.throw(_("Choose the account whose sheet you want to see."))

	if not filters.company:
		frappe.throw(_("Choose a company."))

	return get_columns(), get_data(filters)


def get_columns() -> list[dict]:
	return [
		{
			"fieldname": "posting_date",
			"label": _("Date"),
			"fieldtype": "Date",
			"width": 100,
		},
		{
			"fieldname": "document_number",
			"label": _("Document Field 1"),
			"fieldtype": "Data",
			"width": 140,
		},
		{
			"fieldname": "document_number_2",
			"label": _("Document Field 2"),
			"fieldtype": "Data",
			"width": 110,
		},
		{
			"fieldname": "against_account",
			"label": _("Contra Account"),
			"fieldtype": "Data",
			"width": 220,
		},
		{
			"fieldname": "remark",
			"label": _("Booking Text"),
			"fieldtype": "Data",
			"width": 280,
		},
		{
			"fieldname": "debit",
			"label": _("Debit"),
			"fieldtype": "Currency",
			"width": 130,
		},
		{
			"fieldname": "credit",
			"label": _("Credit"),
			"fieldtype": "Currency",
			"width": 130,
		},
		{
			"fieldname": "balance",
			"label": _("Balance"),
			"fieldtype": "Currency",
			"width": 140,
		},
		{
			"fieldname": "voucher_no",
			"label": _("Voucher"),
			"fieldtype": "Dynamic Link",
			"options": "voucher_type",
			"width": 170,
		},
		{
			"fieldname": "voucher_type",
			"label": _("Voucher Type"),
			"fieldtype": "Data",
			"width": 140,
			"hidden": 1,
		},
	]


def get_data(filters: frappe._dict) -> list[dict]:
	root_type = frappe.get_cached_value("Account", filters.account, "root_type")
	cost_centers = get_cost_centers(filters.cost_center)
	entries = get_entries(filters, cost_centers)
	opening = get_opening(filters, cost_centers)

	balances = running_balances(opening, [Movement(flt(entry.debit), flt(entry.credit)) for entry in entries])
	documents = get_document_fields(entries)
	attachments = get_attachments(entries)

	rows = [opening_row(filters, root_type, opening)]
	for entry, balance in zip(entries, balances, strict=True):
		first, second = document_number(
			entry.voucher_type, entry.voucher_no, documents.get(entry.voucher_no, {})
		)
		rows.append(
			{
				"posting_date": entry.posting_date,
				"document_number": first,
				"document_number_2": second,
				"against_account": contra_accounts(entry.against),
				"remark": entry.remarks,
				"debit": flt(entry.debit),
				"credit": flt(entry.credit),
				"balance": in_natural_direction(root_type, balance),
				"voucher_type": entry.voucher_type,
				"voucher_no": entry.voucher_no,
				# What the paperclip in the sheet opens.
				"attachments": attachments.get((entry.voucher_type, entry.voucher_no), []),
			}
		)

	return rows


def opening_row(filters: frappe._dict, root_type: str, opening: float) -> dict:
	"""The balance carried in, as the first line of the sheet.

	Always there, even at nought: a sheet whose first line is a movement
	invites the reader to assume the account started empty.
	"""
	return {
		"posting_date": getdate(filters.from_date) if filters.from_date else None,
		"remark": _("Balance carried forward"),
		"balance": in_natural_direction(root_type, opening),
		"is_opening": 1,
	}


def get_entries(filters: frappe._dict, cost_centers: list[str] | None) -> list[frappe._dict]:
	"""The movements of the account, in the order they were booked.

	Ordered by date and then by creation, because two entries on the same day
	still happened one after the other, and a running balance that reorders
	them would show a balance the account never had.
	"""
	gl_entry = frappe.qb.DocType("GL Entry")
	query = (
		frappe.qb.from_(gl_entry)
		.select(
			gl_entry.posting_date,
			gl_entry.debit_in_account_currency.as_("debit"),
			gl_entry.credit_in_account_currency.as_("credit"),
			gl_entry.against,
			gl_entry.remarks,
			gl_entry.voucher_type,
			gl_entry.voucher_no,
		)
		.where(gl_entry.company == filters.company)
		.where(gl_entry.account == filters.account)
		.where(gl_entry.is_cancelled == 0)
		.orderby(gl_entry.posting_date)
		.orderby(gl_entry.creation)
	)

	if filters.from_date:
		query = query.where(gl_entry.posting_date >= filters.from_date)

	if filters.to_date:
		query = query.where(gl_entry.posting_date <= filters.to_date)

	if cost_centers is not None:
		query = query.where(gl_entry.cost_center.isin(cost_centers))

	return query.run(as_dict=True)


def get_opening(filters: frappe._dict, cost_centers: list[str] | None) -> float:
	"""Everything booked before the period, as one figure.

	Read the same way the Summen- und Saldenliste reads it, general reversals
	included, so the sheet ties to the evaluation it was opened from.
	"""
	if not filters.from_date:
		return 0.0

	gl_entry = frappe.qb.DocType("GL Entry")
	debit, credit = net_of_reversals(gl_entry, filters.company)
	query = (
		frappe.qb.from_(gl_entry)
		.select(debit.as_("debit"), credit.as_("credit"))
		.where(gl_entry.company == filters.company)
		.where(gl_entry.account == filters.account)
		.where(gl_entry.is_cancelled == 0)
		.where(gl_entry.posting_date < filters.from_date)
	)

	if cost_centers is not None:
		query = query.where(gl_entry.cost_center.isin(cost_centers))

	rows = query.run(as_dict=True)
	return flt(rows[0].debit) - flt(rows[0].credit) if rows else 0.0


def get_document_fields(entries: list[frappe._dict]) -> dict[str, dict]:
	"""The document numbers of the vouchers on this sheet, in one query per type.

	Fetched in a batch rather than per line: a sheet is hundreds of lines and
	a query per line is what makes a report feel slow enough to be avoided.
	"""
	fields_by_type = {}
	for entry in entries:
		if entry.voucher_type in DOCUMENT_NUMBER_FIELDS:
			fields_by_type.setdefault(entry.voucher_type, set()).add(entry.voucher_no)

	documents = {}
	for voucher_type, names in fields_by_type.items():
		fields = [field for field in DOCUMENT_NUMBER_FIELDS[voucher_type] if field]
		for row in frappe.get_all(
			voucher_type, filters={"name": ("in", list(names))}, fields=["name", *fields]
		):
			documents[row.name] = row

	return documents


def get_attachments(entries: list[frappe._dict]) -> dict[tuple[str, str], list[dict]]:
	"""Which vouchers have a document filed with them, and where it is.

	One query for the whole sheet. The sheet only shows that there is
	something; opening it is the reader's next click.
	"""
	names = {entry.voucher_no for entry in entries}
	if not names:
		return {}

	files = frappe.get_all(
		"File",
		filters={
			"attached_to_doctype": ("in", list({entry.voucher_type for entry in entries})),
			"attached_to_name": ("in", list(names)),
		},
		fields=["file_name", "file_url", "attached_to_doctype", "attached_to_name"],
		order_by="creation asc",
	)

	attachments = {}
	for file in files:
		key = (file.attached_to_doctype, file.attached_to_name)
		attachments.setdefault(key, []).append({"name": file.file_name, "url": file.file_url})

	return attachments


@frappe.whitelist()
def get_account_title(account: str) -> str:
	"""What to call the account at the top of the sheet."""
	return account_label(account)
