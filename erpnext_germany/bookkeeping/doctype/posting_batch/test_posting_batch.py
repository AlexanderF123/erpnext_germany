# Copyright (c) 2026, ALYF GmbH and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from erpnext_germany.bookkeeping.lockdown import clear_lockdown_cache

TEST_COMPANY = "_Test Company"
DEBIT_ACCOUNT = "_Test Bank - _TC"
CREDIT_ACCOUNT = "_Test Cash - _TC"


def create_batch(entries=None, **kwargs) -> "frappe.Document":
	doc = frappe.get_doc(
		{
			"doctype": "Posting Batch",
			"company": TEST_COMPANY,
			"fiscal_year": frappe.defaults.get_user_default("fiscal_year"),
			"from_date": "2026-06-01",
			"to_date": "2026-06-30",
			"entries": entries
			if entries is not None
			else [
				{
					"posting_date": "2026-06-15",
					"amount": 119.0,
					"direction": "Debit",
					"account": DEBIT_ACCOUNT,
					"against_account": CREDIT_ACCOUNT,
					"document_number": "RE-2026-0001",
					"remark": "Test",
				}
			],
			**kwargs,
		}
	)
	doc.insert()
	return doc


class TestPostingBatch(FrappeTestCase):
	def setUp(self):
		# frappe.db.delete on purpose: a lockdown cannot be removed through the
		# document lifecycle by design, so test isolation has to go past it.
		frappe.db.delete("Ledger Lockdown")
		clear_lockdown_cache()

	def tearDown(self):
		frappe.db.delete("Ledger Lockdown")
		clear_lockdown_cache()

	def test_totals_are_summed(self):
		batch = create_batch()

		self.assertEqual(batch.total_debit, 119.0)
		self.assertEqual(batch.total_credit, 0.0)
		self.assertEqual(batch.entry_count, 1)

	def test_entry_outside_the_period_is_rejected(self):
		self.assertRaises(
			frappe.ValidationError,
			create_batch,
			entries=[
				{
					"posting_date": "2026-07-01",
					"amount": 10.0,
					"direction": "Debit",
					"account": DEBIT_ACCOUNT,
					"against_account": CREDIT_ACCOUNT,
				}
			],
		)

	def test_same_account_on_both_sides_is_rejected(self):
		self.assertRaises(
			frappe.ValidationError,
			create_batch,
			entries=[
				{
					"posting_date": "2026-06-15",
					"amount": 10.0,
					"direction": "Debit",
					"account": DEBIT_ACCOUNT,
					"against_account": DEBIT_ACCOUNT,
				}
			],
		)

	def test_non_positive_amount_is_rejected(self):
		"""A correction is a general reversal, not a minus sign."""
		self.assertRaises(
			frappe.ValidationError,
			create_batch,
			entries=[
				{
					"posting_date": "2026-06-15",
					"amount": -10.0,
					"direction": "Debit",
					"account": DEBIT_ACCOUNT,
					"against_account": CREDIT_ACCOUNT,
				}
			],
		)

	def test_posting_creates_a_balanced_journal_entry(self):
		batch = create_batch()

		batch.post()
		batch.reload()

		self.assertEqual(batch.status, "Posted")
		self.assertEqual(batch.posted_by, frappe.session.user)

		journal_entry = frappe.get_doc("Journal Entry", batch.entries[0].journal_entry)
		self.assertEqual(journal_entry.docstatus, 1)
		self.assertEqual(journal_entry.total_debit, 119.0)
		self.assertEqual(journal_entry.total_credit, 119.0)
		self.assertEqual(journal_entry.bill_no, "RE-2026-0001")

		sides = {row.account: (row.debit, row.credit) for row in journal_entry.accounts}
		self.assertEqual(sides[DEBIT_ACCOUNT], (119.0, 0.0))
		self.assertEqual(sides[CREDIT_ACCOUNT], (0.0, 119.0))

	def test_credit_direction_flips_both_sides(self):
		batch = create_batch(
			entries=[
				{
					"posting_date": "2026-06-15",
					"amount": 50.0,
					"direction": "Credit",
					"account": DEBIT_ACCOUNT,
					"against_account": CREDIT_ACCOUNT,
				}
			]
		)

		batch.post()
		batch.reload()

		journal_entry = frappe.get_doc("Journal Entry", batch.entries[0].journal_entry)
		sides = {row.account: (row.debit, row.credit) for row in journal_entry.accounts}
		self.assertEqual(sides[DEBIT_ACCOUNT], (0.0, 50.0))
		self.assertEqual(sides[CREDIT_ACCOUNT], (50.0, 0.0))

	def test_posted_batch_cannot_be_changed(self):
		batch = create_batch()
		batch.post()
		batch.reload()

		batch.remarks = "after the fact"
		self.assertRaises(frappe.ValidationError, batch.save)

	def test_posted_batch_cannot_be_posted_twice(self):
		batch = create_batch()
		batch.post()
		batch.reload()

		self.assertRaises(frappe.ValidationError, batch.post)

	def test_posted_batch_cannot_be_deleted(self):
		batch = create_batch()
		batch.post()
		batch.reload()

		self.assertRaises(frappe.ValidationError, batch.delete)

	def test_posting_into_a_locked_period_is_refused(self):
		batch = create_batch()
		frappe.get_doc(
			{"doctype": "Ledger Lockdown", "company": TEST_COMPANY, "locked_up_to": "2026-06-30"}
		).insert()
		clear_lockdown_cache()

		self.assertRaises(frappe.ValidationError, batch.post)

		batch.reload()
		self.assertEqual(batch.status, "Open")
		self.assertIsNone(batch.entries[0].journal_entry)
