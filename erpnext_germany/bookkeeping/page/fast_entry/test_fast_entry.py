# Copyright (c) 2026, ALYF GmbH and Contributors
# See license.txt

import frappe
from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice
from frappe.tests.utils import FrappeTestCase

from erpnext_germany.bookkeeping.doctype.posting_batch.test_posting_batch import (
	FROM_DATE,
	IN_PERIOD,
	TEST_COMPANY,
	TO_DATE,
	create_batch,
	entry,
	make_tax_key,
	party_account,
	posting_accounts,
	set_account_tax_key,
)
from erpnext_germany.bookkeeping.doctype.tax_key.test_tax_key import clear_tax_keys
from erpnext_germany.bookkeeping.fast_entry import (
	add_entry,
	get_balances,
	get_context,
	remove_entry,
	update_entry,
)
from erpnext_germany.bookkeeping.lockdown import clear_lockdown_cache
from erpnext_germany.bookkeeping.tests.test_party import customer

test_dependencies = ["Company"]


class TestFastEntry(FrappeTestCase):
	def setUp(self):
		frappe.db.delete("Ledger Lockdown")
		clear_lockdown_cache()
		clear_tax_keys()

		self.asset, self.tax_account = posting_accounts("Asset", 2)
		self.expense = posting_accounts("Expense", 1)[0]
		self.batch = create_batch(entries=[])

	def tearDown(self):
		frappe.db.delete("Ledger Lockdown")
		clear_lockdown_cache()
		clear_tax_keys()

	def line(self, **kwargs) -> dict:
		values = {
			"posting_date": IN_PERIOD,
			"amount": 119.0,
			"direction": "Debit",
			"account": self.expense,
			"against_account": self.asset,
		}
		values.update(kwargs)
		return values

	def input_tax_key(self) -> str:
		return make_tax_key(
			"VSt 19",
			"Input Tax",
			19.0,
			accounts=[{"company": TEST_COMPANY, "tax_account": self.tax_account}],
		)

	# --- context ----------------------------------------------------------

	def test_the_screen_gets_everything_it_needs_in_one_call(self):
		"""Nothing may have to be fetched again while typing."""
		context = get_context(self.batch.name)

		self.assertEqual(context["batch"]["name"], self.batch.name)
		self.assertEqual(context["batch"]["from_date"], FROM_DATE)
		self.assertEqual(context["batch"]["to_date"], TO_DATE)
		self.assertTrue(context["accounts"])
		self.assertIn("totals", context)
		self.assertEqual(context["totals"]["entry_count"], 0)

	def test_accounts_carry_number_and_name(self):
		"""An account has to be reachable by number as well as by name."""
		context = get_context(self.batch.name)
		account = next(a for a in context["accounts"] if a["name"] == self.expense)

		self.assertIn("number", account)
		self.assertIn("label", account)

	def test_group_accounts_are_not_offered(self):
		context = get_context(self.batch.name)
		offered = {account["name"] for account in context["accounts"]}
		groups = set(
			frappe.get_all("Account", filters={"company": TEST_COMPANY, "is_group": 1}, pluck="name")
		)

		self.assertFalse(offered & groups)

	def test_text_shortcuts_are_keyed_upper_case(self):
		frappe.get_doc({"doctype": "Booking Text Shortcut", "shortcut": "mi", "text": "Miete"}).insert()

		self.assertEqual(get_context(self.batch.name)["text_shortcuts"]["MI"], "Miete")

	# --- writing ----------------------------------------------------------

	def test_a_typed_line_reaches_the_batch(self):
		result = add_entry(self.batch.name, self.line(document_number="RE-1"))

		self.assertEqual(result["row"]["amount"], 119.0)
		self.assertEqual(result["row"]["document_number"], "RE-1")
		self.assertEqual(result["totals"]["entry_count"], 1)

		self.batch.reload()
		self.assertEqual(len(self.batch.entries), 1)

	def test_the_tax_comes_back_with_the_line(self):
		"""The typist sees the split without asking for it."""
		set_account_tax_key(self.expense, self.input_tax_key())

		result = add_entry(self.batch.name, self.line())

		self.assertEqual(result["row"]["net_amount"], 100.0)
		self.assertEqual(result["row"]["tax_amount"], 19.0)
		self.assertEqual(result["row"]["applied_tax_key"], "VSt 19")
		self.assertEqual(result["totals"]["total_tax_amount"], 19.0)

	def test_the_browser_cannot_dictate_the_tax(self):
		"""Derived amounts are recomputed, never taken from the client.

		Otherwise the ledger would depend on what some browser believed.
		"""
		set_account_tax_key(self.expense, self.input_tax_key())

		result = add_entry(
			self.batch.name,
			self.line(net_amount=1.0, tax_amount=999.0, tax_account=self.asset),
		)

		self.assertEqual(result["row"]["net_amount"], 100.0)
		self.assertEqual(result["row"]["tax_amount"], 19.0)
		self.assertEqual(result["row"]["tax_account"], self.tax_account)

	def test_a_line_is_validated_like_any_other(self):
		"""The fast screen is a faster way in, not a way around the rules."""
		self.assertRaises(
			frappe.ValidationError,
			add_entry,
			self.batch.name,
			self.line(posting_date="2026-07-01"),
		)

	def test_a_line_can_be_corrected(self):
		created = add_entry(self.batch.name, self.line())["row"]

		result = update_entry(self.batch.name, created["name"], self.line(amount=200.0))

		self.assertEqual(result["row"]["amount"], 200.0)
		self.assertEqual(result["totals"]["total_amount"], 200.0)

	def test_a_line_can_be_removed(self):
		created = add_entry(self.batch.name, self.line())["row"]

		result = remove_entry(self.batch.name, created["name"])

		self.assertEqual(result["totals"]["entry_count"], 0)

	def test_a_line_that_is_gone_cannot_be_corrected(self):
		self.assertRaises(
			frappe.ValidationError, update_entry, self.batch.name, "does-not-exist", self.line()
		)

	def test_a_posted_batch_takes_no_more_lines(self):
		"""A posted batch is history, whichever screen asks."""
		batch = create_batch(entries=[entry()])
		batch.post()

		self.assertRaises(frappe.ValidationError, add_entry, batch.name, self.line())

	def test_the_json_a_browser_sends_is_accepted(self):
		"""frappe.xcall hands dictionaries over as JSON strings."""
		result = add_entry(self.batch.name, frappe.as_json(self.line()))

		self.assertEqual(result["row"]["amount"], 119.0)


class TestAccountBalances(FrappeTestCase):
	"""The balance is what tells a typist the account number was the right one.

	Measured as a change rather than as an absolute: the test site shares its
	accounts between tests, so what this endpoint owes anybody is that a
	posting moves the figure by what was posted -- not that any account starts
	the day at nought.
	"""

	def setUp(self):
		frappe.db.delete("Ledger Lockdown")
		clear_lockdown_cache()
		clear_tax_keys()

		self.asset, self.other = posting_accounts("Asset", 2)
		self.batch = create_batch(entries=[])

	def balance(self, account) -> float:
		return get_balances(self.batch.name, [account])[account]

	def test_every_account_asked_about_gets_a_figure(self):
		"""Nought rather than nothing, so the caller never has to tell
		"no movement" from "not asked for"."""
		balances = get_balances(self.batch.name, [self.asset, self.other])

		self.assertEqual(sorted(balances), sorted([self.asset, self.other]))
		for figure in balances.values():
			self.assertIsInstance(figure, float)

	def test_a_posted_batch_moves_the_balance(self):
		before_asset = self.balance(self.asset)
		before_other = self.balance(self.other)

		batch = create_batch(
			entries=[entry(amount=400.0, direction="Debit", account=self.asset, against_account=self.other)]
		)
		batch.post()

		self.assertEqual(self.balance(self.asset) - before_asset, 400.0)
		self.assertEqual(self.balance(self.other) - before_other, -400.0)

	def test_a_credit_posting_moves_the_balance_the_other_way(self):
		"""The screen turns the sign into Soll or Haben. The server stays with
		debit minus credit, which is the one reading every evaluation uses."""
		before = self.balance(self.asset)

		batch = create_batch(
			entries=[entry(amount=250.0, direction="Credit", account=self.asset, against_account=self.other)]
		)
		batch.post()

		self.assertEqual(self.balance(self.asset) - before, -250.0)

	def test_an_unposted_batch_is_not_in_the_balance(self):
		"""What is being typed is not yet in the books, and the balance being
		added to is the one without it."""
		before = self.balance(self.asset)

		create_batch(
			entries=[entry(amount=900.0, direction="Debit", account=self.asset, against_account=self.other)]
		)

		self.assertEqual(self.balance(self.asset), before)

	def test_asking_for_nothing_returns_nothing(self):
		self.assertEqual(get_balances(self.batch.name, []), {})
		self.assertEqual(get_balances(self.batch.name, [""]), {})

	def test_accounts_arrive_as_json_from_the_browser(self):
		self.assertEqual(
			sorted(get_balances(self.batch.name, frappe.as_json([self.asset]))),
			[self.asset],
		)


class TestPersonalAccountsOnTheScreen(FrappeTestCase):
	"""Booking against a tenant is most of what a property manager books.

	The screen could not do it at all until it carried the person: a line on a
	receivable account needs a party, and a party needs the type that Frappe
	checks before any code of ours runs.
	"""

	def setUp(self):
		self.bank = posting_accounts("Asset", 1)[0]
		self.expense = posting_accounts("Expense", 1)[0]
		self.debtors = party_account("Receivable")
		self.customer = customer()
		self.batch = create_batch(entries=[])

	def line(self, **kwargs) -> dict:
		values = {
			"posting_date": IN_PERIOD,
			"amount": 100.0,
			"direction": "Credit",
			"account": self.debtors,
			"against_account": self.bank,
			"party": self.customer,
		}
		values.update(kwargs)
		return values

	def open_invoice(self) -> str:
		return create_sales_invoice(
			customer=self.customer, debit_to=self.debtors, posting_date=IN_PERIOD
		).name

	def test_a_line_against_a_person_can_be_typed(self):
		row = add_entry(self.batch.name, self.line())["row"]

		self.assertEqual(row["party"], self.customer)
		self.assertEqual(row["party_type"], "Customer")
		self.assertEqual(row["party_account"], self.debtors)

	def test_a_settlement_can_be_typed(self):
		invoice = self.open_invoice()

		row = add_entry(self.batch.name, self.line(reference_name=invoice))["row"]

		self.assertEqual(row["reference_name"], invoice)
		self.assertEqual(row["reference_type"], "Sales Invoice")

	def test_the_screen_never_sends_the_types(self):
		"""They follow from the accounts, so the browser is not asked for them
		and could not talk the ledger into a different answer if it tried."""
		row = add_entry(self.batch.name, self.line(party_type="Supplier"))["row"]

		self.assertEqual(row["party_type"], "Customer")

	def test_a_person_without_a_personal_account_is_refused(self):
		self.assertRaises(
			frappe.ValidationError,
			add_entry,
			self.batch.name,
			self.line(account=self.expense, against_account=self.bank),
		)

	def test_a_correction_can_take_the_open_item_back_off(self):
		"""A field the screen sends empty has to clear, or a wrong settlement
		could never be undone from here."""
		invoice = self.open_invoice()
		row = add_entry(self.batch.name, self.line(reference_name=invoice))["row"]

		corrected = update_entry(self.batch.name, row["name"], self.line(reference_name=""))["row"]

		self.assertFalse(corrected["reference_name"])
		self.assertFalse(corrected["reference_type"])

	def test_the_screen_is_told_who_can_stand_on_a_line(self):
		context = get_context(self.batch.name)

		parties = {party["name"]: party for party in context["parties"]}
		self.assertIn(self.customer, parties)
		self.assertEqual(parties[self.customer]["party_type"], "Customer")

	def test_the_screen_is_told_which_invoices_are_open(self):
		invoice = self.open_invoice()

		context = get_context(self.batch.name)

		offered = {item["name"]: item for item in context["open_items"]}
		self.assertIn(invoice, offered)
		self.assertEqual(offered[invoice]["party"], self.customer)
		self.assertEqual(offered[invoice]["party_type"], "Customer")

	def test_an_account_says_which_kind_of_person_it_implies(self):
		"""The screen has to know before it can offer anybody."""
		by_name = {account["name"]: account for account in get_context(self.batch.name)["accounts"]}

		self.assertEqual(by_name[self.debtors]["party_type"], "Customer")
		self.assertIsNone(by_name[self.bank]["party_type"])
