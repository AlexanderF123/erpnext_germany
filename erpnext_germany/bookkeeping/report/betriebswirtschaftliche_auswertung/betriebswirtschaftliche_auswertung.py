# Copyright (c) 2026, ALYF GmbH and contributors
# For license information, please see license.txt

"""The BWA: one month of business, on one sheet.

The arrangement comes from a BWA Schema, the figures from the same reading of
the ledger the Summen- und Saldenliste uses. Every line can be opened to the
accounts behind it, and every account from there to its ledger, so that a
figure a tax advisor queries can be followed to the booking that caused it
without leaving the sheet.

What the report adds to the arrangement is a check the arrangement cannot do
for itself: any income or expense account that no line covers is listed at the
bottom. Without that, a range written one digit short would quietly leave
money out of the result, and a BWA that silently omits is worse than one that
is obviously incomplete.
"""

from datetime import date

import frappe
from babel.dates import format_date
from frappe import _
from frappe.utils import cint, flt

from erpnext_germany.bookkeeping.bwa import ACCOUNTS, RATIO, covered_by, deviation, evaluate, row_amount
from erpnext_germany.bookkeeping.ledger import get_cost_centers, get_totals
from erpnext_germany.utils.periods import get_month_range, shift_years

PROFIT_AND_LOSS_ROOT_TYPES = ("Income", "Expense")

# Amounts below this count as no movement at all.
ROUNDING_TOLERANCE = 0.005


def execute(filters=None):
	filters = frappe._dict(filters or {})
	schema = get_schema(filters.bwa_schema)
	fiscal_year_start = frappe.get_cached_value("Fiscal Year", filters.fiscal_year, "year_start_date")
	if not fiscal_year_start:
		frappe.throw(_("Fiscal Year {0} not found").format(filters.fiscal_year))

	month_start, month_end = get_month_range(fiscal_year_start, cint(filters.month))
	month_name = format_date(month_start, format="MMMM", locale=frappe.local.lang)

	data = get_data(filters, schema, fiscal_year_start, month_start, month_end)
	return get_columns(month_name), data


def get_schema(name: str | None):
	if not name:
		frappe.throw(_("Choose the arrangement the BWA should be drawn up in."))

	return frappe.get_doc("BWA Schema", name)


def get_columns(month_name: str) -> list[dict]:
	return [
		{
			"fieldname": "label",
			"label": _("Item", context="BWA column"),
			"fieldtype": "Data",
			"width": 320,
		},
		{
			"fieldname": "current",
			"label": month_name,
			"fieldtype": "Currency",
			"width": 150,
		},
		{
			"fieldname": "cumulative",
			"label": _("Cumulative"),
			"fieldtype": "Currency",
			"width": 150,
		},
		{
			"fieldname": "previous_year",
			"label": _("{0} previous year").format(month_name),
			"fieldtype": "Currency",
			"width": 170,
		},
		{
			"fieldname": "deviation",
			"label": _("Deviation"),
			"fieldtype": "Percent",
			"width": 120,
		},
	]


def get_periods(fiscal_year_start: date, month_start: date, month_end: date) -> dict[str, tuple]:
	"""The three columns of figures, as date ranges.

	Derived from the fiscal year rather than the calendar, so a company whose
	year starts in July reads its own months.
	"""
	return {
		"current": (month_start, month_end),
		"cumulative": (fiscal_year_start, month_end),
		"previous_year": (shift_years(month_start, -1), shift_years(month_end, -1)),
	}


def get_data(
	filters: frappe._dict,
	schema,
	fiscal_year_start: date,
	month_start: date,
	month_end: date,
) -> list[dict]:
	cost_centers = get_cost_centers(filters.cost_center)
	periods = get_periods(fiscal_year_start, month_start, month_end)
	totals = {
		key: get_totals(filters.company, cost_centers, from_date, to_date, skip_period_closing=True)
		for key, (from_date, to_date) in periods.items()
	}

	accounts = get_accounts(filters.company)
	rows = schema.as_rows()
	assignment = assign_accounts(rows, accounts)

	values = {key: evaluate(rows, row_amounts(rows, assignment, period)) for key, period in totals.items()}

	data = []
	for row in rows:
		data.append(build_row(row, values, month_start, month_end))

		if cint(filters.show_accounts) and row.row_type == ACCOUNTS:
			data.extend(account_rows(row, assignment[row.number], accounts, totals, month_start, month_end))

	data.extend(unassigned_rows(assignment, accounts, totals, month_start, month_end))
	return data


def get_accounts(company: str) -> dict[str, frappe._dict]:
	rows = frappe.get_all(
		"Account",
		filters={"company": company, "is_group": 0},
		fields=["name", "account_number", "account_name", "account_label", "root_type"],
	)
	for row in rows:
		row.label = row.account_label or row.account_name

	return {row.name: row for row in rows}


def assign_accounts(rows, accounts: dict[str, frappe._dict]) -> dict[int, list[str]]:
	"""Which accounts each line of the form covers.

	Worked out once for the whole report: the same assignment has to hold for
	every column, or the comparison with last year would compare two
	different arrangements.
	"""
	return {
		row.number: sorted(
			name for name, account in accounts.items() if covered_by(account.account_number, row.ranges)
		)
		for row in rows
		if row.row_type == ACCOUNTS
	}


def row_amounts(rows, assignment: dict[int, list[str]], totals: dict) -> dict[int, float]:
	amounts = {}
	for row in rows:
		if row.row_type != ACCOUNTS:
			continue

		debit = sum(flt(totals.get(name, {}).get("debit")) for name in assignment[row.number])
		credit = sum(flt(totals.get(name, {}).get("credit")) for name in assignment[row.number])
		amounts[row.number] = row_amount(row.sign, debit, credit)

	return amounts


def build_row(row, values: dict[str, dict], month_start: date, month_end: date) -> dict:
	current = values["current"].get(row.number)
	previous = values["previous_year"].get(row.number)

	return {
		"label": row.label,
		"row_number": row.number,
		"indent": 0,
		# A result line is what the eye goes to first, so it is set apart.
		"is_result": int(row.row_type != ACCOUNTS),
		"is_ratio": int(row.row_type == RATIO),
		"current": current,
		"cumulative": values["cumulative"].get(row.number),
		"previous_year": previous,
		"deviation": deviation(current, previous),
		"period_from_date": month_start,
		"period_to_date": month_end,
	}


def account_rows(
	row, names: list[str], accounts: dict, totals: dict, month_start: date, month_end: date
) -> list[dict]:
	"""The accounts behind one line, read in the direction that line reads in.

	So a cost account under a cost line shows the positive figure the line
	shows, and the accounts of a line add up to the line.
	"""
	rows = []
	for name in names:
		figures = {
			key: row_amount(
				row.sign, flt(period.get(name, {}).get("debit")), flt(period.get(name, {}).get("credit"))
			)
			for key, period in totals.items()
		}
		detail = detail_row(accounts[name], name, figures, month_start, month_end)
		if detail:
			rows.append(detail)

	return rows


def detail_row(
	account: frappe._dict, name: str, figures: dict, month_start: date, month_end: date
) -> dict | None:
	"""One account under a line, or nothing where the account did not move."""
	if all(abs(figure) < ROUNDING_TOLERANCE for figure in figures.values()):
		return None

	return {
		"label": f"{account.account_number or ''} {account.label}".strip(),
		"account": name,
		"indent": 1,
		"is_result": 0,
		"is_ratio": 0,
		"current": figures["current"],
		"cumulative": figures["cumulative"],
		"previous_year": figures["previous_year"],
		"deviation": deviation(figures["current"], figures["previous_year"]),
		"period_from_date": month_start,
		"period_to_date": month_end,
	}


def unassigned_rows(
	assignment: dict[int, list[str]],
	accounts: dict[str, frappe._dict],
	totals: dict,
	month_start: date,
	month_end: date,
) -> list[dict]:
	"""Income and expense accounts that no line of the form covers.

	These belong in the result and are not in it. Listed rather than added in,
	because adding them would quietly change an arrangement someone signed off
	on -- but leaving them out silently would misstate the result.

	Read in the direction a result is read in, credit minus debit, because
	there is no line here to say which way is up.
	"""
	covered = {name for names in assignment.values() for name in names}
	loose = []
	for name, account in sorted(accounts.items(), key=lambda entry: entry[1].account_number or ""):
		if name in covered or account.root_type not in PROFIT_AND_LOSS_ROOT_TYPES:
			continue

		figures = {
			key: flt(period.get(name, {}).get("credit")) - flt(period.get(name, {}).get("debit"))
			for key, period in totals.items()
		}
		detail = detail_row(account, name, figures, month_start, month_end)
		if detail:
			loose.append(detail)

	if not loose:
		return []

	heading = {
		"label": _("Not covered by the BWA"),
		"indent": 0,
		"is_result": 1,
		"is_ratio": 0,
		"period_from_date": month_start,
		"period_to_date": month_end,
	}
	for key in ("current", "cumulative", "previous_year"):
		heading[key] = sum(row[key] for row in loose)

	heading["deviation"] = deviation(heading["current"], heading["previous_year"])

	return [heading, *loose]
