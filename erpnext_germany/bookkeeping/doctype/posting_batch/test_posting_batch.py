# Copyright (c) 2026, ALYF GmbH and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from erpnext_germany.bookkeeping.lockdown import clear_lockdown_cache

TEST_COMPANY = "_Test Company"
OTHER_COMPANY = "_Test Company 2"
DEBIT_ACCOUNT = "_Test Bank - _TC"
CREDIT_ACCOUNT = "_Test Cash - _TC"


def entry(amount=119.0, direction="Debit", posting_date="2026-06-15", **kwargs):
	return {
		"posting_date": posting_date,
		"amount": amount,
		"direction": direction,
		"account": DEBIT_ACCOUNT,
		"against_account": CREDIT_ACCOUNT,
		**kwargs,
	}


def create_batch(entries=None, **kwargs) -> "frappe.Document":
	doc = frappe.get_doc(
		{
			"doctype": "Posting Batch",
			"company": TEST_COMPANY,
			"fiscal_year": frappe.defaults.get_user_default("fiscal_year"),
			"from_date": "2026-06-01",
			"to_date": "2026-06-30",
			"entries": entries if entries is not None else [entry(document_number="RE-2026-0001")],
			**kwargs,
		}
	)
	doc.insert()
	return doc


def lock(company=TEST_COMPANY, locked_up_to="2026-06-30"):
	frappe.get_doc({"doctype": "Ledger Lockdown", "company": company, "locked_up_to": locked_up_to}).insert()
	clear_lockdown_cache()


class TestPostingBatch(FrappeTestCase):
	def setUp(self):
		# frappe.db.delete on purpose: a lockdown cannot be removed through the
		# document lifecycle by design, so test isolation has to go past it.
		frappe.db.delete("Ledger Lockdown")
		clear_lockdown_cache()

	def tearDown(self):
		frappe.db.delete("Ledger Lockdown")
		clear_lockdown_cache()

	# --- control totals ---------------------------------------------------

	def test_control_totals_count_and_sum_every_entry(self):
		"""The control total is what a bookkeeper reconciles against.

		Both directions have to count towards the same total. An earlier version
		summed debit and credit into separate columns, which made a mixed batch
		look unbalanced when it was balanced by construction.
		"""
		batch = create_batch(
			entries=[
				entry(amount=119.0, direction="Debit"),
				entry(amount=500.0, direction="Credit"),
				entry(amount=42.5, direction="Debit"),
			]
		)

		self.assertEqual(batch.entry_count, 3)
		self.assertEqual(batch.total_amount, 661.5)

	def test_control_total_matches_the_posted_ledger(self):
		"""The batch total has to equal what actually reaches the books."""
		batch = create_batch(
			entries=[entry(amount=119.0, direction="Debit"), entry(amount=500.0, direction="Credit")]
		)

		batch.post()
		batch.reload()

		posted_debit = 0.0
		posted_credit = 0.0
		for row in batch.entries:
			journal_entry = frappe.get_doc("Journal Entry", row.journal_entry)
			posted_debit += journal_entry.total_debit
			posted_credit += journal_entry.total_credit

		self.assertEqual(posted_debit, batch.total_amount)
		self.assertEqual(posted_credit, batch.total_amount)

	# --- validation -------------------------------------------------------

	def test_entry_outside_the_period_is_rejected(self):
		self.assertRaises(frappe.ValidationError, create_batch, entries=[entry(posting_date="2026-07-01")])

	def test_same_account_on_both_sides_is_rejected(self):
		self.assertRaises(
			frappe.ValidationError, create_batch, entries=[entry(against_account=DEBIT_ACCOUNT)]
		)

	def test_non_positive_amount_is_rejected(self):
		"""A correction is a general reversal, not a minus sign."""
		self.assertRaises(frappe.ValidationError, create_batch, entries=[entry(amount=-10.0)])

	# --- posting ----------------------------------------------------------

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
		batch = create_batch(entries=[entry(amount=50.0, direction="Credit")])

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

	# --- lockdown ---------------------------------------------------------

	def test_posting_into_a_locked_period_is_refused(self):
		batch = create_batch()
		lock()

		self.assertRaises(frappe.ValidationError, batch.post)

		batch.reload()
		self.assertEqual(batch.status, "Open")
		self.assertIsNone(batch.entries[0].journal_entry)

	def test_one_locked_entry_stops_the_whole_batch(self):
		"""All or nothing: a batch must never end up half posted.

		The first entry is in an open period, the second is not. Neither may
		reach the ledger.
		"""
		batch = create_batch(entries=[entry(posting_date="2026-06-25"), entry(posting_date="2026-06-10")])
		lock(locked_up_to="2026-06-15")

		self.assertRaises(frappe.ValidationError, batch.post)

		batch.reload()
		self.assertEqual(batch.status, "Open")
		self.assertEqual([row.journal_entry for row in batch.entries], [None, None])
		self.assertEqual(
			frappe.db.count("Journal Entry", {"company": TEST_COMPANY, "posting_date": "2026-06-25"}),
			0,
		)

	def test_lockdown_boundary_is_inclusive(self):
		"""Locking up to 15 June closes the 15th and leaves the 16th open."""
		lock(locked_up_to="2026-06-15")

		on_the_date = create_batch(entries=[entry(posting_date="2026-06-15")])
		self.assertRaises(frappe.ValidationError, on_the_date.post)

		day_after = create_batch(entries=[entry(posting_date="2026-06-16")])
		day_after.post()
		day_after.reload()
		self.assertEqual(day_after.status, "Posted")

	def test_cancelling_a_posted_entry_in_a_locked_period_is_refused(self):
		"""The reversal path has to be closed too, not just direct posting.

		Cancelling would write reversal entries back into a closed period, which
		is exactly what a lockdown exists to prevent.
		"""
		batch = create_batch()
		batch.post()
		batch.reload()
		journal_entry = frappe.get_doc("Journal Entry", batch.entries[0].journal_entry)

		lock()

		self.assertRaises(frappe.ValidationError, journal_entry.cancel)

		journal_entry.reload()
		self.assertEqual(journal_entry.docstatus, 1)

	def test_another_companys_lockdown_does_not_block(self):
		"""Closing one company's books must not close another's."""
		lock(company=OTHER_COMPANY)

		batch = create_batch()
		batch.post()
		batch.reload()

		self.assertEqual(batch.status, "Posted")
