# Copyright (c) 2026, ALYF GmbH and contributors
# For license information, please see license.txt

"""The arrangement of a BWA.

A form is checked here rather than when it is read, because a BWA that adds
up wrongly is worse than no BWA at all: it is the sheet a bank makes a
decision on, and nobody recalculates it by hand to find out.
"""

import frappe
from frappe import _
from frappe.model.document import Document

from erpnext_germany.bookkeeping.bwa import ACCOUNTS, RATIO, ROW_TYPES, Row, parse_ranges


class BWASchema(Document):
	def validate(self):
		self.validate_row_numbers()
		self.validate_ranges()
		self.validate_spans()
		self.validate_single_default()

	def validate_row_numbers(self):
		"""Numbers are what the result lines point at, so they have to be unique.

		Ascending too: a BWA is read downwards, and a form whose numbering
		jumps about cannot be checked by eye against the printed sheet.
		"""
		seen = set()
		previous = 0
		for row in self.rows:
			if row.row_number in seen:
				frappe.throw(_("Row {0} appears twice.").format(row.row_number))

			if row.row_number <= previous:
				frappe.throw(
					_("Row {0} comes after row {1}. The rows have to be numbered upwards.").format(
						row.row_number, previous
					)
				)

			seen.add(row.row_number)
			previous = row.row_number

	def validate_ranges(self):
		for row in self.rows:
			if row.row_type not in ROW_TYPES:
				frappe.throw(_("Row {0} has an unknown type {1}.").format(row.row_number, row.row_type))

			if row.row_type != ACCOUNTS:
				continue

			if not (row.accounts or "").strip():
				frappe.throw(_("Row {0} covers no accounts.").format(row.row_number))

			try:
				parse_ranges(row.accounts)
			except ValueError as error:
				frappe.throw(_("Row {0}: {1}").format(row.row_number, str(error)))

	def validate_spans(self):
		"""A result line has to point at lines that exist and stand above it."""
		numbers = {row.row_number for row in self.rows}

		for row in self.rows:
			if row.row_type == ACCOUNTS:
				continue

			if row.from_row > row.to_row:
				frappe.throw(
					_("Row {0} starts its total at row {1} and ends it at row {2}.").format(
						row.row_number, row.from_row, row.to_row
					)
				)

			if row.to_row >= row.row_number:
				frappe.throw(
					_("Row {0} would count itself or a line below it.").format(row.row_number),
					title=_("Result Points Downwards"),
				)

			if row.row_type == RATIO and row.reference_row not in numbers:
				frappe.throw(
					_("Row {0} refers to row {1}, which does not exist.").format(
						row.row_number, row.reference_row
					)
				)

	def validate_single_default(self):
		"""Exactly one arrangement can be the one the report opens with."""
		if not self.is_default:
			return

		for other in frappe.get_all(
			"BWA Schema", filters={"is_default": 1, "name": ("!=", self.name)}, pluck="name"
		):
			# Through the document, so the change is versioned like any other.
			schema = frappe.get_doc("BWA Schema", other)
			schema.is_default = 0
			schema.save()

	def as_rows(self) -> list[Row]:
		"""The form in the shape the arithmetic works on."""
		return [
			Row(
				number=row.row_number,
				label=row.label,
				row_type=row.row_type,
				sign=-1 if row.sign == "-" else 1,
				ranges=parse_ranges(row.accounts) if row.row_type == ACCOUNTS else (),
				from_row=row.from_row or 0,
				to_row=row.to_row or 0,
				reference_row=row.reference_row or 0,
			)
			for row in self.rows
		]


def get_default_schema() -> str | None:
	"""The arrangement the report opens with, or the only one there is."""
	names = frappe.get_all(
		"BWA Schema",
		filters={"disabled": 0},
		fields=["name", "is_default"],
		order_by="is_default desc, name asc",
		limit=1,
	)
	return names[0].name if names else None
