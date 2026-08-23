# Copyright (c) 2026, ALYF GmbH and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, nowdate

from erpnext_germany.bookkeeping.doctype.posting_batch.test_posting_batch import (
	TEST_COMPANY,
	fiscal_year_for,
	posting_accounts,
)
from erpnext_germany.bookkeeping.ledger import LedgerScope, get_totals
from erpnext_germany.bookkeeping.lockdown import clear_lockdown_cache
from erpnext_germany.bookkeeping.report.kontoblatt import kontoblatt
from erpnext_germany.bookkeeping.reversal import reverse_entry

test_dependencies = ["Company"]

ACCOUNT_NUMBER = "90300"


def ensure_account(number: str, label: str, root_type: str) -> str:
	"""An account of our own, so the sheet shows only what these tests book.

	Posting commits, so it has to outlive the rollback -- created once and
	reused, and made sure of again by every test.
	"""
	existing = frappe.get_all(
		"Account", filters={"company": TEST_COMPANY, "account_number": number}, pluck="name"
	)
	if existing:
		return existing[0]

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
			}
		)
		.insert()
		.name
	)


class TestKontoblatt(FrappeTestCase):
	def setUp(self):
		# frappe.db.delete on purpose: a lockdown cannot be removed through the
		# document lifecycle by design, so test isolation has to go past it.
		frappe.db.delete("Ledger Lockdown")
		clear_lockdown_cache()

		self.account = ensure_account(ACCOUNT_NUMBER, "Kontoblatt Test", "Expense")
		self.bank = posting_accounts("Asset", 1)[0]
		self.today = nowdate()

	def tearDown(self):
		frappe.db.delete("Ledger Lockdown")
		clear_lockdown_cache()

	# --- helpers ----------------------------------------------------------

	def book(self, amount: float, direction: str = "Debit", on: str | None = None, **kwargs) -> str:
		day = on or self.today
		entry = {
			"posting_date": day,
			"amount": amount,
			"direction": direction,
			"account": self.account,
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

	def sheet(self, **overrides) -> list[dict]:
		filters = {
			"company": TEST_COMPANY,
			"account": self.account,
			"from_date": self.today,
			"to_date": self.today,
		}
		filters.update(overrides)
		_columns, data = kontoblatt.execute(filters)
		return data

	def movements(self, **overrides) -> list[dict]:
		return [row for row in self.sheet(**overrides) if not row.get("is_opening")]

	def last_balance(self) -> float:
		"""Where the sheet stands right now.

		Posting commits, so the lines of earlier tests are still on this
		account. Every assertion below therefore measures from the last line
		rather than from nought.
		"""
		return self.sheet()[-1]["balance"]

	# --- how the sheet is built -------------------------------------------

	def test_the_sheet_starts_with_the_balance_carried_in(self):
		"""Always there, even at nought: otherwise the reader assumes it was."""
		first = self.sheet()[0]

		self.assertTrue(first["is_opening"])
		self.assertEqual(first["remark"], "Balance carried forward")

	def test_the_balance_carried_in_is_what_was_booked_before_the_period(self):
		self.book(300.0, on=add_days(self.today, -10))
		opening = self.sheet()[0]["balance"]

		self.book(200.0, on=add_days(self.today, -5))

		self.assertEqual(self.sheet()[0]["balance"], opening + 200.0)

	def test_every_line_shows_the_balance_as_it_stood(self):
		"""This is what the sheet is for: reading until the figure stops matching."""
		before = self.last_balance()
		self.book(100.0)
		self.book(40.0, direction="Credit")
		rows = self.movements()

		self.assertEqual(rows[-2]["balance"], before + 100.0)
		self.assertEqual(rows[-1]["balance"], before + 60.0)

	def test_an_expense_account_reads_its_costs_positive(self):
		before = self.last_balance()
		self.book(100.0)

		self.assertEqual(self.movements()[-1]["balance"], before + 100.0)

	def test_the_lines_are_ordered_as_they_were_booked(self):
		"""Two entries on the same day still happened one after the other."""
		self.book(10.0)
		self.book(20.0)
		self.book(30.0)
		amounts = [row["debit"] for row in self.movements()[-3:]]

		self.assertEqual(amounts, [10.0, 20.0, 30.0])

	# --- what a line says --------------------------------------------------

	def test_a_line_carries_the_document_number_it_was_booked_with(self):
		self.book(100.0, document_number="RE 4711", document_number_2="K 22")
		row = self.movements()[-1]

		self.assertEqual(row["document_number"], "RE 4711")
		self.assertEqual(row["document_number_2"], "K 22")

	def test_a_line_without_a_document_number_stands_under_its_voucher(self):
		voucher = self.book(100.0)

		self.assertEqual(self.movements()[-1]["document_number"], voucher)

	def test_a_line_names_its_contra_account(self):
		self.book(100.0)

		self.assertEqual(self.movements()[-1]["against_account"], self.bank)

	def test_a_line_carries_its_booking_text(self):
		self.book(100.0, remark="Buerobedarf")

		self.assertIn("Buerobedarf", self.movements()[-1]["remark"] or "")

	def test_a_line_points_at_the_voucher_it_came_from(self):
		voucher = self.book(100.0)
		row = self.movements()[-1]

		self.assertEqual(row["voucher_type"], "Journal Entry")
		self.assertEqual(row["voucher_no"], voucher)

	def test_a_line_says_whether_a_document_was_filed_with_the_booking(self):
		"""The last step of the drill-down: from the booking to the paper."""
		voucher = self.book(100.0)
		frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "rechnung.txt",
				"attached_to_doctype": "Journal Entry",
				"attached_to_name": voucher,
				"content": "Rechnung",
			}
		).insert()

		row = next(row for row in self.movements() if row["voucher_no"] == voucher)
		self.assertEqual([file["name"] for file in row["attachments"]], ["rechnung.txt"])

	def test_a_line_without_a_document_says_so_by_saying_nothing(self):
		self.book(100.0)

		self.assertEqual(self.movements()[-1]["attachments"], [])

	# --- agreement with the evaluations ------------------------------------

	def test_a_general_reversal_is_read_out_of_the_balance_carried_in(self):
		"""The sheet has to tie to the evaluation it was opened from."""
		day = add_days(self.today, -10)
		before = self.sheet()[0]["balance"]
		reverse_entry(self.book(100.0, on=day), "Betrag falsch erfasst", day)

		self.assertEqual(self.sheet()[0]["balance"], before)

	def test_a_general_reversal_is_read_out_of_the_turnover_of_the_sheet(self):
		"""The balance was never the hard part. The turnover is.

		A reversal shown as a credit and counted as a negative debit agrees
		with the Summen- und Saldenliste on the balance and disagrees on
		Soll and Haben -- and those are the figures a tax advisor compares.
		"""
		day = add_days(self.today, 4)
		before = self.movements(from_date=day, to_date=day)
		reverse_entry(self.book(100.0, on=day), "Betrag falsch erfasst", day)

		added = self.movements(from_date=day, to_date=day)[len(before) :]
		self.assertEqual(sum(row["debit"] for row in added), 0.0)
		self.assertEqual(sum(row["credit"] for row in added), 0.0)

	def test_the_turnover_of_the_sheet_is_the_turnover_of_the_evaluation(self):
		"""One reading of the ledger, or the proof behind a BWA proves nothing."""
		day = add_days(self.today, 5)
		self.book(70.0, on=day)
		reverse_entry(self.book(100.0, on=day), "Betrag falsch erfasst", day)

		lines = self.movements(from_date=day, to_date=day)
		totals = get_totals(
			LedgerScope(
				company=TEST_COMPANY,
				from_date=day,
				to_date=day,
				accounts=[self.account],
				skip_period_closing=True,
			)
		)
		figure = totals[self.account]

		self.assertAlmostEqual(sum(row["debit"] for row in lines), figure.debit, places=2)
		self.assertAlmostEqual(sum(row["credit"] for row in lines), figure.credit, places=2)

	def test_an_expense_account_starts_the_fiscal_year_at_nought(self):
		"""Otherwise every balance on the sheet is a year of costs too high.

		The account here is an Expense account, and the Summen- und
		Saldenliste shows it starting each year at nought. A sheet opened
		from that row has to start there too, whether or not the year was
		ever closed with a period closing voucher.
		"""
		year_start = kontoblatt.year_start(TEST_COMPANY, getdate(self.today))
		self.book(40.0, on=add_days(year_start, -1))

		sheet = self.sheet(from_date=year_start, to_date=self.today)

		self.assertEqual(sheet[0]["balance"], 0.0)

	def test_the_sheet_covers_only_the_period_it_was_opened_for(self):
		self.book(100.0, on=add_days(self.today, -10))
		self.book(50.0)

		days = {str(row["posting_date"]) for row in self.movements()}
		self.assertEqual(days, {self.today})

	def test_a_cost_center_narrows_the_sheet(self):
		centers = frappe.get_all(
			"Cost Center", filters={"company": TEST_COMPANY, "is_group": 0}, pluck="name", limit=2
		)
		if len(centers) < 2:
			self.skipTest("Only one cost center on this site")

		self.book(100.0, cost_center=centers[0])
		rows = self.movements(cost_center=centers[1])

		self.assertEqual(rows, [])

	# --- what the report refuses -------------------------------------------

	def test_a_sheet_without_an_account_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			kontoblatt.execute({"company": TEST_COMPANY, "from_date": self.today, "to_date": self.today})

	def test_a_sheet_without_a_company_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			kontoblatt.execute({"account": self.account})
