# Copyright (c) 2026, ALYF GmbH and contributors
# For license information, please see license.txt

from erpnext_germany.utils.account_sheet import (
	Movement,
	in_natural_direction,
	running_balances,
	starts_each_year_at_zero,
)

# --- the running balance ----------------------------------------------------


def test_the_balance_carried_in_is_where_the_sheet_starts():
	assert running_balances(500.0, [Movement(100.0, 0.0)]) == [600.0]


def test_each_line_shows_the_balance_as_it_stood_at_that_moment():
	"""This is what the sheet is for: reading until the figure stops matching."""
	movements = [Movement(100.0, 0.0), Movement(0.0, 30.0), Movement(0.0, 20.0)]

	assert running_balances(0.0, movements) == [100.0, 70.0, 50.0]


def test_a_sheet_without_movements_has_no_lines():
	assert running_balances(500.0, []) == []


def test_the_balance_may_cross_zero():
	"""An account can be overdrawn, and the sheet has to show where."""
	assert running_balances(50.0, [Movement(0.0, 80.0)]) == [-30.0]


# --- which way the balance reads --------------------------------------------


def test_an_expense_account_reads_its_costs_positive():
	assert in_natural_direction("Expense", 500.0) == 500.0


def test_a_revenue_account_reads_its_credit_balance_positive():
	assert in_natural_direction("Income", -500.0) == 500.0


def test_a_liability_reads_the_same_way_as_revenue():
	assert in_natural_direction("Liability", -1200.0) == 1200.0


# --- what an account carries from one year into the next --------------------


def test_a_balance_sheet_account_carries_its_balance_forward():
	for root_type in ("Asset", "Liability", "Equity"):
		assert not starts_each_year_at_zero(root_type)


def test_profit_and_loss_starts_every_year_at_nought():
	"""Last year's result was closed into equity.

	An evaluation that carried it forward here as well would count it twice,
	and a Kontoblatt that did would disagree with the Summen- und Saldenliste
	it was opened from.
	"""
	for root_type in ("Income", "Expense"):
		assert starts_each_year_at_zero(root_type)
