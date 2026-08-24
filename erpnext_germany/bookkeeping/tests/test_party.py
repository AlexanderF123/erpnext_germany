# Copyright (c) 2026, ALYF GmbH and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from erpnext_germany.bookkeeping.doctype.posting_batch.test_posting_batch import (
	TEST_COMPANY,
	create_batch,
	entry,
	party_account,
	posting_accounts,
)
from erpnext_germany.bookkeeping.party import derive_party, get_open_items

test_dependencies = ["Company", "Customer", "Supplier"]


class TestDeriveParty(FrappeTestCase):
	"""Which side of a line is a person follows from the accounts alone."""

	def setUp(self):
		self.bank = posting_accounts("Asset", 1)[0]
		self.expense = posting_accounts("Expense", 1)[0]
		self.debtors = party_account("Receivable")
		self.creditors = party_account("Payable")

	def test_two_ordinary_accounts_have_no_party(self):
		derived = derive_party(self.bank, self.expense)

		self.assertFalse(derived.wanted)
		self.assertIsNone(derived.party_type)

	def test_a_receivable_account_makes_it_a_customer(self):
		derived = derive_party(self.debtors, self.bank)

		self.assertTrue(derived.wanted)
		self.assertEqual(derived.account, self.debtors)
		self.assertEqual(derived.party_type, "Customer")
		self.assertEqual(derived.reference_type, "Sales Invoice")

	def test_a_payable_account_makes_it_a_supplier(self):
		derived = derive_party(self.bank, self.creditors)

		self.assertEqual(derived.account, self.creditors)
		self.assertEqual(derived.party_type, "Supplier")
		self.assertEqual(derived.reference_type, "Purchase Invoice")

	def test_the_side_does_not_matter(self):
		"""A personal account is a personal account, whichever column it stands in."""
		self.assertEqual(derive_party(self.debtors, self.bank).account, self.debtors)
		self.assertEqual(derive_party(self.bank, self.debtors).account, self.debtors)

	def test_two_personal_accounts_are_refused(self):
		"""Two people on one line is two bookings, and no single party field
		could describe it honestly."""
		self.assertRaises(frappe.ValidationError, derive_party, self.debtors, self.creditors)


class TestPartyOnTheLine(FrappeTestCase):
	"""What the batch does with it."""

	def setUp(self):
		self.bank = posting_accounts("Asset", 1)[0]
		self.expense = posting_accounts("Expense", 1)[0]
		self.debtors = party_account("Receivable")
		self.customer = frappe.get_all("Customer", pluck="name", limit=1)[0]

	def test_a_personal_account_without_a_party_is_refused(self):
		self.assertRaises(
			frappe.ValidationError,
			create_batch,
			entries=[entry(account=self.debtors, against_account=self.bank)],
		)

	def test_a_party_without_a_personal_account_is_dropped(self):
		"""Nobody to book against, so the person goes: keeping them would leave
		the ledger carrying a party that nothing points at."""
		batch = create_batch(
			entries=[
				entry(
					account=self.bank,
					against_account=self.expense,
					party_type="Customer",
					party=self.customer,
				)
			]
		)

		self.assertFalse(batch.entries[0].party)
		self.assertFalse(batch.entries[0].party_type)

	def test_the_line_records_whose_account_it_touches(self):
		batch = create_batch(
			entries=[
				entry(
					account=self.debtors,
					against_account=self.bank,
					party_type="Customer",
					party=self.customer,
				)
			]
		)
		line = batch.entries[0]

		self.assertEqual(line.party_account, self.debtors)
		self.assertEqual(line.party_type, "Customer")
		self.assertEqual(line.party, self.customer)

	def test_a_party_type_that_contradicts_the_account_is_refused(self):
		"""A receivable account is a customer. Saying supplier next to it is
		not a preference, it is a mistake."""
		self.assertRaises(
			frappe.ValidationError,
			create_batch,
			entries=[
				entry(
					account=self.debtors,
					against_account=self.bank,
					party_type="Supplier",
					party=self.customer,
				)
			],
		)

	def test_the_party_is_dropped_when_the_line_stops_touching_one(self):
		"""Otherwise the ledger would carry a party that nothing points at."""
		batch = create_batch(
			entries=[
				entry(
					account=self.debtors,
					against_account=self.bank,
					party_type="Customer",
					party=self.customer,
				)
			]
		)

		batch.entries[0].account = self.expense
		batch.save()

		self.assertFalse(batch.entries[0].party)
		self.assertFalse(batch.entries[0].party_account)

	def test_posting_puts_the_party_on_the_personal_row_only(self):
		batch = create_batch(
			entries=[
				entry(
					amount=300.0,
					account=self.debtors,
					against_account=self.bank,
					party_type="Customer",
					party=self.customer,
				)
			]
		)
		batch.post()

		journal_entry = frappe.get_doc("Journal Entry", batch.entries[0].journal_entry)
		by_account = {row.account: row for row in journal_entry.accounts}

		self.assertEqual(by_account[self.debtors].party_type, "Customer")
		self.assertEqual(by_account[self.debtors].party, self.customer)
		self.assertFalse(by_account[self.bank].party)


class TestOpenItems(FrappeTestCase):
	def setUp(self):
		self.bank = posting_accounts("Asset", 1)[0]
		self.debtors = party_account("Receivable")
		self.customer = frappe.get_all("Customer", pluck="name", limit=1)[0]

	def test_a_party_without_open_documents_has_no_open_items(self):
		items = get_open_items(TEST_COMPANY, "Customer", self.customer)

		for item in items:
			self.assertNotEqual(item["outstanding_amount"], 0)

	def test_an_unknown_party_type_has_none(self):
		self.assertEqual(get_open_items(TEST_COMPANY, "Employee", self.customer), [])

	def test_no_party_means_no_question(self):
		self.assertEqual(get_open_items(TEST_COMPANY, "Customer", ""), [])

	def test_an_open_item_that_does_not_exist_is_refused(self):
		self.assertRaises(
			frappe.ValidationError,
			create_batch,
			entries=[
				entry(
					account=self.debtors,
					against_account=self.bank,
					party_type="Customer",
					party=self.customer,
					reference_name="SINV-DOES-NOT-EXIST",
				)
			],
		)
