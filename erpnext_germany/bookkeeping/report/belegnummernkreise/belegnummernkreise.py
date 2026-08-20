# Copyright (c) 2026, ALYF GmbH and contributors
# For license information, please see license.txt

"""What is missing from a run of document numbers.

A gap in the numbering is what an auditor takes as evidence that a document
was written and then made to disappear, and the burden of explaining it falls
on the company. So the sheet says, per range, which numbers between the first
and the last nothing was written under, which numbers were used twice, and
which documents are dated outside the year they were counted in.

Cancelled documents are counted as present. A cancelled invoice still occupies
its number and is still there to be shown -- it is not a gap, and reporting it
as one would send somebody looking for a document that was never missing.
"""

from datetime import date

import frappe
from frappe import _
from frappe.utils import getdate

from erpnext_germany.bookkeeping.document_ranges import (
	describe_gap,
	find_duplicates,
	find_gaps,
	out_of_period,
)

GAP = "Gap"
DUPLICATE = "Duplicate"
OUTSIDE = "Outside the period"
UNREADABLE = "Not countable"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.company:
		frappe.throw(_("Choose a company."))

	if not filters.fiscal_year:
		frappe.throw(_("Choose a fiscal year."))

	return get_columns(), get_data(filters)


def get_columns() -> list[dict]:
	return [
		{
			"fieldname": "range",
			"label": _("Document Range"),
			"fieldtype": "Link",
			"options": "Document Range",
			"width": 220,
		},
		{"fieldname": "finding", "label": _("Finding"), "fieldtype": "Data", "width": 150},
		{"fieldname": "numbers", "label": _("Numbers"), "fieldtype": "Data", "width": 280},
		{"fieldname": "count", "label": _("Count"), "fieldtype": "Int", "width": 90},
		{"fieldname": "detail", "label": _("Detail"), "fieldtype": "Data", "width": 340},
		{
			"fieldname": "voucher_no",
			"label": _("Document"),
			"fieldtype": "Dynamic Link",
			"options": "voucher_type",
			"width": 180,
		},
		{
			"fieldname": "voucher_type",
			"label": _("Document Type"),
			"fieldtype": "Data",
			"width": 140,
			"hidden": 1,
		},
	]


def get_data(filters: frappe._dict) -> list[dict]:
	from_date, to_date = fiscal_year_range(filters.fiscal_year)
	rows = []

	for name in get_ranges(filters):
		document_range = frappe.get_doc("Document Range", name)
		documents = document_range.documents()
		rows.extend(describe(document_range, documents, from_date, to_date))

	return rows


def get_ranges(filters: frappe._dict) -> list[str]:
	if filters.document_range:
		return [filters.document_range]

	return frappe.get_all(
		"Document Range",
		filters={"company": filters.company, "fiscal_year": filters.fiscal_year, "disabled": 0},
		pluck="name",
		order_by="title asc",
	)


def describe(document_range, documents: list[frappe._dict], from_date, to_date) -> list[dict]:
	"""One heading for the range, then whatever is wrong with it."""
	countable = [document for document in documents if document.number is not None]
	numbers = [document.number for document in countable]
	prefix = document_range.prefix or ""

	rows = [
		{
			"range": document_range.name,
			"finding": _("Range"),
			"numbers": span(numbers, prefix),
			"count": len(countable),
			"detail": _("{0}, {1}").format(document_range.kind, document_range.fiscal_year),
			"indent": 0,
			"is_range": 1,
		}
	]

	for gap in find_gaps(numbers):
		rows.append(
			finding(
				document_range,
				GAP,
				describe_gap(gap, prefix),
				gap.size,
				_("Nothing was written under this."),
			)
		)

	for duplicate in find_duplicates(numbers):
		used = [document for document in countable if document.number == duplicate]
		for document in used:
			rows.append(
				finding(
					document_range,
					DUPLICATE,
					f"{prefix}{duplicate}",
					len(used),
					_("Used by {0} documents.").format(len(used)),
					document,
				)
			)

	loose = out_of_period([(document, document.posting_date) for document in countable], from_date, to_date)
	for document, _posting_date in loose:
		rows.append(
			finding(
				document_range,
				OUTSIDE,
				document.number_text,
				1,
				_("Dated {0}.").format(frappe.utils.format_date(document.posting_date)),
				document,
			)
		)

	for document in documents:
		if document.number is None:
			rows.append(
				finding(
					document_range,
					UNREADABLE,
					document.number_text,
					1,
					_("This number has no counting part, so it is not part of the sequence."),
					document,
				)
			)

	return rows


def finding(document_range, kind: str, numbers: str, count: int, detail: str, document=None) -> dict:
	return {
		"range": document_range.name,
		"finding": kind,
		"numbers": numbers,
		"count": count,
		"detail": detail,
		"voucher_type": document.voucher_type if document else None,
		"voucher_no": document.voucher_no if document else None,
		"indent": 1,
		"is_range": 0,
	}


def span(numbers: list[int], prefix: str) -> str:
	if not numbers:
		return ""

	return f"{prefix}{min(numbers)} - {prefix}{max(numbers)}"


def fiscal_year_range(fiscal_year: str) -> tuple[date, date]:
	dates = frappe.get_cached_value(
		"Fiscal Year", fiscal_year, ["year_start_date", "year_end_date"], as_dict=True
	)
	if not dates:
		frappe.throw(_("Fiscal Year {0} not found").format(fiscal_year))

	return (getdate(dates.year_start_date), getdate(dates.year_end_date))
