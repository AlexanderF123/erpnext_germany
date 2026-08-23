# Copyright (c) 2023, ALYF GmbH and contributors
# For license information, please see license.txt

from datetime import date

import frappe
from babel.dates import format_date
from frappe import _
from frappe.query_builder.functions import Sum
from frappe.utils import add_days, cint, flt
from frappe.utils.nestedset import get_descendants_of

from erpnext_germany.utils.periods import get_month_range, shift_years

DEBIT_ROOT_TYPES = ("Asset", "Expense")
BALANCE_SHEET_ROOT_TYPES = ("Asset", "Liability", "Equity")

# Amounts below this are treated as zero when hiding empty rows.
ROUNDING_TOLERANCE = 0.005

# Every column that carries a figure, listed explicitly instead of derived by
# exclusion, so that adding a descriptive field can never silently make rows
# count as empty.
AMOUNT_FIELDS = (
	"debit_opening_balance",
	"credit_opening_balance",
	"debit_until_evaluation_period",
	"credit_until_evaluation_period",
	"debit_in_evaluation_period",
	"credit_in_evaluation_period",
	"debit_closing_balance",
	"credit_closing_balance",
	"previous_year_in_evaluation_period",
	"previous_year_until_evaluation_period",
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	fiscal_year_start = frappe.get_cached_value("Fiscal Year", filters.fiscal_year, "year_start_date")
	if not fiscal_year_start:
		frappe.throw(_("Fiscal Year {0} not found").format(filters.fiscal_year))

	month_start, month_end = get_month_range(fiscal_year_start, cint(filters.month))
	month_name = format_date(month_start, format="MMMM", locale=frappe.local.lang)
	with_previous_year = bool(cint(filters.with_previous_year))

	columns = get_columns(month_name, with_previous_year)
	data = get_data(filters, fiscal_year_start, month_start, month_end, with_previous_year)
	return columns, data


def get_columns(month_name: str, with_previous_year: bool):
	columns = [
		{
			"fieldname": "account",
			"label": _("Account"),
			"fieldtype": "Link",
			"options": "Account",
			"width": 300,
		},
		{
			"fieldname": "account_name",
			"label": _("Account Name"),
			"fieldtype": "Data",
			"width": 220,
		},
		{
			"fieldname": "account_currency",
			"label": _("Currency"),
			"fieldtype": "Link",
			"options": "Currency",
			"width": 100,
		},
		{
			"fieldname": "debit_opening_balance",
			"label": _("Debit Opening Balance"),
			"fieldtype": "Currency",
			"width": 170,
			"options": "account_currency",
		},
		{
			"fieldname": "credit_opening_balance",
			"label": _("Credit Opening Balance"),
			"fieldtype": "Currency",
			"width": 170,
			"options": "account_currency",
		},
		{
			"fieldname": "debit_until_evaluation_period",
			"label": _("Debit until {0}").format(month_name),
			"fieldtype": "Currency",
			"width": 170,
			"options": "account_currency",
		},
		{
			"fieldname": "credit_until_evaluation_period",
			"label": _("Credit until {0}").format(month_name),
			"fieldtype": "Currency",
			"width": 170,
			"options": "account_currency",
		},
		{
			"fieldname": "debit_in_evaluation_period",
			"label": _("Debit in {0}").format(month_name),
			"fieldtype": "Currency",
			"width": 170,
			"options": "account_currency",
		},
		{
			"fieldname": "credit_in_evaluation_period",
			"label": _("Credit in {0}").format(month_name),
			"fieldtype": "Currency",
			"width": 170,
			"options": "account_currency",
		},
		{
			"fieldname": "debit_closing_balance",
			"label": _("Debit Closing Balance"),
			"fieldtype": "Currency",
			"width": 170,
			"options": "account_currency",
		},
		{
			"fieldname": "credit_closing_balance",
			"label": _("Credit Closing Balance"),
			"fieldtype": "Currency",
			"width": 170,
			"options": "account_currency",
		},
	]

	if with_previous_year:
		columns += [
			{
				"fieldname": "previous_year_in_evaluation_period",
				"label": _("Previous year in {0}").format(month_name),
				"fieldtype": "Currency",
				"width": 180,
				"options": "account_currency",
			},
			{
				"fieldname": "previous_year_until_evaluation_period",
				"label": _("Previous year up to and including {0}").format(month_name),
				"fieldtype": "Currency",
				"width": 220,
				"options": "account_currency",
			},
		]

	return columns


def get_periods(
	fiscal_year_start: date, month_start: date, month_end: date, with_previous_year: bool
) -> list[tuple]:
	"""Return the periods the report aggregates, as (key, from, to, skip closing).

	The opening period deliberately includes period closing vouchers: that is
	how the balance of a closed year is carried forward.
	"""
	periods = [
		("opening", None, add_days(fiscal_year_start, -1), False),
		("until", fiscal_year_start, add_days(month_start, -1), True),
		("current", month_start, month_end, True),
	]

	if with_previous_year:
		previous_month_end = shift_years(month_end, -1)
		periods += [
			("previous_current", shift_years(month_start, -1), previous_month_end, True),
			("previous_until", shift_years(fiscal_year_start, -1), previous_month_end, True),
		]

	return periods


def get_data(
	filters: frappe._dict,
	fiscal_year_start: date,
	month_start: date,
	month_end: date,
	with_previous_year: bool,
):
	cost_centers = get_cost_centers(filters.cost_center)
	totals = {
		key: get_totals(filters.company, cost_centers, from_date, to_date, skip_closing)
		for key, from_date, to_date, skip_closing in get_periods(
			fiscal_year_start, month_start, month_end, with_previous_year
		)
	}

	# An account belongs into the report if it carries an opening balance or was
	# touched in the current fiscal year, even if there was no movement in the
	# evaluation month itself.
	account_names = set(totals["opening"]) | set(totals["until"]) | set(totals["current"])
	if not account_names:
		return []

	accounts = get_accounts(account_names)
	hide_empty_rows = cint(filters.hide_empty_rows)

	rows = []
	for name in account_names:
		account = accounts.get(name)
		if not account:
			# The account was deleted, but its ledger entries remain.
			continue

		row = build_row(
			account,
			{key: period.get(name, {}) for key, period in totals.items()},
			month_start,
			month_end,
			with_previous_year,
		)
		if hide_empty_rows and is_empty(row):
			continue

		rows.append(row)

	return sorted(rows, key=sort_key)


def build_row(
	account: frappe._dict,
	totals: dict[str, dict],
	month_start: date,
	month_end: date,
	with_previous_year: bool,
) -> frappe._dict:
	root_type = account.root_type

	# Income and expense accounts start every fiscal year at zero: last year's
	# result is closed into equity and must not be carried forward here.
	carried_forward = net(totals["opening"]) if root_type in BALANCE_SHEET_ROOT_TYPES else 0.0
	closing = carried_forward + net(totals["until"]) + net(totals["current"])

	opening_debit, opening_credit = (
		in_natural_direction(root_type, carried_forward)
		if root_type in BALANCE_SHEET_ROOT_TYPES
		else (None, None)
	)
	closing_debit, closing_credit = in_natural_direction(root_type, closing)

	row = frappe._dict(
		{
			"account": account.name,
			"account_name": account.account_name,
			"account_number": account.account_number,
			"account_currency": account.account_currency,
			"debit_opening_balance": opening_debit,
			"credit_opening_balance": opening_credit,
			"debit_until_evaluation_period": totals["until"].get("debit"),
			"credit_until_evaluation_period": totals["until"].get("credit"),
			"debit_in_evaluation_period": totals["current"].get("debit"),
			"credit_in_evaluation_period": totals["current"].get("credit"),
			"debit_closing_balance": closing_debit,
			"credit_closing_balance": closing_credit,
			# Carried along so that the client can link the account to its ledger
			# for exactly this period, without recomputing the dates.
			"period_from_date": month_start,
			"period_to_date": month_end,
		}
	)

	if with_previous_year:
		row.previous_year_in_evaluation_period = natural_net(root_type, totals["previous_current"])
		row.previous_year_until_evaluation_period = natural_net(root_type, totals["previous_until"])

	return row


def net(totals: dict) -> float:
	"""Debit minus credit of one period."""
	return flt(totals.get("debit")) - flt(totals.get("credit"))


def natural_net(root_type: str, totals: dict) -> float:
	"""Net movement, signed so that a normal balance reads positive."""
	amount = net(totals)
	return amount if root_type in DEBIT_ROOT_TYPES else -amount


def in_natural_direction(root_type: str, amount: float) -> tuple[float | None, float | None]:
	"""Put a debit-minus-credit amount on the side the account normally carries."""
	return (amount, None) if root_type in DEBIT_ROOT_TYPES else (None, -amount)


def is_empty(row: frappe._dict) -> bool:
	return all(abs(flt(row.get(field))) < ROUNDING_TOLERANCE for field in AMOUNT_FIELDS)


def sort_key(row: frappe._dict) -> tuple[int, int, str]:
	"""Sort by account number, falling back to the account name.

	Account numbers are compared numerically so that 9 sorts before 10. Accounts
	without a numeric account number are listed last.
	"""
	account_number = str(row.account_number or "").strip()
	if account_number.isdigit():
		return (0, int(account_number), row.account)

	return (1, 0, row.account)


def get_cost_centers(cost_center: str | None) -> list[str] | None:
	"""Return the cost center including all of its descendants, or None for no filter."""
	if not cost_center:
		return None

	return [cost_center, *get_descendants_of("Cost Center", cost_center)]


def get_totals(
	company: str,
	cost_centers: list[str] | None,
	from_date: date | None = None,
	to_date: date | None = None,
	skip_period_closing: bool = False,
) -> dict[str, frappe._dict]:
	"""Return gross debit and credit totals per account for the given period.

	Both bounds are inclusive.
	"""
	gl_entry = frappe.qb.DocType("GL Entry")

	query = (
		frappe.qb.from_(gl_entry)
		.select(
			gl_entry.account,
			Sum(gl_entry.debit_in_account_currency).as_("debit"),
			Sum(gl_entry.credit_in_account_currency).as_("credit"),
		)
		.where((gl_entry.company == company) & (gl_entry.is_cancelled == 0))
		.groupby(gl_entry.account)
	)

	if from_date:
		query = query.where(gl_entry.posting_date >= from_date)

	if to_date:
		query = query.where(gl_entry.posting_date <= to_date)

	if skip_period_closing:
		query = query.where(gl_entry.voucher_type != "Period Closing Voucher")

	if cost_centers is not None:
		query = query.where(gl_entry.cost_center.isin(cost_centers))

	return {row.account: row for row in query.run(as_dict=True)}


def get_accounts(account_names: set[str]) -> dict[str, frappe._dict]:
	accounts = frappe.get_all(
		"Account",
		filters={"name": ("in", list(account_names))},
		fields=["name", "account_name", "account_number", "account_currency", "root_type"],
	)
	return {account.name: account for account in accounts}
