# Copyright (c) 2026, ALYF GmbH and contributors
# For license information, please see license.txt

"""A Belegkreis: one run of document numbers that has to be unbroken.

Which documents belong to a range follows from its kind, not from a field
somebody fills in per document. Outgoing invoices are the outgoing invoice
range of their company and year, and nothing else. A range that had to be
assigned by hand would have gaps exactly where somebody forgot -- which is
the thing it exists to detect.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

from erpnext_germany.bookkeeping.document_ranges import belongs_to, parse_number

# Which documents a range of this kind counts, and which field carries the
# number a person would recognise as the Belegnummer.
SOURCES = {
	"Sales Invoice": ("Sales Invoice", "name"),
	"Purchase Invoice": ("Purchase Invoice", "bill_no"),
	"Cash": ("Journal Entry", "bill_no"),
	"Bank": ("Journal Entry", "bill_no"),
	"Other": ("Journal Entry", "bill_no"),
}


class DocumentRange(Document):
	def validate(self):
		self.validate_kind()
		self.validate_no_overlap()

	def validate_kind(self):
		if self.kind not in SOURCES:
			frappe.throw(_("{0} is not a kind of document range.").format(self.kind))

	def validate_no_overlap(self):
		"""Two ranges must never count the same documents.

		Cash, bank and everything else are all journal entries, so what tells
		them apart is the prefix their numbers carry -- nothing else does. Two
		ranges reading the same documents without distinct prefixes would each
		report the other's numbers as gaps, and neither would be wrong.
		"""
		for other in self.overlapping():
			if not self.prefix or not other.prefix:
				frappe.throw(
					_("{0} already reads the same documents. Give both a prefix to tell them apart.").format(
						other.name
					),
					title=_("Ranges Overlap"),
				)

			if other.prefix == self.prefix:
				frappe.throw(
					_("{0} already counts the numbers starting with {1}.").format(other.name, self.prefix),
					title=_("Ranges Overlap"),
				)

	def overlapping(self) -> list[frappe._dict]:
		"""Other ranges of this company and year that read the same documents."""
		doctype, field = self.source
		return [
			other
			for other in frappe.get_all(
				"Document Range",
				filters={
					"company": self.company,
					"fiscal_year": self.fiscal_year,
					"name": ("!=", self.name),
				},
				fields=["name", "kind", "prefix"],
			)
			if SOURCES.get(other.kind) == (doctype, field)
		]

	@property
	def source(self) -> tuple[str, str]:
		return SOURCES[self.kind]

	def documents(self) -> list[frappe._dict]:
		"""Every document this range counts, with its number read out.

		Cancelled documents are in on purpose: a cancelled invoice still
		occupies its number and is still there to be shown. Leaving it out
		would report a gap where nothing is missing.

		Deliberately not narrowed to the fiscal year either -- a document
		dated outside its year is one of the things worth finding, so the
		reading cannot start by excluding it.
		"""
		doctype, field = self.source
		rows = []

		for document in frappe.get_all(
			doctype,
			filters={"company": self.company, "docstatus": ("<", 3)},
			fields=["name", field, "posting_date", "docstatus"],
			order_by="posting_date asc, name asc",
		):
			raw = document.get(field)
			if not belongs_to(raw, self.prefix or ""):
				# Either nothing was written in the number field, or the
				# number belongs to a different range. Neither is a hole in
				# this one.
				continue

			parsed = parse_number(raw)
			rows.append(
				frappe._dict(
					voucher_type=doctype,
					voucher_no=document.name,
					number_text=parsed.raw,
					number=parsed.number,
					posting_date=getdate(document.get("posting_date")),
					docstatus=document.docstatus,
				)
			)

		return rows
