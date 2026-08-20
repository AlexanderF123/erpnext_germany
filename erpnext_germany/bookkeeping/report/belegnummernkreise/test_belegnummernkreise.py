# Copyright (c) 2026, ALYF GmbH and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

from erpnext_germany.bookkeeping.doctype.posting_batch.test_posting_batch import (
	TEST_COMPANY,
	fiscal_year_for,
	posting_accounts,
)
from erpnext_germany.bookkeeping.lockdown import clear_lockdown_cache
from erpnext_germany.bookkeeping.report.belegnummernkreise import belegnummernkreise as report
from erpnext_germany.bookkeeping.tests.test_month_end import ensure_account

test_dependencies = ["Company"]

PREFIX = "BK-TEST-"
RANGE_NAME = "Belegkreis Test"


class TestBelegnummernkreise(FrappeTestCase):
	def setUp(self):
		# frappe.db.delete on purpose: a lockdown cannot be removed through the
		# document lifecycle by design, so test isolation has to go past it.
		frappe.db.delete("Ledger Lockdown")
		clear_lockdown_cache()

		self.expense = ensure_account("91100", "Monatsabschluss Aufwand", "Expense")
		self.bank = posting_accounts("Asset", 1)[0]
		self.today = nowdate()
		self.fiscal_year = fiscal_year_for(self.today)
		self.range = self.ensure_range()

	def tearDown(self):
		frappe.db.delete("Ledger Lockdown")
		clear_lockdown_cache()

	# --- helpers ----------------------------------------------------------

	def ensure_range(self) -> str:
		if frappe.db.exists("Document Range", RANGE_NAME):
			return RANGE_NAME

		return (
			frappe.get_doc(
				{
					"doctype": "Document Range",
					"title": RANGE_NAME,
					"company": TEST_COMPANY,
					"fiscal_year": self.fiscal_year,
					"kind": "Other",
					"prefix": PREFIX,
				}
			)
			.insert()
			.name
		)

	def book(self, number: str, on: str | None = None) -> str:
		day = on or self.today
		batch = frappe.get_doc(
			{
				"doctype": "Posting Batch",
				"company": TEST_COMPANY,
				"fiscal_year": fiscal_year_for(day),
				"from_date": day,
				"to_date": day,
				"entries": [
					{
						"posting_date": day,
						"amount": 100.0,
						"direction": "Debit",
						"account": self.expense,
						"against_account": self.bank,
						"document_number": number,
					}
				],
			}
		).insert()
		batch.post()
		return batch.entries[0].journal_entry

	def findings(self, kind: str | None = None) -> list[dict]:
		_columns, data = report.execute(
			{
				"company": TEST_COMPANY,
				"fiscal_year": self.fiscal_year,
				"document_range": self.range,
			}
		)
		rows = [row for row in data if not row["is_range"]]
		return [row for row in rows if kind is None or row["finding"] == kind]

	def numbers_reported(self, kind: str) -> list[str]:
		return [row["numbers"] for row in self.findings(kind)]

	# --- the sequence -----------------------------------------------------

	def test_the_range_gets_a_heading_saying_what_it_covers(self):
		self.book(f"{PREFIX}1000")
		_columns, data = report.execute(
			{"company": TEST_COMPANY, "fiscal_year": self.fiscal_year, "document_range": self.range}
		)
		heading = next(row for row in data if row["is_range"])

		self.assertEqual(heading["range"], self.range)
		self.assertIn(self.fiscal_year, heading["detail"])

	def test_an_unbroken_run_reports_no_gap(self):
		base = 2000
		for offset in range(3):
			self.book(f"{PREFIX}{base + offset}")

		gaps = self.numbers_reported(report.GAP)
		self.assertNotIn(f"{PREFIX}{base + 1}", gaps)

	def test_a_missing_number_is_named(self):
		"""A gap is what an auditor takes as evidence a document disappeared."""
		self.book(f"{PREFIX}3000")
		self.book(f"{PREFIX}3002")

		self.assertIn(f"{PREFIX}3001", self.numbers_reported(report.GAP))

	def test_several_missing_numbers_are_named_as_a_span(self):
		self.book(f"{PREFIX}4000")
		self.book(f"{PREFIX}4004")

		self.assertIn(f"{PREFIX}4001 - {PREFIX}4003", self.numbers_reported(report.GAP))

	def test_a_number_used_twice_is_reported_against_both_documents(self):
		"""A sequence can be unbroken and still be wrong."""
		first = self.book(f"{PREFIX}5000")
		second = self.book(f"{PREFIX}5000")

		duplicates = self.findings(report.DUPLICATE)
		vouchers = [row["voucher_no"] for row in duplicates if row["numbers"] == f"{PREFIX}5000"]
		self.assertIn(first, vouchers)
		self.assertIn(second, vouchers)

	def test_a_document_dated_outside_its_year_is_reported(self):
		outside = add_days(f"{self.fiscal_year_start()}", -1)
		self.book(f"{PREFIX}6000", on=outside)

		self.assertIn(f"{PREFIX}6000", self.numbers_reported(report.OUTSIDE))

	def test_a_number_from_another_range_is_left_out_of_this_sequence(self):
		"""Otherwise every other range's numbers would read as gaps here."""
		self.book("ANDERER-7000")

		reported = [row["numbers"] for row in self.findings()]
		self.assertNotIn("ANDERER-7000", reported)

	def test_a_number_that_cannot_be_counted_is_said_so_rather_than_ignored(self):
		self.book(f"{PREFIX}Storno")

		self.assertIn(f"{PREFIX}Storno", self.numbers_reported(report.UNREADABLE))

	# --- what the report refuses -------------------------------------------

	def test_a_sheet_without_a_company_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			report.execute({"fiscal_year": self.fiscal_year})

	def test_a_sheet_without_a_fiscal_year_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			report.execute({"company": TEST_COMPANY})

	def fiscal_year_start(self):
		return frappe.get_cached_value("Fiscal Year", self.fiscal_year, "year_start_date")
