# Copyright (c) 2026, ALYF GmbH and Contributors
# See license.txt

import frappe
from frappe.desk.query_report import run
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Company"]

COMPANY = "_Test Company"
THIS_YEAR = "2026-06-15"
LAST_YEAR = "2025-06-15"


def ledger_account(label: str, root_type: str) -> str:
	"""Create a ledger account that belongs to this test alone.

	The report sums whatever sits on an account, so sharing accounts with other
	tests would make the expected figures depend on execution order. Dedicated
	accounts keep every assertion exact.
	"""
	name = f"{label} - _TC"
	if frappe.db.exists("Account", name):
		return name

	parent = frappe.db.get_value(
		"Account", {"company": COMPANY, "is_group": 1, "root_type": root_type}, "name"
	)
	if not parent:
		raise ValueError(f"No {root_type} group account for {COMPANY}")

	frappe.get_doc(
		{
			"doctype": "Account",
			"account_name": label,
			"parent_account": parent,
			"company": COMPANY,
			"root_type": root_type,
			"is_group": 0,
		}
	).insert()

	return name


def fiscal_year_for(day: str) -> str:
	return frappe.db.get_value(
		"Fiscal Year",
		{"year_start_date": ("<=", day), "year_end_date": (">=", day), "disabled": 0},
		"name",
	)


def cost_center(name: str) -> str:
	full_name = f"{name} - _TC"
	if not frappe.db.exists("Cost Center", full_name):
		parent = frappe.db.get_value("Cost Center", {"company": COMPANY, "is_group": 1}, "name")
		frappe.get_doc(
			{
				"doctype": "Cost Center",
				"cost_center_name": name,
				"parent_cost_center": parent,
				"company": COMPANY,
				"is_group": 0,
			}
		).insert()

	return full_name


def post(amount, debit_account, credit_account, posting_date, center=None):
	"""Put one balanced entry into the ledger."""
	journal_entry = frappe.new_doc("Journal Entry")
	journal_entry.voucher_type = "Journal Entry"
	journal_entry.company = COMPANY
	journal_entry.posting_date = posting_date
	for account, side in ((debit_account, "debit"), (credit_account, "credit")):
		journal_entry.append(
			"accounts",
			{"account": account, f"{side}_in_account_currency": amount, "cost_center": center},
		)

	journal_entry.insert()
	journal_entry.submit()
	return journal_entry


def clear_ledger():
	"""Empty the company's ledger.

	Submitting a document commits, so the rollback between tests does not undo
	a posted journal entry and its figures would carry into the next test. The
	deletes go past the document lifecycle on purpose: this is test scaffolding
	on a throwaway site, and cancelling would leave reversal entries behind,
	which is exactly what has to disappear here.
	"""
	journal_entries = frappe.get_all("Journal Entry", filters={"company": COMPANY}, pluck="name")
	if journal_entries:
		frappe.db.delete("Journal Entry Account", {"parent": ("in", journal_entries)})
		frappe.db.delete("Journal Entry", {"name": ("in", journal_entries)})

	frappe.db.delete("GL Entry", {"company": COMPANY})


class TestSummenUndSaldenliste(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.asset = ledger_account("SuSa Test Asset", "Asset")
		cls.liability = ledger_account("SuSa Test Liability", "Liability")
		cls.expense = ledger_account("SuSa Test Expense", "Expense")

	def setUp(self):
		clear_ledger()

	def tearDown(self):
		clear_ledger()

	def report(self, month=6, **filters):
		options = {
			"company": COMPANY,
			"fiscal_year": fiscal_year_for(THIS_YEAR),
			"month": month,
			"with_previous_year": 0,
			"hide_empty_rows": 0,
		}
		options.update(filters)
		result = run("Summen- und Saldenliste", filters=options, ignore_prepared_report=True)
		by_account = {row["account"]: row for row in result["result"]}
		columns = [column["fieldname"] for column in result["columns"]]
		return by_account, columns

	# --- the regression this report was fixed for -------------------------

	def test_account_without_movement_in_the_month_still_appears(self):
		"""A balance does not stop existing because a month had no postings.

		The report used to be built from the accounts moved in the evaluation
		month, so a quiet month came back empty.
		"""
		post(119, self.asset, self.expense, THIS_YEAR)

		rows, _ = self.report(month=8)

		self.assertIn(self.asset, rows)
		self.assertEqual(frappe.utils.flt(rows[self.asset]["debit_in_evaluation_period"]), 0)
		self.assertEqual(rows[self.asset]["debit_until_evaluation_period"], 119)
		self.assertEqual(rows[self.asset]["debit_closing_balance"], 119)

	# --- direction --------------------------------------------------------

	def test_closing_balance_sits_on_the_natural_side(self):
		post(200, self.asset, self.liability, THIS_YEAR)

		rows, _ = self.report()

		self.assertEqual(rows[self.asset]["debit_closing_balance"], 200)
		self.assertIsNone(rows[self.asset]["credit_closing_balance"])
		self.assertEqual(rows[self.liability]["credit_closing_balance"], 200)
		self.assertIsNone(rows[self.liability]["debit_closing_balance"])

	def test_only_balance_sheet_accounts_carry_an_opening_balance(self):
		"""Income and expense accounts start every fiscal year at zero."""
		post(50, self.asset, self.expense, LAST_YEAR)

		rows, _ = self.report()

		self.assertEqual(rows[self.asset]["debit_opening_balance"], 50)
		self.assertIsNone(rows[self.expense]["debit_opening_balance"])
		self.assertIsNone(rows[self.expense]["credit_opening_balance"])

	# --- previous year ----------------------------------------------------

	def test_previous_year_columns_carry_the_prior_year_movement(self):
		post(80, self.asset, self.expense, LAST_YEAR)

		rows, columns = self.report(with_previous_year=1)

		self.assertIn("previous_year_in_evaluation_period", columns)
		self.assertEqual(rows[self.asset]["previous_year_in_evaluation_period"], 80)
		self.assertEqual(rows[self.asset]["previous_year_until_evaluation_period"], 80)
		# Expense keeps its natural direction: a credit reads as a negative net.
		self.assertEqual(rows[self.expense]["previous_year_in_evaluation_period"], -80)

	def test_previous_year_columns_are_absent_when_not_asked_for(self):
		_, columns = self.report(with_previous_year=0)

		self.assertNotIn("previous_year_in_evaluation_period", columns)
		self.assertNotIn("previous_year_until_evaluation_period", columns)

	# --- filters ----------------------------------------------------------

	def test_hide_empty_rows_drops_accounts_without_figures(self):
		post(70, self.asset, self.expense, LAST_YEAR)

		shown, _ = self.report(hide_empty_rows=0)
		hidden, _ = self.report(hide_empty_rows=1)

		# The expense account only moved last year: no opening balance, no
		# turnover this year, so it is empty in this fiscal year.
		self.assertIn(self.expense, shown)
		self.assertNotIn(self.expense, hidden)
		# The asset account carries the balance forward and stays.
		self.assertIn(self.asset, hidden)

	def test_cost_center_filter_narrows_the_figures(self):
		mine = cost_center("Bookkeeping Test A")
		other = cost_center("Bookkeeping Test B")
		post(300, self.asset, self.expense, THIS_YEAR, center=mine)
		post(400, self.asset, self.expense, THIS_YEAR, center=other)

		everything, _ = self.report()
		narrowed, _ = self.report(cost_center=mine)

		self.assertEqual(everything[self.asset]["debit_in_evaluation_period"], 700)
		self.assertEqual(narrowed[self.asset]["debit_in_evaluation_period"], 300)
