# Copyright (c) 2026, ALYF GmbH and contributors
# For license information, please see license.txt

"""What a voucher carries besides its ledger rows, fetched for many at once.

A ledger row says which account moved. It does not say what number stood on
the paper, or whether there is any paper at all -- and both are questions
every German evaluation asks: the Kontoblatt to show them, the GoBD package
to hand them to an auditor.

Both are asked for a whole sheet or a whole year at a time, so both are
answered in one query per doctype rather than one per line. And both are
keyed by ``(voucher_type, voucher_no)``: a name only identifies a document
together with its doctype, and an ``IN`` over types crossed with an ``IN``
over names matches pairs that do not exist.
"""

import frappe

from erpnext_germany.bookkeeping.account_sheet import DOCUMENT_NUMBER_FIELDS

Voucher = tuple[str, str]


def document_fields(vouchers: set[Voucher]) -> dict[Voucher, frappe._dict]:
	"""The document-number fields of these vouchers, one query per doctype."""
	names_by_type: dict[str, set[str]] = {}
	for voucher_type, voucher_no in vouchers:
		if voucher_type in DOCUMENT_NUMBER_FIELDS:
			names_by_type.setdefault(voucher_type, set()).add(voucher_no)

	fields: dict[Voucher, frappe._dict] = {}
	for voucher_type, names in names_by_type.items():
		fieldnames = [field for field in DOCUMENT_NUMBER_FIELDS[voucher_type] if field]
		for row in frappe.get_all(
			voucher_type, filters={"name": ("in", sorted(names))}, fields=["name", *fieldnames]
		):
			fields[(voucher_type, row.name)] = row

	return fields


def attachments(vouchers: set[Voucher]) -> dict[Voucher, list[frappe._dict]]:
	"""The files filed with these vouchers, oldest first.

	One query for the whole set, then narrowed to the pairs actually asked
	for: filtering by type and by name separately is a cross product, and it
	would hang somebody else's document on this booking.
	"""
	if not vouchers:
		return {}

	files = frappe.get_all(
		"File",
		filters={
			"attached_to_doctype": ("in", sorted({voucher_type for voucher_type, _name in vouchers})),
			"attached_to_name": ("in", sorted({name for _type, name in vouchers})),
		},
		fields=["name", "file_name", "file_url", "attached_to_doctype", "attached_to_name"],
		order_by="attached_to_name asc, creation asc, name asc",
	)

	filed: dict[Voucher, list[frappe._dict]] = {}
	for file in files:
		key = (file.attached_to_doctype, file.attached_to_name)
		if key in vouchers:
			filed.setdefault(key, []).append(file)

	return filed
