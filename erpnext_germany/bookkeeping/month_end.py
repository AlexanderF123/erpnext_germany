# Copyright (c) 2026, ALYF GmbH and contributors
# For license information, please see license.txt

"""The checks a period has to pass before it is closed.

Closing a period is irreversible by design, so the questions worth asking are
the ones a practice asks before a return goes out: does the tax on the tax
accounts match the tax the turnover implies, is anything still sitting on a
clearing account, is a supplier showing a debit balance. None of them are
errors on their own -- each is a question, and the answer may well be "yes,
that is right". What matters is that nobody closes a month without having
seen them.

Every finding carries the account and the period it was found in, so it can be
followed to the Kontoblatt and from there to the booking, rather than sending
whoever runs the check off to look for it.
"""

from collections.abc import Callable
from datetime import date

import frappe
from frappe import _
from frappe.query_builder.functions import Sum
from frappe.utils import flt, getdate

from erpnext_germany.bookkeeping.account_search import account_label
from erpnext_germany.bookkeeping.document_ranges import describe_gap, find_gaps
from erpnext_germany.bookkeeping.ledger import LedgerScope, get_totals
from erpnext_germany.bookkeeping.tax import OUTPUT_TAX, expected_tax, verify_tax

# Tax is rounded per document and the check adds the documents up, so a clean
# month still differs by cents. Anything under this is not worth a person's
# attention; anything over it is.
TAX_TOLERANCE = 1.0

# ERPNext's own marker for a clearing or interim account. Used rather than a
# list of our own, so an account that is one says so in the chart itself.
CLEARING_ACCOUNT_TYPE = "Temporary"


class Finding(frappe._dict):
	"""One thing worth looking at, and where to look."""


def get_checks() -> dict[str, Callable]:
	"""The checks, in the order they are worth reading.

	Named here rather than discovered, so that adding one is a decision
	somebody made rather than a side effect of naming a function a certain way.
	"""
	return {
		"tax_verification": check_tax_verification,
		"clearing_accounts": check_clearing_accounts,
		"missing_cost_center": check_missing_cost_center,
		"creditors_with_debit_balance": check_creditors_with_debit_balance,
		"debtors_with_credit_balance": check_debtors_with_credit_balance,
		"disabled_accounts": check_disabled_accounts,
		"vouchers_without_document": check_vouchers_without_document,
		"document_number_gaps": check_document_number_gaps,
	}


def get_titles() -> dict[str, str]:
	return {
		"tax_verification": _("VAT Verification"),
		"clearing_accounts": _("Balances on Clearing Accounts"),
		"missing_cost_center": _("Postings Without a Cost Center"),
		"creditors_with_debit_balance": _("Suppliers With a Debit Balance"),
		"debtors_with_credit_balance": _("Customers With a Credit Balance"),
		"disabled_accounts": _("Postings to Disabled Accounts"),
		"vouchers_without_document": _("Vouchers Without a Document"),
		"document_number_gaps": _("Gaps in the Document Numbering"),
	}


def run_checks(company: str, from_date: date, to_date: date) -> dict[str, list[Finding]]:
	"""Every check, over one company and one period."""
	return {name: check(company, from_date, to_date) for name, check in get_checks().items()}


# --- the checks -------------------------------------------------------------


def check_tax_verification(company: str, from_date: date, to_date: date) -> list[Finding]:
	"""Does each tax account hold the tax its turnover implies.

	Verprobt per tax account rather than per tax key: several keys can book to
	the same account, and then the account's balance is the only figure that
	exists to compare against. The keys that feed it are named with the
	finding, because "1576 is 240 EUR out" is not something anyone can act on
	without knowing which accounts fed it.
	"""
	totals = get_totals(
		LedgerScope(company=company, from_date=from_date, to_date=to_date, skip_period_closing=True)
	)
	findings = []

	for tax_account, keys in tax_accounts(company).items():
		expected = 0.0
		causes = []
		for key in keys:
			net = net_turnover(totals, key.accounts, key.effect)
			expected += expected_tax(net, key.rate)
			causes.extend(key.accounts)

		booked = booked_tax(totals, tax_account, keys[0].effect)
		verification = verify_tax(expected, booked)
		if verification.is_clean(TAX_TOLERANCE):
			continue

		findings.append(
			Finding(
				label=account_label(tax_account),
				account=tax_account,
				amount=verification.deviation,
				detail=_("Expected {0}, booked {1}. From: {2}").format(
					frappe.format_value(verification.expected, {"fieldtype": "Currency"}),
					frappe.format_value(verification.booked, {"fieldtype": "Currency"}),
					", ".join(sorted(set(causes))) or _("no accounts"),
				),
			)
		)

	return findings


def check_clearing_accounts(company: str, from_date: date, to_date: date) -> list[Finding]:
	"""Anything left on a clearing account at the end of a month is unfinished work."""
	accounts = frappe.get_all(
		"Account",
		filters={"company": company, "is_group": 0, "account_type": CLEARING_ACCOUNT_TYPE},
		pluck="name",
	)
	if not accounts:
		return []

	# Up to the end of the period, not within it: what matters is what is still
	# sitting there, not what moved through.
	totals = get_totals(LedgerScope(company=company, to_date=to_date))
	findings = []
	for account in accounts:
		row = totals.get(account) or {}
		balance = flt(row.get("debit")) - flt(row.get("credit"))
		if abs(balance) < 0.005:
			continue

		findings.append(Finding(label=account_label(account), account=account, amount=balance))

	return findings


def check_missing_cost_center(company: str, from_date: date, to_date: date) -> list[Finding]:
	"""Income and expense without a cost center cannot be reported on."""
	gl_entry = frappe.qb.DocType("GL Entry")
	account = frappe.qb.DocType("Account")
	rows = (
		frappe.qb.from_(gl_entry)
		.join(account)
		.on(account.name == gl_entry.account)
		.select(gl_entry.voucher_type, gl_entry.voucher_no, gl_entry.account, gl_entry.debit, gl_entry.credit)
		.where(gl_entry.company == company)
		.where(gl_entry.posting_date[from_date:to_date])
		.where(gl_entry.is_cancelled == 0)
		.where(account.root_type.isin(["Income", "Expense"]))
		.where((gl_entry.cost_center.isnull()) | (gl_entry.cost_center == ""))
	).run(as_dict=True)

	return [
		Finding(
			label=account_label(row.account),
			account=row.account,
			amount=flt(row.debit) - flt(row.credit),
			voucher_type=row.voucher_type,
			voucher_no=row.voucher_no,
		)
		for row in rows
	]


def check_creditors_with_debit_balance(company: str, from_date: date, to_date: date) -> list[Finding]:
	"""A supplier we are owed money by is usually an unposted credit note."""
	return party_balances(company, to_date, "Payable", "Supplier", wrong_sign=1)


def check_debtors_with_credit_balance(company: str, from_date: date, to_date: date) -> list[Finding]:
	"""A customer in credit is usually a payment that found the wrong invoice."""
	return party_balances(company, to_date, "Receivable", "Customer", wrong_sign=-1)


def check_disabled_accounts(company: str, from_date: date, to_date: date) -> list[Finding]:
	"""An account is disabled to stop it being used. A posting on one says otherwise."""
	disabled = frappe.get_all("Account", filters={"company": company, "disabled": 1}, pluck="name")
	if not disabled:
		return []

	gl_entry = frappe.qb.DocType("GL Entry")
	rows = (
		frappe.qb.from_(gl_entry)
		.select(gl_entry.voucher_type, gl_entry.voucher_no, gl_entry.account, gl_entry.debit, gl_entry.credit)
		.where(gl_entry.company == company)
		.where(gl_entry.posting_date[from_date:to_date])
		.where(gl_entry.is_cancelled == 0)
		.where(gl_entry.account.isin(disabled))
	).run(as_dict=True)

	return [
		Finding(
			label=account_label(row.account),
			account=row.account,
			amount=flt(row.debit) - flt(row.credit),
			voucher_type=row.voucher_type,
			voucher_no=row.voucher_no,
		)
		for row in rows
	]


def check_vouchers_without_document(company: str, from_date: date, to_date: date) -> list[Finding]:
	"""Keine Buchung ohne Beleg -- the oldest rule there is.

	Only the vouchers this app posts are looked at. An invoice carries its own
	document by being one; a manual entry is where a missing document actually
	means something.
	"""
	entries = frappe.get_all(
		"Journal Entry",
		filters={"company": company, "docstatus": 1, "posting_date": ("between", [from_date, to_date])},
		fields=["name", "posting_date", "total_debit", "user_remark"],
	)
	if not entries:
		return []

	attached = set(
		frappe.get_all(
			"File",
			filters={
				"attached_to_doctype": "Journal Entry",
				"attached_to_name": ("in", [entry.name for entry in entries]),
			},
			pluck="attached_to_name",
		)
	)

	return [
		Finding(
			label=entry.name,
			amount=flt(entry.total_debit),
			detail=entry.user_remark,
			voucher_type="Journal Entry",
			voucher_no=entry.name,
		)
		for entry in entries
		if entry.name not in attached
	]


def check_document_number_gaps(company: str, from_date: date, to_date: date) -> list[Finding]:
	"""Numbers nothing was written under, in the ranges covering this period.

	The other half of the question the missing-document check asks. That one
	asks whether there is a document for a payment; this one asks whether
	there is a document for a number -- and a gap in the numbering is what an
	auditor takes as evidence that one was written and made to disappear.

	Checked over the whole range rather than only the month: a sequence is
	unbroken or it is not, and a gap in March is still a gap in April.
	"""
	findings = []
	for name in frappe.get_all(
		"Document Range",
		filters={"company": company, "disabled": 0},
		pluck="name",
		order_by="title asc",
	):
		document_range = frappe.get_doc("Document Range", name)
		if not covers(document_range, to_date):
			continue

		prefix = document_range.prefix or ""
		numbers = [document.number for document in document_range.documents() if document.number is not None]
		findings.extend(
			Finding(
				label=f"{document_range.name}: {describe_gap(gap, prefix)}",
				amount=gap.size,
				detail=_("Nothing was written under this."),
			)
			for gap in find_gaps(numbers)
		)

	return findings


def covers(document_range, to_date: date) -> bool:
	"""Whether this range belongs to the year the period ends in."""
	year = frappe.get_cached_value(
		"Fiscal Year",
		document_range.fiscal_year,
		["year_start_date", "year_end_date"],
		as_dict=True,
	)
	if not year:
		return False

	return getdate(year.year_start_date) <= getdate(to_date) <= getdate(year.year_end_date)


# --- what the checks are built from -----------------------------------------


def tax_accounts(company: str) -> dict[str, list[frappe._dict]]:
	"""Which tax keys book to which tax account in this company."""
	rows = frappe.get_all(
		"Tax Key Account",
		filters={"company": company, "parenttype": "Tax Key"},
		fields=["parent", "tax_account"],
	)

	accounts = {}
	for row in rows:
		key = frappe.get_cached_doc("Tax Key", row.parent)
		if key.disabled or not key.rate:
			continue

		accounts.setdefault(row.tax_account, []).append(
			frappe._dict(
				name=key.name,
				rate=key.rate,
				effect=key.effect,
				accounts=frappe.get_all(
					"Account", filters={"company": company, "tax_key": key.name}, pluck="name"
				),
			)
		)

	return accounts


def net_turnover(totals: dict, accounts: list[str], effect: str) -> float:
	"""The net the tax was supposed to be calculated on, in its own direction."""
	total = 0.0
	for account in accounts:
		row = totals.get(account) or {}
		total += direction(effect) * (flt(row.get("debit")) - flt(row.get("credit")))

	return total


def booked_tax(totals: dict, tax_account: str, effect: str) -> float:
	row = totals.get(tax_account) or {}
	return direction(effect) * (flt(row.get("debit")) - flt(row.get("credit")))


def direction(effect: str) -> int:
	"""Which way round an effect's accounts carry their balance.

	Input tax sits on the debit side, output tax on the credit side. Reverse
	charge is read like input tax, because the expense that carries it does.
	"""
	return -1 if effect == OUTPUT_TAX else 1


def party_balances(
	company: str, to_date: date, account_type: str, party_type: str, wrong_sign: int
) -> list[Finding]:
	"""Parties whose balance is on the side it should not be on."""
	gl_entry = frappe.qb.DocType("GL Entry")
	rows = (
		frappe.qb.from_(gl_entry)
		.select(
			gl_entry.party,
			gl_entry.account,
			(Sum(gl_entry.debit) - Sum(gl_entry.credit)).as_("balance"),
		)
		.where(gl_entry.company == company)
		.where(gl_entry.posting_date <= to_date)
		.where(gl_entry.is_cancelled == 0)
		.where(gl_entry.party_type == party_type)
		.groupby(gl_entry.party, gl_entry.account)
	).run(as_dict=True)

	return [
		Finding(
			label=f"{row.party} ({account_label(row.account)})",
			account=row.account,
			party=row.party,
			amount=flt(row.balance),
		)
		for row in rows
		if flt(row.balance) * wrong_sign > 0.005
	]


# --- keeping the result -----------------------------------------------------


def render(company: str, from_date: date, to_date: date, results: dict) -> str:
	"""The result as a page, for filing rather than for reading on screen."""
	titles = get_titles()
	period = f"{frappe.utils.format_date(from_date)} &ndash; {frappe.utils.format_date(to_date)}"
	parts = [
		f"<h3>{_('Month End Checklist')}</h3>",
		f"<p>{frappe.utils.escape_html(company)}<br>{period}</p>",
	]

	for name, findings in results.items():
		heading = _("{0}: {1} finding(s)").format(titles.get(name, name), len(findings))
		parts.append(f"<h4>{frappe.utils.escape_html(heading)}</h4>")

		if not findings:
			parts.append(f"<p>{_('Nothing to look at.')}</p>")
			continue

		items = "".join(rendered_finding(finding) for finding in findings)
		parts.append(f"<ul>{items}</ul>")

	return "\n".join(parts)


def rendered_finding(finding: Finding) -> str:
	label = frappe.utils.escape_html(finding.get("label") or "")
	amount = frappe.format_value(flt(finding.get("amount")), {"fieldtype": "Currency"})
	detail = finding.get("detail")
	note = f" ({frappe.utils.escape_html(detail)})" if detail else ""

	return f"<li>{label} &mdash; {amount}{note}</li>"


@frappe.whitelist()
def archive(company: str, from_date: str, to_date: str) -> str:
	"""File the result with the company.

	Filed rather than left on screen, because the question an auditor asks
	later is not "was there a checklist" but "what did the people who closed
	this month see when they closed it".
	"""
	return attach(company, frappe.utils.getdate(from_date), frappe.utils.getdate(to_date))


def attach(company: str, from_date: date, to_date: date) -> str:
	results = run_checks(company, from_date, to_date)
	file = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"Pruefliste {company} {frappe.utils.format_date(to_date)}.html",
			"attached_to_doctype": "Company",
			"attached_to_name": company,
			"content": render(company, from_date, to_date, results),
			"is_private": 1,
		}
	).insert()

	return file.name
