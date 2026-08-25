# Copyright (c) 2026, ALYF GmbH and Contributors
# See license.txt

import frappe
from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice
from frappe.tests.utils import FrappeTestCase

from erpnext_germany.bookkeeping.doctype.posting_batch.test_posting_batch import (
	IN_PERIOD,
	TEST_COMPANY,
	create_batch,
	entry,
	party_account,
	posting_accounts,
)
from erpnext_germany.bookkeeping.party import derive_party, get_open_items

test_dependencies = ["Company", "Customer", "Supplier"]


def customer() -> str:
	"""Somebody who is billed in the company's own currency.

	The test fixtures include customers who are not, and an invoice for one of
	those fails on the currency long before it can say anything about parties.
	"""
	names = frappe.get_all("Customer", filters={"default_currency": ("is", "not set")}, pluck="name", limit=1)
	return names[0]


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
		self.customer = customer()

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
		not a preference, it is a mistake.

		No party is named here on purpose. With one, Frappe would refuse the
		line first -- a customer is not found under Supplier -- and the test
		would pass without our rule ever running. The assertion quotes our own
		wording for the same reason.
		"""
		with self.assertRaises(frappe.ValidationError) as refused:
			create_batch(
				entries=[
					entry(
						account=self.debtors,
						against_account=self.bank,
						party_type="Supplier",
					)
				]
			)

		self.assertIn("implies Customer, not Supplier", str(refused.exception))

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
		self.creditors = party_account("Payable")
		self.customer = customer()

	def open_invoice(self) -> str:
		"""A posted invoice with money still owed on it.

		Made here rather than looked up. A test that skips when the site
		happens to carry no open invoice is a test that stops running exactly
		when the feature it covers starts mattering.
		"""
		return create_sales_invoice(
			customer=self.customer, debit_to=self.debtors, posting_date=IN_PERIOD
		).name

	def test_an_open_invoice_is_offered_to_its_party(self):
		invoice = self.open_invoice()

		offered = get_open_items(TEST_COMPANY, "Customer", self.customer)

		self.assertIn(invoice, [item["name"] for item in offered])
		for item in offered:
			self.assertNotEqual(item["outstanding_amount"], 0)

	def test_an_unknown_party_type_has_none(self):
		self.assertEqual(get_open_items(TEST_COMPANY, "Employee", self.customer), [])

	def test_no_party_means_no_question(self):
		self.assertEqual(get_open_items(TEST_COMPANY, "Customer", ""), [])

	def test_a_line_can_actually_carry_an_open_item(self):
		"""A settlement saves and keeps pointing at what it settles.

		Both types travel with their value, the way the form sends them. That
		is the whole contract: Frappe checks a dynamic link before it runs any
		hook of ours, so a `reference_name` whose `reference_type` was meant to
		be worked out later is refused by the framework with "Open Item Type
		must be set first", and no code of ours ever gets a say.
		"""
		invoice = self.open_invoice()

		batch = create_batch(
			entries=[
				entry(
					account=self.debtors,
					against_account=self.bank,
					direction="Credit",
					party_type="Customer",
					party=self.customer,
					reference_type="Sales Invoice",
					reference_name=invoice,
				)
			]
		)
		line = batch.entries[0]

		self.assertEqual(line.reference_name, invoice)
		self.assertEqual(line.reference_type, "Sales Invoice")

	def test_a_reference_type_that_contradicts_the_account_is_refused(self):
		"""A payable account settles a supplier's invoice, so a sales invoice
		next to it is a leftover from before the account was changed.

		The document itself exists, so Frappe is happy with the link and our
		rule is what has to catch it.
		"""
		invoice = self.open_invoice()

		with self.assertRaises(frappe.ValidationError) as refused:
			create_batch(
				entries=[
					entry(
						account=self.creditors,
						against_account=self.bank,
						party_type="Supplier",
						reference_type="Sales Invoice",
						reference_name=invoice,
					)
				]
			)

		self.assertIn("implies Purchase Invoice, not Sales Invoice", str(refused.exception))

	def test_the_open_item_goes_when_the_line_stops_touching_a_person(self):
		"""Otherwise the line would still claim to settle an invoice it no
		longer books against."""
		batch = create_batch(
			entries=[
				entry(
					account=self.debtors,
					against_account=self.bank,
					direction="Credit",
					party_type="Customer",
					party=self.customer,
					reference_type="Sales Invoice",
					reference_name=self.open_invoice(),
				)
			]
		)

		batch.entries[0].account = posting_accounts("Expense", 1)[0]
		batch.save()

		self.assertFalse(batch.entries[0].reference_name)
		self.assertFalse(batch.entries[0].reference_type)


class TestTheOpenItemIsTheRightOne(FrappeTestCase):
	"""ERPNext would take the reference and quietly settle nothing.

	A wrong open item is not a posting error anybody notices on the day. It is
	a dunning letter three weeks later, so each way of being wrong is refused
	by name.
	"""

	def setUp(self):
		self.bank = posting_accounts("Asset", 1)[0]
		self.debtors = party_account("Receivable")
		self.customer = customer()

	def settlement_of(self, invoice: str, party: str | None = None):
		return create_batch(
			entries=[
				entry(
					account=self.debtors,
					against_account=self.bank,
					direction="Credit",
					party_type="Customer",
					party=party or self.customer,
					reference_type="Sales Invoice",
					reference_name=invoice,
				)
			]
		)

	def invoice_for(self, customer: str, **kwargs) -> str:
		return create_sales_invoice(
			customer=customer, debit_to=self.debtors, posting_date=IN_PERIOD, **kwargs
		).name

	def test_a_draft_invoice_cannot_be_settled(self):
		"""Nothing is owed yet on a document that was never posted."""
		draft = self.invoice_for(self.customer, do_not_submit=True)

		with self.assertRaises(frappe.ValidationError) as refused:
			self.settlement_of(draft)

		self.assertIn("is not posted", str(refused.exception))

	def test_an_invoice_of_somebody_else_cannot_be_settled(self):
		"""The mistake that pays one tenant's rent off another's account."""
		other = frappe.get_all(
			"Customer",
			filters={"name": ("!=", self.customer), "default_currency": ("is", "not set")},
			pluck="name",
			limit=1,
		)[0]
		theirs = self.invoice_for(other)

		with self.assertRaises(frappe.ValidationError) as refused:
			self.settlement_of(theirs, party=self.customer)

		self.assertIn(self.customer, str(refused.exception))
