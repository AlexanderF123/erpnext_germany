# Copyright (c) 2026, ALYF GmbH and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from erpnext_germany.bookkeeping.doctype.posting_batch.test_posting_batch import (
	TEST_COMPANY,
	fiscal_year_for,
	posting_accounts,
)
from erpnext_germany.bookkeeping.ledger import get_totals
from erpnext_germany.bookkeeping.lockdown import clear_lockdown_cache
from erpnext_germany.bookkeeping.report.betriebswirtschaftliche_auswertung import (
	betriebswirtschaftliche_auswertung as report,
)

test_dependencies = ["Company"]

SCHEMA = "BWA Test"
REVENUE_NUMBER = "90100"
MATERIAL_NUMBER = "90200"
LOOSE_NUMBER = "90900"
IN_PERIOD = "2026-06-15"


def group_account(root_type: str) -> str:
	return frappe.get_all(
		"Account",
		filters={"company": TEST_COMPANY, "is_group": 1, "root_type": root_type},
		pluck="name",
		order_by="lft asc",
		limit=1,
	)[0]


def ensure_account(number: str, label: str, root_type: str) -> str:
	"""An account with a known number, created once and reused.

	Posting commits, so an account these tests book to has to outlive the
	rollback -- otherwise the ledger would keep entries whose account is gone.
	"""
	existing = frappe.get_all(
		"Account", filters={"company": TEST_COMPANY, "account_number": number}, pluck="name"
	)
	if existing:
		return existing[0]

	return (
		frappe.get_doc(
			{
				"doctype": "Account",
				"company": TEST_COMPANY,
				"account_name": label,
				"account_number": number,
				"parent_account": group_account(root_type),
				"root_type": root_type,
				"is_group": 0,
			}
		)
		.insert()
		.name
	)


def ensure_schema() -> str:
	"""A small form of our own, so the tests do not depend on the SKR03 ranges."""
	rows = [
		{
			"row_number": 1,
			"label": "Umsatzerloese",
			"row_type": "Accounts",
			"sign": "+",
			"accounts": "90100-90199",
		},
		{
			"row_number": 2,
			"label": "Materialaufwand",
			"row_type": "Accounts",
			"sign": "-",
			"accounts": "90200-90299",
		},
		{
			"row_number": 3,
			"label": "Rohertrag",
			"row_type": "Subtotal",
			"sign": "+",
			"from_row": 1,
			"to_row": 2,
		},
		{
			"row_number": 4,
			"label": "Gesamtkosten",
			"row_type": "Subtotal",
			"sign": "-",
			"from_row": 2,
			"to_row": 2,
		},
		{
			"row_number": 5,
			"label": "Materialquote",
			"row_type": "Ratio",
			"sign": "-",
			"from_row": 2,
			"to_row": 2,
			"reference_row": 1,
		},
	]

	if frappe.db.exists("BWA Schema", SCHEMA):
		doc = frappe.get_doc("BWA Schema", SCHEMA)
		doc.rows = []
	else:
		doc = frappe.new_doc("BWA Schema")
		doc.schema_name = SCHEMA

	doc.chart_of_accounts = "Test"
	for row in rows:
		doc.append("rows", row)

	doc.save()
	return doc.name


class TestBetriebswirtschaftlicheAuswertung(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.revenue = ensure_account(REVENUE_NUMBER, "BWA Test Erloese", "Income")
		cls.material = ensure_account(MATERIAL_NUMBER, "BWA Test Material", "Expense")
		cls.loose = ensure_account(LOOSE_NUMBER, "BWA Test Ohne Zeile", "Expense")
		cls.bank = posting_accounts("Asset", 1)[0]
		ensure_schema()
		frappe.db.commit()

	def setUp(self):
		# frappe.db.delete on purpose: a lockdown cannot be removed through the
		# document lifecycle by design, so test isolation has to go past it.
		frappe.db.delete("Ledger Lockdown")
		clear_lockdown_cache()

	def tearDown(self):
		frappe.db.delete("Ledger Lockdown")
		clear_lockdown_cache()

	# --- helpers ----------------------------------------------------------

	def book(self, account: str, amount: float, direction: str, on: str = IN_PERIOD):
		batch = frappe.get_doc(
			{
				"doctype": "Posting Batch",
				"company": TEST_COMPANY,
				"fiscal_year": fiscal_year_for(on),
				"from_date": on,
				"to_date": on,
				"entries": [
					{
						"posting_date": on,
						"amount": amount,
						"direction": direction,
						"account": account,
						"against_account": self.bank,
					}
				],
			}
		).insert()
		batch.post()

	def run_report(self, **overrides) -> dict:
		"""The report, as a lookup from line to row."""
		filters = {
			"company": TEST_COMPANY,
			"bwa_schema": SCHEMA,
			"fiscal_year": fiscal_year_for(IN_PERIOD),
			"month": self.month_of(IN_PERIOD),
			"show_accounts": 1,
		}
		filters.update(overrides)
		_columns, data = report.execute(filters)
		return {row["label"]: row for row in data}

	def month_of(self, day: str) -> int:
		"""The 1-based month within the fiscal year, not within the calendar."""
		start = getdate(frappe.get_cached_value("Fiscal Year", fiscal_year_for(day), "year_start_date"))
		posted = getdate(day)
		return (posted.year - start.year) * 12 + posted.month - start.month + 1

	# --- the shipped form -------------------------------------------------

	def test_the_standard_form_is_installed_and_valid(self):
		"""It is shipped with the app, so it has to survive its own validation."""
		schema = frappe.get_doc("BWA Schema", "BWA Standard SKR03")
		schema.save()

		self.assertTrue(schema.is_default)
		self.assertEqual(len(schema.rows), 28)
		self.assertEqual(schema.rows[-1].label, "Vorlaeufiges Ergebnis")

	# --- the figures ------------------------------------------------------

	def test_revenue_lands_on_its_line(self):
		before = self.run_report()["Umsatzerloese"]["current"]
		self.book(self.revenue, 1000.0, "Credit")

		self.assertEqual(self.run_report()["Umsatzerloese"]["current"], before + 1000.0)

	def test_a_cost_line_reads_positive_and_still_comes_off_the_result(self):
		"""A BWA prints costs positive. Only the result shows what they did."""
		before = self.run_report()
		self.book(self.material, 400.0, "Debit")
		after = self.run_report()

		self.assertEqual(after["Materialaufwand"]["current"], before["Materialaufwand"]["current"] + 400.0)
		self.assertEqual(after["Rohertrag"]["current"], before["Rohertrag"]["current"] - 400.0)

	def test_a_cost_total_prints_positive(self):
		before = self.run_report()["Gesamtkosten"]["current"]
		self.book(self.material, 400.0, "Debit")

		self.assertEqual(self.run_report()["Gesamtkosten"]["current"], before + 400.0)

	def test_the_accounts_of_a_line_add_up_to_the_line(self):
		"""The drill-down is only worth having if it reconciles."""
		self.book(self.revenue, 1000.0, "Credit")
		data = self.run_report()

		account_row = data[f"{REVENUE_NUMBER} BWA Test Erloese"]
		self.assertEqual(account_row["indent"], 1)
		self.assertEqual(account_row["current"], data["Umsatzerloese"]["current"])

	def test_an_account_can_be_followed_to_its_ledger(self):
		"""The row carries what the link needs, so the dates match the figure."""
		self.book(self.revenue, 1000.0, "Credit")
		row = self.run_report()[f"{REVENUE_NUMBER} BWA Test Erloese"]

		self.assertEqual(row["account"], self.revenue)
		self.assertEqual(str(row["period_from_date"]), "2026-06-01")
		self.assertEqual(str(row["period_to_date"]), "2026-06-30")

	def test_a_ratio_reads_as_a_percentage(self):
		data = self.run_report()
		revenue = data["Umsatzerloese"]["current"]
		material = data["Materialaufwand"]["current"]

		if not revenue:
			self.skipTest("No revenue booked in this period")

		self.assertAlmostEqual(data["Materialquote"]["current"], 100.0 * material / revenue, places=6)
		self.assertTrue(data["Materialquote"]["is_ratio"])

	# --- what the form does not cover -------------------------------------

	def test_an_account_no_line_covers_is_reported_rather_than_dropped(self):
		"""A range written one digit short must not make money disappear."""
		self.book(self.loose, 250.0, "Debit")
		data = self.run_report()

		self.assertIn("Not covered by the BWA", data)
		self.assertIn(f"{LOOSE_NUMBER} BWA Test Ohne Zeile", data)

	def test_a_balance_sheet_account_is_not_reported_as_missing(self):
		"""Only income and expense belong in a BWA; the bank account does not."""
		self.book(self.revenue, 1000.0, "Credit")
		labels = self.run_report()

		self.assertNotIn(self.bank, [row.get("account") for row in labels.values()])

	# --- agreement with the Summen- und Saldenliste -----------------------

	def test_the_lines_agree_with_the_summen_und_saldenliste(self):
		"""The acceptance criterion: both sheets read the same ledger.

		Checked against the shared reading rather than against a second
		implementation, because that is exactly what the two reports share.
		"""
		self.book(self.revenue, 1000.0, "Credit")
		self.book(self.material, 400.0, "Debit")
		data = self.run_report()
		totals = get_totals(TEST_COMPANY, None, "2026-06-01", "2026-06-30", skip_period_closing=True)

		revenue = totals.get(self.revenue, {})
		self.assertEqual(
			data[f"{REVENUE_NUMBER} BWA Test Erloese"]["current"],
			revenue.get("credit", 0) - revenue.get("debit", 0),
		)

		material = totals.get(self.material, {})
		self.assertEqual(
			data[f"{MATERIAL_NUMBER} BWA Test Material"]["current"],
			material.get("debit", 0) - material.get("credit", 0),
		)

	# --- the columns ------------------------------------------------------

	def test_the_cumulative_column_reaches_back_to_the_start_of_the_year(self):
		self.book(self.revenue, 500.0, "Credit", on="2026-02-10")
		self.book(self.revenue, 300.0, "Credit", on=IN_PERIOD)
		data = self.run_report()

		self.assertGreaterEqual(data["Umsatzerloese"]["cumulative"], data["Umsatzerloese"]["current"] + 500.0)

	def test_the_previous_year_column_reads_the_same_month_a_year_earlier(self):
		self.book(self.revenue, 700.0, "Credit", on="2025-06-15")
		data = self.run_report()

		self.assertGreaterEqual(data["Umsatzerloese"]["previous_year"], 700.0)

	def test_the_deviation_is_stated_where_last_year_had_a_figure(self):
		self.book(self.revenue, 1000.0, "Credit", on="2025-06-15")
		self.book(self.revenue, 1000.0, "Credit", on=IN_PERIOD)
		row = self.run_report()["Umsatzerloese"]

		expected = 100.0 * (row["current"] - row["previous_year"]) / abs(row["previous_year"])
		self.assertAlmostEqual(row["deviation"], expected, places=6)

	def test_the_month_follows_the_fiscal_year_not_the_calendar(self):
		"""A company whose year starts in July reads its own months."""
		year_start = frappe.get_cached_value("Fiscal Year", fiscal_year_for(IN_PERIOD), "year_start_date")
		columns, _data = report.execute(
			{
				"company": TEST_COMPANY,
				"bwa_schema": SCHEMA,
				"fiscal_year": fiscal_year_for(IN_PERIOD),
				"month": 1,
			}
		)

		self.assertEqual(columns[1]["label"], getdate(year_start).strftime("%B"))

	# --- what the report refuses ------------------------------------------

	def test_a_report_without_an_arrangement_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			report.execute({"company": TEST_COMPANY, "fiscal_year": fiscal_year_for(IN_PERIOD), "month": 6})
