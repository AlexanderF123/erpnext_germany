# Copyright (c) 2026, ALYF GmbH and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import nowdate

from erpnext_germany.bookkeeping.account_search import account_label, get_accounts, get_usage
from erpnext_germany.bookkeeping.doctype.posting_batch.test_posting_batch import (
	TEST_COMPANY,
	fiscal_year_for,
	posting_accounts,
)
from erpnext_germany.bookkeeping.lockdown import clear_lockdown_cache

test_dependencies = ["Company"]


def set_label(account: str, label: str | None):
	doc = frappe.get_doc("Account", account)
	doc.account_label = label
	doc.save()
	frappe.clear_document_cache("Account", account)


class TestAccountSearch(FrappeTestCase):
	def setUp(self):
		frappe.db.delete("Ledger Lockdown")
		clear_lockdown_cache()

		self.first, self.second = posting_accounts("Expense", 2)
		self.asset = posting_accounts("Asset", 1)[0]
		set_label(self.first, None)
		set_label(self.second, None)

	def tearDown(self):
		set_label(self.first, None)
		set_label(self.second, None)
		frappe.db.delete("Ledger Lockdown")
		clear_lockdown_cache()

	def book(self, account: str, times: int):
		"""Put real ledger entries behind an account, on today's books."""
		today = nowdate()
		batch = frappe.get_doc(
			{
				"doctype": "Posting Batch",
				"company": TEST_COMPANY,
				"fiscal_year": fiscal_year_for(today),
				"from_date": today,
				"to_date": today,
				"entries": [
					{
						"posting_date": today,
						"amount": 10.0,
						"direction": "Debit",
						"account": account,
						"against_account": self.asset,
					}
					for _ in range(times)
				],
			}
		).insert()
		batch.post()

	def accounts_by_name(self) -> dict:
		return {row["name"]: row for row in get_accounts(TEST_COMPANY)}

	# --- what the list carries -------------------------------------------

	def test_every_account_carries_number_and_label(self):
		row = self.accounts_by_name()[self.first]

		self.assertIn("number", row)
		self.assertIn("label", row)
		self.assertIn("tax_key", row)

	def test_the_company_label_wins_over_the_account_name(self):
		"""A company may call 4830 whatever it likes without renaming the chart."""
		set_label(self.first, "Hausmeister")

		self.assertEqual(self.accounts_by_name()[self.first]["label"], "Hausmeister")
		self.assertEqual(account_label(self.first), "Hausmeister")

	def test_without_a_label_the_account_name_stands(self):
		account_name = frappe.db.get_value("Account", self.first, "account_name")

		self.assertEqual(self.accounts_by_name()[self.first]["label"], account_name)
		self.assertEqual(account_label(self.first), account_name)

	def test_group_accounts_are_left_out(self):
		"""They cannot be booked to, so offering them only costs a correction."""
		groups = set(
			frappe.get_all("Account", filters={"company": TEST_COMPANY, "is_group": 1}, pluck="name")
		)

		self.assertFalse(set(self.accounts_by_name()) & groups)

	def test_accounts_of_another_company_are_left_out(self):
		other = frappe.get_all(
			"Account", filters={"company": "_Test Company 2", "is_group": 0}, pluck="name", limit=1
		)[0]

		self.assertNotIn(other, self.accounts_by_name())

	# --- ordering ---------------------------------------------------------

	def test_recently_used_accounts_come_first(self):
		"""The account being looked for is usually one of a handful."""
		self.book(self.second, times=3)

		order = [row["name"] for row in get_accounts(TEST_COMPANY)]

		self.assertEqual(order[0], self.second)
		self.assertLess(order.index(self.second), order.index(self.first))

	def test_usage_counts_and_dates_the_postings(self):
		self.book(self.second, times=2)

		usage = get_usage(TEST_COMPANY)

		self.assertEqual(usage[self.second]["uses"], 2)
		self.assertEqual(usage[self.second]["last_used"], nowdate())

	def test_postings_outside_the_window_do_not_count(self):
		"""What was booked last year says nothing about what is booked today."""
		self.book(self.second, times=1)

		usage = get_usage(TEST_COMPANY, days=0)
		recent = get_usage(TEST_COMPANY, days=90)

		self.assertNotIn(self.second, usage)
		self.assertIn(self.second, recent)

	def test_an_unused_account_still_appears(self):
		"""Ordering must never hide an account, only rank it."""
		self.book(self.second, times=1)

		self.assertIn(self.first, self.accounts_by_name())

	def test_unused_accounts_are_ordered_by_number(self):
		rows = [row for row in get_accounts(TEST_COMPANY) if not row["uses"]]
		numbers = [row["number"] for row in rows if row["number"]]

		self.assertEqual(numbers, sorted(numbers))
