# Copyright (c) 2026, ALYF GmbH and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

from erpnext_germany.bookkeeping import month_end
from erpnext_germany.bookkeeping.doctype.posting_batch.test_posting_batch import (
	TEST_COMPANY,
	fiscal_year_for,
	posting_accounts,
)
from erpnext_germany.bookkeeping.doctype.tax_key.test_tax_key import clear_tax_keys
from erpnext_germany.bookkeeping.lockdown import clear_lockdown_cache

test_dependencies = ["Company"]


def ensure_account(number: str, label: str, root_type: str, **kwargs) -> str:
	"""An account of our own, created once and reused. Posting commits."""
	existing = frappe.get_all(
		"Account", filters={"company": TEST_COMPANY, "account_number": number}, pluck="name"
	)
	if existing:
		name = existing[0]
		if kwargs:
			account = frappe.get_doc("Account", name)
			account.update(kwargs)
			account.save()
		return name

	parent = frappe.get_all(
		"Account",
		filters={"company": TEST_COMPANY, "is_group": 1, "root_type": root_type},
		pluck="name",
		order_by="lft asc",
		limit=1,
	)[0]

	return (
		frappe.get_doc(
			{
				"doctype": "Account",
				"company": TEST_COMPANY,
				"account_name": label,
				"account_number": number,
				"parent_account": parent,
				"root_type": root_type,
				"is_group": 0,
				**kwargs,
			}
		)
		.insert()
		.name
	)


def disable(account: str, disabled: int):
	doc = frappe.get_doc("Account", account)
	doc.disabled = disabled
	doc.save()
	frappe.clear_document_cache("Account", account)


class TestMonthEndChecks(FrappeTestCase):
	def setUp(self):
		# frappe.db.delete on purpose: a lockdown cannot be removed through the
		# document lifecycle by design, so test isolation has to go past it.
		frappe.db.delete("Ledger Lockdown")
		clear_lockdown_cache()
		clear_tax_keys()

		self.expense = ensure_account("91100", "Monatsabschluss Aufwand", "Expense")
		self.bank = posting_accounts("Asset", 1)[0]
		self.today = nowdate()

	def tearDown(self):
		frappe.db.delete("Ledger Lockdown")
		clear_lockdown_cache()
		clear_tax_keys()

	# --- helpers ----------------------------------------------------------

	def book(self, account: str, amount: float, direction: str = "Debit", on=None, **kwargs) -> str:
		day = on or self.today
		entry = {
			"posting_date": day,
			"amount": amount,
			"direction": direction,
			"account": account,
			"against_account": self.bank,
		}
		entry.update(kwargs)
		batch = frappe.get_doc(
			{
				"doctype": "Posting Batch",
				"company": TEST_COMPANY,
				"fiscal_year": fiscal_year_for(day),
				"from_date": day,
				"to_date": day,
				"entries": [entry],
			}
		).insert()
		batch.post()
		return batch.entries[0].journal_entry

	def findings_of(self, name: str, from_date=None, to_date=None):
		return month_end.get_checks()[name](TEST_COMPANY, from_date or self.today, to_date or self.today)

	# --- the checks -------------------------------------------------------

	def test_every_check_runs_and_is_named(self):
		"""A check without a title would show up as a fieldname on the sheet."""
		results = month_end.run_checks(TEST_COMPANY, self.today, self.today)
		titles = month_end.get_titles()

		self.assertEqual(set(results), set(month_end.get_checks()))
		self.assertEqual(set(results), set(titles))
		self.assertTrue(all(titles.values()))

	def test_a_balance_left_on_a_clearing_account_is_reported(self):
		clearing = ensure_account("91200", "Verrechnung", "Asset", account_type="Temporary")
		before = len(self.findings_of("clearing_accounts"))
		self.book(clearing, 250.0)
		findings = self.findings_of("clearing_accounts")

		self.assertEqual(len(findings), before + 1)
		self.assertEqual(findings[-1].account, clearing)
		self.assertEqual(findings[-1].amount, 250.0)

	def test_a_clearing_account_that_was_cleared_is_not_reported(self):
		"""What matters is what is still sitting there, not what moved through."""
		clearing = ensure_account("91300", "Verrechnung Zwei", "Asset", account_type="Temporary")
		self.book(clearing, 250.0)
		self.book(clearing, 250.0, direction="Credit")

		self.assertNotIn(clearing, [finding.account for finding in self.findings_of("clearing_accounts")])

	def test_a_posting_to_a_disabled_account_is_reported(self):
		"""An account is disabled to stop it being used. A posting says otherwise."""
		account = ensure_account("91400", "Gesperrt", "Expense")
		voucher = self.book(account, 100.0)
		disable(account, 1)

		try:
			vouchers = [finding.voucher_no for finding in self.findings_of("disabled_accounts")]
			self.assertIn(voucher, vouchers)
		finally:
			disable(account, 0)

	def test_a_voucher_without_a_document_is_reported(self):
		"""Keine Buchung ohne Beleg."""
		voucher = self.book(self.expense, 100.0)

		findings = self.findings_of("vouchers_without_document")
		self.assertIn(voucher, [finding.voucher_no for finding in findings])

	def test_a_voucher_with_a_document_is_not_reported(self):
		voucher = self.book(self.expense, 100.0)
		frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "beleg.txt",
				"attached_to_doctype": "Journal Entry",
				"attached_to_name": voucher,
				"content": "Beleg",
			}
		).insert()

		findings = self.findings_of("vouchers_without_document")
		self.assertNotIn(voucher, [finding.voucher_no for finding in findings])

	# --- the tax verification ---------------------------------------------

	def test_a_correctly_taxed_month_verifies(self):
		"""The check every practice runs before a return goes out."""
		self.taxed_account("VSt 19 ME")
		self.book(self.taxed, 1190.0)

		accounts = [finding.account for finding in self.findings_of("tax_verification")]
		self.assertNotIn(self.tax_account, accounts)

	def test_tax_booked_past_the_account_shows_up_as_a_deviation(self):
		"""Booked straight to the tax account, so the turnover no longer explains it.

		Measured as a change rather than as an absolute: posting commits, so
		what earlier tests booked to this account is still there.
		"""
		self.taxed_account("VSt 19 MF")
		before = self.deviation_on_tax_account()
		self.book(self.tax_account, 500.0)

		self.assertEqual(self.deviation_on_tax_account(), before + 500.0)

	def deviation_on_tax_account(self) -> float:
		findings = {finding.account: finding for finding in self.findings_of("tax_verification")}
		finding = findings.get(self.tax_account)
		return finding.amount if finding else 0.0

	def test_a_deviation_names_the_accounts_that_caused_it(self):
		""" "1576 is 500 out" is not something anyone can act on by itself."""
		self.taxed_account("VSt 19 MG")
		self.book(self.tax_account, 500.0)

		finding = next(f for f in self.findings_of("tax_verification") if f.account == self.tax_account)
		self.assertIn(self.taxed, finding.detail)

	def taxed_account(self, key_name: str):
		"""An expense account whose bookings derive 19 % input tax."""
		self.tax_account = ensure_account("91500", "Vorsteuer Test", "Asset")
		self.taxed = ensure_account("91600", "Aufwand mit Steuer", "Expense")

		key = frappe.get_doc(
			{
				"doctype": "Tax Key",
				"tax_key_name": key_name,
				"key_number": str(abs(hash(key_name)) % 10000),
				"effect": "Input Tax",
				"rate": 19.0,
				"accounts": [{"company": TEST_COMPANY, "tax_account": self.tax_account}],
			}
		).insert()

		account = frappe.get_doc("Account", self.taxed)
		account.tax_key = key.name
		account.save()
		frappe.clear_document_cache("Account", self.taxed)

	# --- keeping the result -----------------------------------------------

	def test_the_result_is_filed_with_the_lockdown_that_closes_the_period(self):
		"""What an auditor asks later is what the people who closed it saw."""
		self.book(self.expense, 100.0)
		lockdown = frappe.get_doc(
			{"doctype": "Ledger Lockdown", "company": TEST_COMPANY, "locked_up_to": self.today}
		).insert()
		clear_lockdown_cache()

		files = frappe.get_all(
			"File",
			filters={"attached_to_doctype": "Ledger Lockdown", "attached_to_name": lockdown.name},
			pluck="file_name",
		)
		self.assertEqual(len(files), 1)
		self.assertTrue(files[0].startswith("Pruefliste"))

	def test_filing_by_hand_needs_a_lockdown_to_file_against(self):
		with self.assertRaises(frappe.ValidationError):
			month_end.archive(TEST_COMPANY, self.today, self.today)

	def test_the_period_a_lockdown_closes_starts_after_the_previous_one(self):
		"""So the checklist covers what is newly closed, not the whole year."""
		first = add_days(self.today, -40)
		frappe.get_doc(
			{"doctype": "Ledger Lockdown", "company": TEST_COMPANY, "locked_up_to": first}
		).insert()
		clear_lockdown_cache()
		second = frappe.get_doc(
			{"doctype": "Ledger Lockdown", "company": TEST_COMPANY, "locked_up_to": self.today}
		).insert()

		self.assertEqual(str(month_end.period_start(second)), add_days(first, 1))

	def test_the_result_reads_as_a_page(self):
		results = month_end.run_checks(TEST_COMPANY, self.today, self.today)
		page = month_end.render(TEST_COMPANY, self.today, self.today, results)

		self.assertIn(TEST_COMPANY, page)
		for title in month_end.get_titles().values():
			self.assertIn(title, page)
