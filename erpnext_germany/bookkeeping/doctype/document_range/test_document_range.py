# Copyright (c) 2026, ALYF GmbH and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import nowdate

from erpnext_germany.bookkeeping.doctype.posting_batch.test_posting_batch import (
	TEST_COMPANY,
	fiscal_year_for,
)

test_dependencies = ["Company"]


def a_range(title: str, **kwargs):
	doc = frappe.new_doc("Document Range")
	doc.title = title
	doc.company = TEST_COMPANY
	doc.fiscal_year = fiscal_year_for(nowdate())
	doc.kind = "Other"
	doc.update(kwargs)
	return doc


class TestDocumentRange(FrappeTestCase):
	def tearDown(self):
		for name in frappe.get_all(
			"Document Range", filters={"title": ("like", "Range Test%")}, pluck="name"
		):
			frappe.delete_doc("Document Range", name, force=True)

	def test_a_range_with_a_prefix_is_accepted(self):
		doc = a_range("Range Test A", prefix="RTA-").insert()

		self.assertEqual(doc.prefix, "RTA-")

	def test_a_range_knows_which_documents_it_counts(self):
		self.assertEqual(a_range("Range Test B", kind="Sales Invoice").source, ("Sales Invoice", "name"))
		self.assertEqual(a_range("Range Test C", kind="Cash").source, ("Journal Entry", "bill_no"))

	def test_two_ranges_over_the_same_documents_need_different_prefixes(self):
		"""Cash, bank and everything else are all journal entries. Without
		distinct prefixes each would report the other's numbers as gaps."""
		a_range("Range Test D", kind="Cash", prefix="RTD-").insert()

		with self.assertRaises(frappe.ValidationError):
			a_range("Range Test E", kind="Bank", prefix="RTD-").insert()

	def test_two_ranges_over_the_same_documents_both_need_a_prefix(self):
		a_range("Range Test F", kind="Cash", prefix="RTF-").insert()

		with self.assertRaises(frappe.ValidationError):
			a_range("Range Test G", kind="Bank").insert()

	def test_distinct_prefixes_over_the_same_documents_are_fine(self):
		a_range("Range Test H", kind="Cash", prefix="RTH-").insert()
		other = a_range("Range Test I", kind="Bank", prefix="RTI-").insert()

		self.assertEqual(other.prefix, "RTI-")

	def test_ranges_over_different_documents_do_not_collide(self):
		"""Sales invoices and journal entries never share a number."""
		a_range("Range Test J", kind="Sales Invoice").insert()
		other = a_range("Range Test K", kind="Purchase Invoice").insert()

		self.assertEqual(other.kind, "Purchase Invoice")

	def test_an_unknown_kind_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			a_range("Range Test L", kind="Nichts dergleichen").insert()
