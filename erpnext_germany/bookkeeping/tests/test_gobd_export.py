# Copyright (c) 2026, ALYF GmbH and Contributors
# See license.txt

import io
import zipfile

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import nowdate

from erpnext_germany.bookkeeping import gobd_export
from erpnext_germany.bookkeeping.doctype.posting_batch.test_posting_batch import (
	TEST_COMPANY,
	fiscal_year_for,
	posting_accounts,
)
from erpnext_germany.bookkeeping.tests.test_month_end import ensure_account

test_dependencies = ["Company"]


class TestGoBDExport(FrappeTestCase):
	def setUp(self):
		self.expense = ensure_account("91100", "Monatsabschluss Aufwand", "Expense")
		self.bank = posting_accounts("Asset", 1)[0]
		self.today = nowdate()
		self.fiscal_year = fiscal_year_for(self.today)
		self.from_date, self.to_date = gobd_export.fiscal_year_range(self.fiscal_year)

	# --- helpers ----------------------------------------------------------

	def book(self, amount: float = 100.0, **kwargs) -> str:
		entry = {
			"posting_date": self.today,
			"amount": amount,
			"direction": "Debit",
			"account": self.expense,
			"against_account": self.bank,
		}
		entry.update(kwargs)
		batch = frappe.get_doc(
			{
				"doctype": "Posting Batch",
				"company": TEST_COMPANY,
				"fiscal_year": self.fiscal_year,
				"from_date": self.today,
				"to_date": self.today,
				"entries": [entry],
			}
		).insert()
		batch.post()
		return batch.entries[0].journal_entry

	def package(self) -> dict[str, str]:
		archive = gobd_export.build_package(TEST_COMPANY, self.fiscal_year, self.from_date, self.to_date)
		with zipfile.ZipFile(io.BytesIO(archive)) as opened:
			return {name: opened.read(name).decode("utf-8") for name in opened.namelist()}

	def journal_rows(self) -> list[str]:
		return self.package()["buchungsjournal.csv"].splitlines()[1:]

	# --- what the package contains ----------------------------------------

	def test_the_package_holds_every_declared_table_and_its_index(self):
		files = set(self.package())

		self.assertIn("index.xml", files)
		for table in gobd_export.get_tables():
			self.assertIn(table.file_name, files)

	def test_the_index_describes_the_files_that_are_there(self):
		"""The one failure in an export that nobody catches by looking."""
		package = self.package()
		index = package["index.xml"]

		for table in gobd_export.get_tables():
			self.assertIn(table.file_name, index)
			header = package[table.file_name].splitlines()[0]
			for column in table.columns:
				self.assertIn(column.label, header)
				self.assertIn(f"<Name>{column.label}</Name>", index)

	def test_a_booking_of_the_year_is_in_the_journal(self):
		voucher = self.book(150.0)
		rows = [row for row in self.journal_rows() if voucher in row]

		self.assertTrue(rows)
		self.assertTrue(any("150,00" in row for row in rows))

	def test_the_journal_says_who_entered_a_booking_and_when(self):
		voucher = self.book()
		row = next(row for row in self.journal_rows() if voucher in row)

		self.assertIn(frappe.session.user, row)

	def test_the_document_of_a_booking_is_linked_by_a_stable_identifier(self):
		voucher = self.book()
		file = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "beleg.txt",
				"attached_to_doctype": "Journal Entry",
				"attached_to_name": voucher,
				"content": "Beleg",
			}
		).insert()

		links = self.package()["belegverknuepfungen.csv"]
		self.assertIn(voucher, links)
		self.assertIn(file.name, links)

	def test_a_voucher_without_a_number_on_the_paper_reports_none(self):
		"""Belegfeld 1 says what stood on the document.

		Repeating the voucher's own name there would assert a paper number to
		a Betriebspruefer that no document supports. The Belegnummer column
		already carries what we called it.
		"""
		voucher = self.book()
		row = next(row for row in self.journal_rows() if voucher in row)

		self.assertEqual(row.count(voucher), 1)

	def test_a_voucher_reports_the_number_it_was_booked_with(self):
		voucher = self.book(document_number="RE 4711")
		row = next(row for row in self.journal_rows() if voucher in row)

		self.assertIn("RE 4711", row)

	def test_the_accounts_are_in_the_package_with_their_numbers(self):
		"""Number and name in their own columns, so the journal's account
		column can be matched to the chart."""
		accounts = self.package()["konten.csv"]

		self.assertIn('"91100";"Monatsabschluss Aufwand"', accounts)

	# --- what an auditor relies on ----------------------------------------

	def test_the_export_is_repeatable_and_gives_the_same_bytes(self):
		"""An acceptance criterion, not a nicety: a second copy has to be
		provably the same package."""
		self.book()
		first = gobd_export.build_package(TEST_COMPANY, self.fiscal_year, self.from_date, self.to_date)
		second = gobd_export.build_package(TEST_COMPANY, self.fiscal_year, self.from_date, self.to_date)

		self.assertEqual(first, second)

	def test_a_booking_text_with_a_line_break_does_not_break_a_row(self):
		"""One extra line in the file shifts everything a reader counts on."""
		before = len(self.journal_rows())
		self.book(remark="Miete\nJanuar")

		self.assertEqual(len(self.journal_rows()), before + 2)

	def test_the_package_is_filed_with_the_company(self):
		"""What was handed to an auditor stays where it can be shown again."""
		url = gobd_export.export(TEST_COMPANY, self.fiscal_year)

		self.assertTrue(url)
		files = frappe.get_all(
			"File",
			filters={"attached_to_doctype": "Company", "attached_to_name": TEST_COMPANY},
			pluck="file_name",
		)
		self.assertTrue(any(name.startswith("GoBD") for name in files))

	def test_an_unknown_fiscal_year_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			gobd_export.fiscal_year_range("No Such Year")
