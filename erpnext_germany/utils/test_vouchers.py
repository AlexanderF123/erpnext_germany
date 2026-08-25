# Copyright (c) 2026, ALYF GmbH and contributors
# For license information, please see license.txt

from erpnext_germany.utils.vouchers import contra_accounts, document_number

# --- the document fields ----------------------------------------------------


def test_an_incoming_invoice_keeps_the_suppliers_number():
	"""Belegfeld 1 is the number on the paper, not the one we gave it."""
	first, second = document_number("Purchase Invoice", {"bill_no": "RE 4711"})

	assert first == "RE 4711"
	assert second == ""


def test_a_journal_entry_carries_both_document_fields():
	first, second = document_number("Journal Entry", {"bill_no": "RE 4711", "cheque_no": "K 22"})

	assert (first, second) == ("RE 4711", "K 22")


def test_a_voucher_without_a_document_number_has_none():
	"""Empty stays empty: a number nobody wrote is not a number to report.

	Standing a voucher under its own name is a decision of whoever reads the
	sheet, and it is taken where that reason is visible.
	"""
	assert document_number("Sales Invoice", {}) == ("", "")
	assert document_number("Journal Entry", {"bill_no": "  "}) == ("", "")


# --- the contra account -----------------------------------------------------


def test_a_line_booked_against_one_account_names_it():
	assert contra_accounts("1200 - Bank") == "1200 - Bank"


def test_a_line_booked_against_several_names_the_first_and_counts_the_rest():
	"""A column that grows without limit makes the sheet unreadable."""
	assert contra_accounts("1200 - Bank, 1576 - Vorsteuer, 4980 - Buero") == "1200 - Bank (+2)"


def test_a_line_booked_against_nothing_leaves_the_column_empty():
	assert contra_accounts(None) == ""
	assert contra_accounts(" , ") == ""
