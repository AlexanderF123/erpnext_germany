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

# Where the number that stands on the paper actually lives, per voucher type.
# DATEV calls the two Belegfeld 1 and Belegfeld 2; ERPNext keeps them under
# names of its own, and only for the voucher types that can carry them.
DOCUMENT_NUMBER_FIELDS = {
	"Journal Entry": ("bill_no", "cheque_no"),
	"Purchase Invoice": ("bill_no", None),
}

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


def document_number(voucher_type: str, fields: dict) -> tuple[str, str]:
	"""The two document fields of a voucher, as DATEV knows them.

	Belegfeld 1 is the number on the paper -- an incoming invoice keeps the
	supplier's number, not ours. Empty stays empty here: a voucher that
	carries no such number has none, and saying otherwise would put a figure
	in an audit package that no document supports.
	"""
	first_field, second_field = DOCUMENT_NUMBER_FIELDS.get(voucher_type, (None, None))
	first = (fields.get(first_field) or "").strip() if first_field else ""
	second = (fields.get(second_field) or "").strip() if second_field else ""

	return (first, second)


def contra_accounts(against: str | None) -> str:
	"""The contra account of a line, shortened the way a sheet shows it.

	A line booked against several accounts names the first and says how many
	others there are. The full list is one click away on the voucher, and a
	column that grows without limit makes the sheet unreadable.
	"""
	accounts = [entry.strip() for entry in (against or "").split(",") if entry.strip()]
	if not accounts:
		return ""

	if len(accounts) == 1:
		return accounts[0]

	return f"{accounts[0]} (+{len(accounts) - 1})"
