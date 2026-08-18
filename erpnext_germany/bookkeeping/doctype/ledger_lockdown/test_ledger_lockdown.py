# Copyright (c) 2026, ALYF GmbH and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from erpnext_germany.bookkeeping.lockdown import clear_lockdown_cache, get_locked_up_to

test_dependencies = ["Company"]

TEST_COMPANY = "_Test Company"


def create_lockdown(locked_up_to: str, company: str = TEST_COMPANY) -> "frappe.Document":
	doc = frappe.get_doc(
		{
			"doctype": "Ledger Lockdown",
			"company": company,
			"locked_up_to": locked_up_to,
		}
	)
	doc.insert()
	return doc


class TestLedgerLockdown(FrappeTestCase):
	def setUp(self):
		# frappe.db.delete on purpose: a lockdown cannot be removed through the
		# document lifecycle by design, so test isolation has to go past it.
		frappe.db.delete("Ledger Lockdown")
		clear_lockdown_cache()

	def tearDown(self):
		frappe.db.delete("Ledger Lockdown")
		clear_lockdown_cache()

	def test_records_who_locked_and_when(self):
		lockdown = create_lockdown("2026-03-31")

		self.assertEqual(lockdown.locked_by, frappe.session.user)
		self.assertIsNotNone(lockdown.locked_on)

	def test_cannot_be_changed(self):
		lockdown = create_lockdown("2026-03-31")

		lockdown.remarks = "changed my mind"
		self.assertRaises(frappe.ValidationError, lockdown.save)

	def test_cannot_be_deleted(self):
		lockdown = create_lockdown("2026-03-31")

		self.assertRaises(frappe.ValidationError, lockdown.delete)

	def test_cannot_move_backwards(self):
		"""Reopening a closed period must not be possible by writing an earlier date."""
		create_lockdown("2026-03-31")

		self.assertRaises(frappe.ValidationError, create_lockdown, "2026-02-28")

	def test_cannot_repeat_the_same_date(self):
		create_lockdown("2026-03-31")

		self.assertRaises(frappe.ValidationError, create_lockdown, "2026-03-31")

	def test_can_move_forward(self):
		create_lockdown("2026-03-31")
		later = create_lockdown("2026-04-30")

		self.assertEqual(str(get_locked_up_to(TEST_COMPANY)), "2026-04-30")
		self.assertEqual(str(later.locked_up_to), "2026-04-30")

	def test_lockdown_is_per_company(self):
		"""Closing one company's books must not close another's."""
		create_lockdown("2026-03-31")

		self.assertIsNone(get_locked_up_to("_Test Company 2"))

	def test_no_lockdown_returns_none(self):
		self.assertIsNone(get_locked_up_to(TEST_COMPANY))
