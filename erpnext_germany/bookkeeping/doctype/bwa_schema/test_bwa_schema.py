# Copyright (c) 2026, ALYF GmbH and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

NAME = "BWA Schema Test"


def schema(rows: list[dict], **kwargs):
	doc = frappe.new_doc("BWA Schema")
	doc.schema_name = kwargs.pop("schema_name", NAME)
	doc.update(kwargs)
	for row in rows:
		doc.append("rows", row)

	return doc


def accounts_row(number: int, label: str = "Line", sign: str = "+", accounts: str = "4000-4999"):
	return {
		"row_number": number,
		"label": label,
		"row_type": "Accounts",
		"sign": sign,
		"accounts": accounts,
	}


def subtotal_row(number: int, from_row: int, to_row: int, sign: str = "+"):
	return {
		"row_number": number,
		"label": "Result",
		"row_type": "Subtotal",
		"sign": sign,
		"from_row": from_row,
		"to_row": to_row,
	}


class TestBWASchema(FrappeTestCase):
	def tearDown(self):
		for name in frappe.get_all("BWA Schema", filters={"schema_name": ("like", "BWA Schema Test%")}):
			frappe.delete_doc("BWA Schema", name.name, force=True)

	# --- what a valid form looks like --------------------------------------

	def test_a_simple_form_is_accepted(self):
		doc = schema([accounts_row(1), subtotal_row(2, 1, 1)])
		doc.insert()

		self.assertEqual(len(doc.rows), 2)

	def test_the_form_comes_back_in_the_shape_the_arithmetic_works_on(self):
		doc = schema([accounts_row(1, sign="-", accounts="4100-4199\n4210"), subtotal_row(2, 1, 1)])
		doc.insert()
		rows = doc.as_rows()

		self.assertEqual(rows[0].sign, -1)
		self.assertEqual(len(rows[0].ranges), 2)
		self.assertEqual(rows[1].from_row, 1)

	# --- what is refused ---------------------------------------------------

	def test_a_row_number_is_not_used_twice(self):
		"""Result lines point at numbers, so a number has to mean one line."""
		with self.assertRaises(frappe.ValidationError):
			schema([accounts_row(1), accounts_row(1, label="Again")]).insert()

	def test_rows_are_numbered_upwards(self):
		"""A BWA is read downwards and has to be checkable against the sheet."""
		with self.assertRaises(frappe.ValidationError):
			schema([accounts_row(2), accounts_row(1)]).insert()

	def test_an_account_line_without_accounts_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			schema([accounts_row(1, accounts="   ")]).insert()

	def test_an_unreadable_range_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			schema([accounts_row(1, accounts="Personalkosten")]).insert()

	def test_a_range_that_ends_before_it_starts_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			schema([accounts_row(1, accounts="4999-4000")]).insert()

	def test_a_result_cannot_count_itself(self):
		with self.assertRaises(frappe.ValidationError):
			schema([accounts_row(1), subtotal_row(2, 1, 2)]).insert()

	def test_a_result_cannot_reach_below_itself(self):
		"""Otherwise the sheet would not add up in the order it is read in."""
		with self.assertRaises(frappe.ValidationError):
			schema([accounts_row(1), subtotal_row(2, 1, 3), accounts_row(3)]).insert()

	def test_a_result_that_starts_after_it_ends_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			schema([accounts_row(1), accounts_row(2), subtotal_row(3, 2, 1)]).insert()

	def test_a_ratio_pointing_at_a_missing_line_is_refused(self):
		rows = [
			accounts_row(1),
			{
				"row_number": 2,
				"label": "Quote",
				"row_type": "Ratio",
				"sign": "+",
				"from_row": 1,
				"to_row": 1,
				"reference_row": 99,
			},
		]

		with self.assertRaises(frappe.ValidationError):
			schema(rows).insert()

	# --- the default form --------------------------------------------------

	def test_only_one_form_is_the_default(self):
		"""The report opens on one arrangement, so only one can claim to be it."""
		first = schema([accounts_row(1)], schema_name="BWA Schema Test A", is_default=1)
		first.insert()
		second = schema([accounts_row(1)], schema_name="BWA Schema Test B", is_default=1)
		second.insert()

		self.assertFalse(frappe.get_doc("BWA Schema", first.name).is_default)
		self.assertTrue(frappe.get_doc("BWA Schema", second.name).is_default)
