# Copyright (c) 2026, ALYF GmbH and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate, nowdate

from erpnext_germany.bookkeeping.doctype.posting_batch.test_posting_batch import (
	TEST_COMPANY,
	fiscal_year_for,
	posting_accounts,
)
from erpnext_germany.bookkeeping.month_end import get_titles
from erpnext_germany.bookkeeping.report.pruefliste_monatsabschluss import (
	pruefliste_monatsabschluss as report,
)
from erpnext_germany.bookkeeping.tests.test_month_end import ensure_account

test_dependencies = ["Company"]


class TestPrueflisteMonatsabschluss(FrappeTestCase):
	def setUp(self):
		self.expense = ensure_account("91100", "Monatsabschluss Aufwand", "Expense")
		self.bank = posting_accounts("Asset", 1)[0]
		self.today = nowdate()

	def book(self, amount: float = 100.0) -> str:
		batch = frappe.get_doc(
			{
				"doctype": "Posting Batch",
				"company": TEST_COMPANY,
				"fiscal_year": fiscal_year_for(self.today),
				"from_date": self.today,
				"to_date": self.today,
				"entries": [
					{
						"posting_date": self.today,
						"amount": amount,
						"direction": "Debit",
						"account": self.expense,
						"against_account": self.bank,
					}
				],
			}
		).insert()
		batch.post()
		return batch.entries[0].journal_entry

	def run_report(self, **overrides):
		filters = {
			"company": TEST_COMPANY,
			"fiscal_year": fiscal_year_for(self.today),
			"month": self.month_of(self.today),
		}
		filters.update(overrides)
		return report.execute(filters)

	def month_of(self, day: str) -> int:
		start = getdate(frappe.get_cached_value("Fiscal Year", fiscal_year_for(day), "year_start_date"))
		posted = getdate(day)
		return (posted.year - start.year) * 12 + posted.month - start.month + 1

	def checks(self, rows) -> dict:
		return {row["label"]: row for row in rows if row.get("is_check")}

	# --- what the sheet says -----------------------------------------------

	def test_every_check_gets_a_line_even_when_it_found_nothing(self):
		"""A list that only shows problems cannot tell a clean month from a
		check that never ran."""
		_columns, data = self.run_report()

		self.assertEqual(set(self.checks(data)), set(get_titles().values()))

	def test_a_check_that_found_nothing_reads_as_clean(self):
		_columns, data = self.run_report()
		clearing = self.checks(data)[get_titles()["clearing_accounts"]]

		if clearing["count"]:
			self.skipTest("This site has a balance on a clearing account")

		self.assertEqual(clearing["status"], report.CLEAN)

	def test_a_finding_sits_under_its_check_and_can_be_followed(self):
		voucher = self.book()
		_columns, data = self.run_report()

		finding = next(row for row in data if row.get("voucher_no") == voucher)
		self.assertEqual(finding["indent"], 1)
		self.assertEqual(finding["voucher_type"], "Journal Entry")

	def test_a_finding_carries_the_period_it_was_found_in(self):
		"""So the drill-down lands on the same period the sheet was read for."""
		self.book()
		_columns, data = self.run_report()

		finding = next(row for row in data if row.get("indent") == 1)
		self.assertTrue(finding["period_from_date"])
		self.assertTrue(finding["period_to_date"])

	def test_the_sheet_can_be_narrowed_to_what_needs_looking_at(self):
		self.book()
		_columns, all_rows = self.run_report()
		_columns, only_findings = self.run_report(only_findings=1)

		self.assertLess(len(self.checks(only_findings)), len(self.checks(all_rows)))
		self.assertTrue(all(row["count"] for row in self.checks(only_findings).values()))

	# --- what the report refuses -------------------------------------------

	def test_a_sheet_without_a_company_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			report.execute({"fiscal_year": fiscal_year_for(self.today), "month": 1})

	def test_an_unknown_fiscal_year_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			report.execute({"company": TEST_COMPANY, "fiscal_year": "No Such Year", "month": 1})
