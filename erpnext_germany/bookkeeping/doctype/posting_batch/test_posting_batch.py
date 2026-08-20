# Copyright (c) 2026, ALYF GmbH and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from erpnext_germany.bookkeeping.doctype.tax_key.test_tax_key import clear_tax_keys
from erpnext_germany.bookkeeping.lockdown import clear_lockdown_cache

test_dependencies = ["Company"]

TEST_COMPANY = "_Test Company"
OTHER_COMPANY = "_Test Company 2"
FROM_DATE = "2026-06-01"
TO_DATE = "2026-06-30"
IN_PERIOD = "2026-06-15"


def posting_accounts(root_type: str, count: int = 1, company: str = TEST_COMPANY) -> list[str]:
	"""Return ledger accounts of the company that can be posted to directly.

	Resolved from the chart of accounts instead of hard-coded, so the tests do
	not depend on how a particular ERPNext version names its accounts.
	Receivable and payable accounts are excluded because they would require a
	party on every entry.
	"""
	accounts = frappe.get_all(
		"Account",
		filters={
			"company": company,
			"is_group": 0,
			"disabled": 0,
			"root_type": root_type,
			"account_type": ("not in", ("Receivable", "Payable")),
		},
		pluck="name",
		order_by="name asc",
		limit=count,
	)
	if len(accounts) < count:
		raise ValueError(f"Need {count} postable {root_type} accounts for {company}")

	return accounts


def posting_account(root_type: str, company: str = TEST_COMPANY) -> str:
	return posting_accounts(root_type, company=company)[0]


def fiscal_year_for(day: str) -> str:
	year = frappe.db.get_value(
		"Fiscal Year",
		{"year_start_date": ("<=", day), "year_end_date": (">=", day), "disabled": 0},
		"name",
	)
	if not year:
		raise ValueError(f"No fiscal year covers {day}")

	return year


def entry(amount=119.0, direction="Debit", posting_date=IN_PERIOD, **kwargs):
	row = {
		"posting_date": posting_date,
		"amount": amount,
		"direction": direction,
		"account": posting_account("Asset"),
		"against_account": posting_account("Expense"),
	}
	row.update(kwargs)
	return row


def create_batch(entries=None, **kwargs) -> "frappe.Document":
	doc = frappe.get_doc(
		{
			"doctype": "Posting Batch",
			"company": TEST_COMPANY,
			"fiscal_year": fiscal_year_for(FROM_DATE),
			"from_date": FROM_DATE,
			"to_date": TO_DATE,
			"entries": entries if entries is not None else [entry(document_number="RE-2026-0001")],
			**kwargs,
		}
	)
	doc.insert()
	return doc


def lock(company=TEST_COMPANY, locked_up_to=TO_DATE):
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
			frappe.ValidationError,
			create_batch,
			entries=[entry(against_account=posting_account("Asset"))],
		)

	def test_non_positive_amount_is_rejected(self):
		"""A correction is a general reversal, not a minus sign."""
		self.assertRaises(frappe.ValidationError, create_batch, entries=[entry(amount=-10.0)])

	def test_account_of_another_company_is_rejected(self):
		other_account = posting_account("Asset", OTHER_COMPANY)

		self.assertRaises(frappe.ValidationError, create_batch, entries=[entry(account=other_account)])

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
		self.assertEqual(sides[posting_account("Asset")], (119.0, 0.0))
		self.assertEqual(sides[posting_account("Expense")], (0.0, 119.0))

	def test_credit_direction_flips_both_sides(self):
		batch = create_batch(entries=[entry(amount=50.0, direction="Credit")])

		batch.post()
		batch.reload()

		journal_entry = frappe.get_doc("Journal Entry", batch.entries[0].journal_entry)
		sides = {row.account: (row.debit, row.credit) for row in journal_entry.accounts}
		self.assertEqual(sides[posting_account("Asset")], (0.0, 50.0))
		self.assertEqual(sides[posting_account("Expense")], (50.0, 0.0))

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


# --- tax derivation ------------------------------------------------------


def make_tax_key(name: str, effect: str, rate: float, accounts=None, **kwargs) -> str:
	doc = frappe.get_doc(
		{
			"doctype": "Tax Key",
			"tax_key_name": name,
			"key_number": str(abs(hash(name)) % 10**8),
			"effect": effect,
			"rate": rate,
			"accounts": accounts or [],
			**kwargs,
		}
	)
	doc.insert()
	return doc.name


def set_account_tax_key(account: str, key: str | None):
	doc = frappe.get_doc("Account", account)
	doc.tax_key = key
	doc.save()
	frappe.clear_document_cache("Account", account)


def sides_of(journal_entry) -> dict:
	return {row.account: (row.debit, row.credit) for row in journal_entry.accounts}


class TestPostingBatchTax(FrappeTestCase):
	"""The Automatikkonto principle: the tax follows from the account."""

	def setUp(self):
		frappe.db.delete("Ledger Lockdown")
		clear_lockdown_cache()
		clear_tax_keys()

		self.expense, self.other_expense = posting_accounts("Expense", 2)
		self.asset, self.input_tax, self.owed_tax = posting_accounts("Asset", 3)
		self.liability = posting_accounts("Liability", 1)[0]

	def tearDown(self):
		frappe.db.delete("Ledger Lockdown")
		clear_lockdown_cache()
		clear_tax_keys()

	def domestic_key(self, rate=19.0, name="VSt 19") -> str:
		return make_tax_key(
			name,
			"Input Tax",
			rate,
			accounts=[{"company": TEST_COMPANY, "tax_account": self.input_tax}],
		)

	def test_the_account_alone_derives_the_tax(self):
		"""Nobody types a tax amount. Booking to the account is enough."""
		set_account_tax_key(self.expense, self.domestic_key())

		batch = create_batch(entries=[entry(amount=119.0, account=self.expense, against_account=self.asset)])

		line = batch.entries[0]
		self.assertEqual(line.applied_tax_key, "VSt 19")
		self.assertIsNone(line.tax_key)
		self.assertEqual(line.net_amount, 100.0)
		self.assertEqual(line.tax_amount, 19.0)
		self.assertEqual(line.tax_account, self.input_tax)

	def test_a_key_on_the_line_overrides_the_account(self):
		"""The exception is typed on the line and stays visible afterwards."""
		set_account_tax_key(self.expense, self.domestic_key())
		reduced = self.domestic_key(rate=7.0, name="VSt 7")

		batch = create_batch(
			entries=[
				entry(amount=107.0, account=self.expense, against_account=self.asset, tax_key=reduced)
			]
		)

		line = batch.entries[0]
		self.assertEqual(line.tax_key, "VSt 7")
		self.assertEqual(line.applied_tax_key, "VSt 7")
		self.assertEqual(line.net_amount, 100.0)
		self.assertEqual(line.tax_amount, 7.0)

	def test_an_account_without_a_key_stays_untaxed(self):
		batch = create_batch(entries=[entry(amount=119.0)])

		line = batch.entries[0]
		self.assertIsNone(line.applied_tax_key)
		self.assertEqual(line.net_amount, 119.0)
		self.assertEqual(line.tax_amount, 0.0)
		self.assertIsNone(line.tax_account)

	def test_posting_books_net_tax_and_gross_to_three_accounts(self):
		"""The account keeps the net, the tax account takes the tax, the contra
		account settles the gross -- exactly how the invoice reads."""
		set_account_tax_key(self.expense, self.domestic_key())

		batch = create_batch(entries=[entry(amount=119.0, account=self.expense, against_account=self.asset)])
		batch.post()
		batch.reload()

		journal_entry = frappe.get_doc("Journal Entry", batch.entries[0].journal_entry)
		sides = sides_of(journal_entry)

		self.assertEqual(sides[self.expense], (100.0, 0.0))
		self.assertEqual(sides[self.input_tax], (19.0, 0.0))
		self.assertEqual(sides[self.asset], (0.0, 119.0))
		self.assertEqual(journal_entry.total_debit, journal_entry.total_credit)

	def test_reverse_charge_adds_an_offsetting_pair(self):
		"""§ 13b: the supplier bills net, so nothing extra passes to the contra
		account. The tax owed and the deductible input tax cancel each other."""
		key = make_tax_key(
			"RC 19",
			"Reverse Charge",
			19.0,
			accounts=[
				{
					"company": TEST_COMPANY,
					"tax_account": self.owed_tax,
					"deductible_tax_account": self.input_tax,
				}
			],
		)
		set_account_tax_key(self.expense, key)

		batch = create_batch(
			entries=[entry(amount=1000.0, account=self.expense, against_account=self.asset)]
		)
		self.assertEqual(batch.entries[0].net_amount, 1000.0)
		self.assertEqual(batch.entries[0].tax_amount, 190.0)

		batch.post()
		batch.reload()

		journal_entry = frappe.get_doc("Journal Entry", batch.entries[0].journal_entry)
		sides = sides_of(journal_entry)

		self.assertEqual(sides[self.expense], (1000.0, 0.0))
		self.assertEqual(sides[self.asset], (0.0, 1000.0))
		self.assertEqual(sides[self.owed_tax], (0.0, 190.0))
		self.assertEqual(sides[self.input_tax], (190.0, 0.0))
		self.assertEqual(journal_entry.total_debit, journal_entry.total_credit)

	def test_control_totals_separate_net_and_tax(self):
		set_account_tax_key(self.expense, self.domestic_key())

		batch = create_batch(
			entries=[
				entry(amount=119.0, account=self.expense, against_account=self.asset),
				entry(amount=238.0, account=self.expense, against_account=self.asset),
			]
		)

		self.assertEqual(batch.total_amount, 357.0)
		self.assertEqual(batch.total_net_amount, 300.0)
		self.assertEqual(batch.total_tax_amount, 57.0)

	# --- contradictions ---------------------------------------------------

	def test_a_key_that_does_not_apply_yet_is_refused(self):
		key = make_tax_key(
			"VSt 19 neu",
			"Input Tax",
			19.0,
			valid_from="2026-07-01",
			accounts=[{"company": TEST_COMPANY, "tax_account": self.input_tax}],
		)
		set_account_tax_key(self.expense, key)

		self.assertRaises(
			frappe.ValidationError,
			create_batch,
			entries=[entry(amount=119.0, account=self.expense, against_account=self.asset)],
		)

	def test_a_disabled_key_is_refused(self):
		key = make_tax_key(
			"VSt alt",
			"Input Tax",
			19.0,
			disabled=1,
			accounts=[{"company": TEST_COMPANY, "tax_account": self.input_tax}],
		)

		self.assertRaises(
			frappe.ValidationError,
			create_batch,
			entries=[entry(amount=119.0, account=self.expense, against_account=self.asset, tax_key=key)],
		)

	def test_a_key_without_an_account_for_this_company_is_refused(self):
		"""Deriving a tax with nowhere to book it would silently lose it."""
		key = make_tax_key("VSt ohne Konto", "Input Tax", 19.0)

		self.assertRaises(
			frappe.ValidationError,
			create_batch,
			entries=[entry(amount=119.0, account=self.expense, against_account=self.asset, tax_key=key)],
		)

	def test_a_tax_account_cannot_carry_a_key_itself(self):
		"""That would report the same tax twice."""
		key = self.domestic_key()

		self.assertRaises(
			frappe.ValidationError,
			create_batch,
			entries=[
				entry(amount=119.0, account=self.input_tax, against_account=self.asset, tax_key=key)
			],
		)

	def test_a_tax_free_key_carries_no_tax(self):
		key = make_tax_key("Steuerfrei", "Tax Free", 0.0)
		set_account_tax_key(self.expense, key)

		batch = create_batch(entries=[entry(amount=500.0, account=self.expense, against_account=self.asset)])

		line = batch.entries[0]
		self.assertEqual(line.net_amount, 500.0)
		self.assertEqual(line.tax_amount, 0.0)
		self.assertIsNone(line.tax_account)
