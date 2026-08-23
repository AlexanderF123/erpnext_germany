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

from datetime import date

import frappe
from erpnext.accounts.utils import get_fiscal_year
from frappe import _
from frappe.utils import add_days, flt, getdate

from erpnext_germany.bookkeeping.account_search import account_label
from erpnext_germany.bookkeeping.account_sheet import (
	Movement,
	contra_accounts,
	document_number,
	in_natural_direction,
	running_balances,
	starts_each_year_at_zero,
)
from erpnext_germany.bookkeeping.ledger import LedgerScope, get_cost_centers, get_totals
from erpnext_germany.bookkeeping.reversal import reversal_sides
from erpnext_germany.bookkeeping.vouchers import attachments as voucher_attachments
from erpnext_germany.bookkeeping.vouchers import document_fields


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
	entries = get_entries(period_scope(filters, cost_centers))
	opening = get_opening(filters, cost_centers, root_type)

	balances = running_balances(opening, [Movement(flt(entry.debit), flt(entry.credit)) for entry in entries])
	vouchers = {(entry.voucher_type, entry.voucher_no) for entry in entries}
	documents = document_fields(vouchers)
	# What the paperclip in the sheet opens, in the shape the sheet shows it.
	filed = {
		voucher: [{"name": file.file_name, "url": file.file_url} for file in files]
		for voucher, files in voucher_attachments(vouchers).items()
	}

	rows = [opening_row(filters, root_type, opening)]
	for entry, balance in zip(entries, balances, strict=True):
		voucher = (entry.voucher_type, entry.voucher_no)
		first, second = document_number(entry.voucher_type, documents.get(voucher, {}))
		rows.append(
			{
				"posting_date": entry.posting_date,
				# The voucher's own name stands in where there is no number on
				# the paper: a line of a sheet nobody can follow up is a line
				# nobody can use.
				"document_number": first or entry.voucher_no,
				"document_number_2": second,
				"against_account": contra_accounts(entry.against),
				"remark": entry.remarks,
				"debit": flt(entry.debit),
				"credit": flt(entry.credit),
				"balance": in_natural_direction(root_type, balance),
				"voucher_type": entry.voucher_type,
				"voucher_no": entry.voucher_no,
				"attachments": filed.get(voucher, []),
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


def period_scope(filters: frappe._dict, cost_centers: list[str] | None) -> LedgerScope:
	"""The entries the sheet shows as movements.

	Period closing vouchers are left out for the same reason the Summen- und
	Saldenliste leaves them out of a period: the carry forward of a closed
	year belongs in the balance the sheet opens with, not among the movements
	of a month.
	"""
	return LedgerScope(
		company=filters.company,
		from_date=filters.from_date,
		to_date=filters.to_date,
		cost_centers=cost_centers,
		accounts=[filters.account],
		skip_period_closing=True,
	)


def get_entries(scope: LedgerScope) -> list[frappe._dict]:
	"""The movements of the account, in the order they were booked.

	Ordered by date and then by creation, because two entries on the same day
	still happened one after the other, and a running balance that reorders
	them would show a balance the account never had.

	Read through the same rule as every evaluation: a general reversal counts
	as a minus on the side the mistake was booked on, so the turnover of the
	sheet is the turnover of the figure it was opened from.
	"""
	gl_entry = frappe.qb.DocType("GL Entry")
	debit, credit = reversal_sides(gl_entry, scope.company)

	query = scope.apply(
		frappe.qb.from_(gl_entry)
		.select(
			gl_entry.posting_date,
			debit.as_("debit"),
			credit.as_("credit"),
			gl_entry.against,
			gl_entry.remarks,
			gl_entry.voucher_type,
			gl_entry.voucher_no,
		)
		.orderby(gl_entry.posting_date)
		.orderby(gl_entry.creation),
		gl_entry,
	)

	return query.run(as_dict=True)


def get_opening(filters: frappe._dict, cost_centers: list[str] | None, root_type: str) -> float:
	"""The balance the sheet starts from.

	A balance sheet account carries everything ever booked to it. Income and
	expense start again at the beginning of the fiscal year the period falls
	in: last year's result was closed into equity, and a sheet that carried it
	forward as well would show every line off by a year's worth of costs --
	and would disagree with the Summen- und Saldenliste it was opened from,
	which applies the same rule.

	Period closing vouchers are counted here, because that is how the balance
	of a closed year is carried forward.
	"""
	if not filters.from_date:
		return 0.0

	from_date = getdate(filters.from_date)
	scope = LedgerScope(
		company=filters.company,
		from_date=year_start(filters.company, from_date) if starts_each_year_at_zero(root_type) else None,
		to_date=add_days(from_date, -1),
		cost_centers=cost_centers,
		accounts=[filters.account],
	)
	row = get_totals(scope).get(filters.account)
	return flt(row.debit) - flt(row.credit) if row else 0.0


def year_start(company: str, day: date) -> date:
	"""The first day of the fiscal year the given day falls in."""
	_name, start, _end = get_fiscal_year(day, company=company)
	return getdate(start)


@frappe.whitelist()
def get_account_title(account: str) -> str:
	"""What to call the account at the top of the sheet."""
	return account_label(account)
