# Copyright (c) 2026, ALYF GmbH and contributors
# For license information, please see license.txt

from erpnext_germany.bookkeeping.account_sheet import (
	Movement,
	contra_accounts,
	document_number,
	in_natural_direction,
	running_balances,
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


# --- the document fields ----------------------------------------------------


def test_an_incoming_invoice_keeps_the_suppliers_number():
	"""Belegfeld 1 is the number on the paper, not the one we gave it."""
	first, second = document_number("Purchase Invoice", "ACC-PINV-0001", {"bill_no": "RE 4711"})

	assert first == "RE 4711"
	assert second == ""


def test_a_journal_entry_carries_both_document_fields():
	first, second = document_number(
		"Journal Entry", "ACC-JV-0001", {"bill_no": "RE 4711", "cheque_no": "K 22"}
	)

	assert (first, second) == ("RE 4711", "K 22")


def test_a_voucher_without_a_document_number_stands_under_its_own_name():
	"""A line with no reference at all cannot be followed up."""
	assert document_number("Sales Invoice", "ACC-SINV-0001", {})[0] == "ACC-SINV-0001"
	assert document_number("Journal Entry", "ACC-JV-0002", {"bill_no": "  "})[0] == "ACC-JV-0002"


# --- the contra account -----------------------------------------------------


def test_a_line_booked_against_one_account_names_it():
	assert contra_accounts("1200 - Bank") == "1200 - Bank"


def test_a_line_booked_against_several_names_the_first_and_counts_the_rest():
	"""A column that grows without limit makes the sheet unreadable."""
	assert contra_accounts("1200 - Bank, 1576 - Vorsteuer, 4980 - Buero") == "1200 - Bank (+2)"


def test_a_line_booked_against_nothing_leaves_the_column_empty():
	assert contra_accounts(None) == ""
	assert contra_accounts(" , ") == ""
