# Copyright (c) 2026, ALYF GmbH and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

from erpnext_germany.bookkeeping.doctype.posting_batch.test_posting_batch import (
	TEST_COMPANY,
	fiscal_year_for,
	posting_accounts,
)
from erpnext_germany.bookkeeping.ledger import LedgerScope, get_totals
from erpnext_germany.bookkeeping.reversal import REVERSAL_REMARK, reverse_entry

test_dependencies = ["Company"]

REASON = "Betrag falsch erfasst"


class TestReversal(FrappeTestCase):
	def setUp(self):
		self.expense, self.other_expense = posting_accounts("Expense", 2)
		self.asset = posting_accounts("Asset", 1)[0]
		self.day = nowdate()

	# --- helpers ----------------------------------------------------------

	def book(self, amount: float, account: str | None = None, on: str | None = None) -> str:
		"""Post one line and return the Journal Entry it became."""
		day = on or self.day
		batch = frappe.get_doc(
			{
				"doctype": "Posting Batch",
				"company": TEST_COMPANY,
				"fiscal_year": fiscal_year_for(day),
				"from_date": day,
				"to_date": day,
				"entries": [
					{
						"posting_date": day,
						"amount": amount,
						"direction": "Debit",
						"account": account or self.expense,
						"against_account": self.asset,
					}
				],
			}
		).insert()
		batch.post()
		return batch.entries[0].journal_entry

	def turnover(self, account: str | None = None) -> tuple[float, float]:
		"""Debit and credit turnover of the account, as the evaluation reads it."""
		totals = get_totals(LedgerScope(company=TEST_COMPANY, from_date=self.day, to_date=self.day))
		row = totals.get(account or self.expense) or {}
		return (float(row.get("debit") or 0), float(row.get("credit") or 0))

	# --- what a reversal is -----------------------------------------------

	def test_reversal_mirrors_the_original_sides(self):
		original = frappe.get_doc("Journal Entry", self.book(100.0))
		reversal = frappe.get_doc("Journal Entry", reverse_entry(original.name, REASON))

		self.assertEqual(len(reversal.accounts), len(original.accounts))
		for before, after in zip(original.accounts, reversal.accounts, strict=True):
			self.assertEqual(before.account, after.account)
			self.assertEqual(before.debit_in_account_currency, after.credit_in_account_currency)
			self.assertEqual(before.credit_in_account_currency, after.debit_in_account_currency)

	def test_reversal_is_posted_and_carries_its_reason(self):
		original_name = self.book(100.0)
		reversal = frappe.get_doc("Journal Entry", reverse_entry(original_name, REASON))

		self.assertEqual(reversal.docstatus, 1)
		self.assertEqual(reversal.general_reversal_of, original_name)
		self.assertEqual(reversal.reversal_reason, REASON)
		self.assertIn(REVERSAL_REMARK, reversal.user_remark)
		self.assertIn(REASON, reversal.user_remark)

	def test_the_original_points_back_at_its_reversal(self):
		original_name = self.book(100.0)
		reversal_name = reverse_entry(original_name, REASON)

		original = frappe.get_doc("Journal Entry", original_name)
		self.assertEqual(original.general_reversal_by, reversal_name)

	def test_reversal_is_dated_today_by_default(self):
		original_name = self.book(100.0, on=add_days(nowdate(), -40))
		reversal = frappe.get_doc("Journal Entry", reverse_entry(original_name, REASON))

		self.assertEqual(str(reversal.posting_date), nowdate())

	def test_reversal_can_be_dated_explicitly(self):
		original_name = self.book(100.0)
		day = add_days(nowdate(), -1)
		reversal = frappe.get_doc("Journal Entry", reverse_entry(original_name, REASON, day))

		self.assertEqual(str(reversal.posting_date), day)

	# --- what is refused --------------------------------------------------

	def test_a_reversal_needs_a_reason(self):
		"""Blank counts as no reason. A missing one never gets this far: the
		signature is typed, so Frappe refuses the call itself."""
		original_name = self.book(100.0)

		for empty in ("", "   ", "\n"):
			with self.assertRaises(frappe.ValidationError):
				reverse_entry(original_name, empty)

	def test_a_draft_cannot_be_reversed(self):
		draft = frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"company": TEST_COMPANY,
				"posting_date": self.day,
				"accounts": [
					{"account": self.expense, "debit_in_account_currency": 10},
					{"account": self.asset, "credit_in_account_currency": 10},
				],
			}
		).insert()

		with self.assertRaises(frappe.ValidationError):
			reverse_entry(draft.name, REASON)

	def test_an_entry_is_reversed_only_once(self):
		original_name = self.book(100.0)
		reverse_entry(original_name, REASON)

		with self.assertRaises(frappe.ValidationError):
			reverse_entry(original_name, REASON)

	def test_a_reversal_cannot_itself_be_reversed(self):
		"""A correction of a correction is a new booking, not a second undo."""
		reversal_name = reverse_entry(self.book(100.0), REASON)

		with self.assertRaises(frappe.ValidationError):
			reverse_entry(reversal_name, REASON)

	def test_a_reversal_without_a_reason_is_refused_on_the_document(self):
		"""Not only through the button: the rule lives on the document."""
		original_name = self.book(100.0)
		entry = frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"company": TEST_COMPANY,
				"posting_date": self.day,
				"general_reversal_of": original_name,
				"accounts": [
					{"account": self.expense, "credit_in_account_currency": 10},
					{"account": self.asset, "debit_in_account_currency": 10},
				],
			}
		)

		with self.assertRaises(frappe.ValidationError):
			entry.insert()

	# --- the turnover figures ---------------------------------------------

	def test_a_reversal_does_not_raise_the_turnover_figures(self):
		"""The point of a general reversal, and the reason it is not a counter posting.

		Booking 100 by mistake and correcting it must leave the account exactly
		where it was: not at 100 debit and 100 credit with a balance of nil.
		"""
		self.book(500.0)
		before = self.turnover()

		mistake = self.book(100.0)
		self.assertEqual(self.turnover(), (before[0] + 100.0, before[1]))

		reverse_entry(mistake, REASON)
		self.assertEqual(self.turnover(), before)

	def test_the_counter_account_is_netted_too(self):
		"""The whole entry is reversed, not only the account someone looked at."""
		before = self.turnover(self.asset)
		reverse_entry(self.book(100.0), REASON)

		self.assertEqual(self.turnover(self.asset), before)

	def test_an_ordinary_counter_posting_still_raises_the_figures(self):
		"""Only a marked reversal is read with a minus.

		Two independent bookings that happen to cancel each other out are two
		movements, and the figures have to say so.
		"""
		before = self.turnover()
		self.book(100.0)

		batch = frappe.get_doc(
			{
				"doctype": "Posting Batch",
				"company": TEST_COMPANY,
				"fiscal_year": fiscal_year_for(self.day),
				"from_date": self.day,
				"to_date": self.day,
				"entries": [
					{
						"posting_date": self.day,
						"amount": 100.0,
						"direction": "Credit",
						"account": self.expense,
						"against_account": self.asset,
					}
				],
			}
		).insert()
		batch.post()

		self.assertEqual(self.turnover(), (before[0] + 100.0, before[1] + 100.0))

	def test_the_balance_is_unchanged_either_way(self):
		"""Netting must not move the balance, only the turnover it is made of."""
		before = self.turnover()
		reverse_entry(self.book(100.0), REASON)
		after = self.turnover()

		self.assertEqual(after[0] - after[1], before[0] - before[1])

	def test_only_this_company_is_netted(self):
		"""The reversals of one company must not be subtracted in another."""
		other = frappe.get_all("Company", filters={"name": ("!=", TEST_COMPANY)}, limit=1, pluck="name")
		if not other:
			self.skipTest("No second company on this site")

		reverse_entry(self.book(100.0), REASON)
		totals = get_totals(LedgerScope(company=other[0], from_date=self.day, to_date=self.day))

		self.assertNotIn(self.expense, totals)
