# Copyright (c) 2026, ALYF GmbH and contributors
# For license information, please see license.txt

"""Server side of the fast entry screen.

The screen is built for typing, not for clicking: one line per booking, a
fixed tab order and no round trip that the typist has to wait for. That shapes
this module in two ways.

Everything the line needs to resolve while typing -- the chart of accounts,
the tax keys, the text shortcuts -- is handed over once when the screen opens,
so looking up an account by number or by name never touches the server and
stays inside the reaction time a keyboard user notices.

Everything that changes the batch goes through the document, never past it, so
a line typed here is validated and taxed exactly like one typed in the form.
"""

import frappe
from frappe import _

from erpnext_germany.bookkeeping.account_search import get_accounts
from erpnext_germany.bookkeeping.doctype.posting_batch.posting_batch import OPEN

ENTRY_FIELDS = (
	"posting_date",
	"amount",
	"direction",
	"account",
	"against_account",
	"tax_key",
	"document_number",
	"document_number_2",
	"cost_center",
	"remark",
)

ROW_FIELDS = (
	"name",
	"idx",
	*ENTRY_FIELDS,
	"applied_tax_key",
	"net_amount",
	"tax_amount",
	"tax_account",
)


@frappe.whitelist()
def get_context(batch: str) -> dict:
	"""Everything the screen needs to run without asking again."""
	doc = _get_batch(batch, "read")

	return {
		"batch": {
			"name": doc.name,
			"title": doc.title,
			"company": doc.company,
			"from_date": str(doc.from_date),
			"to_date": str(doc.to_date),
			"status": doc.status,
		},
		"accounts": get_accounts(doc.company),
		"tax_keys": get_tax_keys(),
		"text_shortcuts": get_text_shortcuts(),
		"cost_centers": get_cost_centers(doc.company),
		"rows": [_row(entry) for entry in doc.entries],
		"totals": _totals(doc),
	}


def get_tax_keys() -> list[dict]:
	keys = frappe.get_all(
		"Tax Key",
		filters={"disabled": 0},
		fields=["name", "key_number", "rate", "effect"],
		order_by="key_number asc",
	)

	return [dict(key) for key in keys]


def get_cost_centers(company: str) -> list[str]:
	return frappe.get_all(
		"Cost Center",
		filters={"company": company, "is_group": 0, "disabled": 0},
		pluck="name",
		order_by="name asc",
	)


def get_text_shortcuts() -> dict:
	"""Short codes that expand into a booking text while typing."""
	shortcuts = frappe.get_all(
		"Booking Text Shortcut",
		filters={"disabled": 0},
		fields=["shortcut", "text"],
	)

	return {row.shortcut.upper(): row.text for row in shortcuts}


@frappe.whitelist()
def add_entry(batch: str, row: dict | str) -> dict:
	"""Append one typed line to the batch."""
	doc = _get_batch(batch, "write")
	entry = doc.append("entries", _clean(row))
	doc.save()

	return {"row": _row(doc.entries[entry.idx - 1]), "totals": _totals(doc)}


@frappe.whitelist()
def update_entry(batch: str, row_name: str, row: dict | str) -> dict:
	"""Correct a line that is still in the batch."""
	doc = _get_batch(batch, "write")
	entry = _find(doc, row_name)
	entry.update(_clean(row))
	doc.save()

	return {"row": _row(entry), "totals": _totals(doc)}


@frappe.whitelist()
def remove_entry(batch: str, row_name: str) -> dict:
	doc = _get_batch(batch, "write")
	doc.entries.remove(_find(doc, row_name))
	doc.save()

	return {"totals": _totals(doc)}


def _get_batch(batch: str, permission: str):
	doc = frappe.get_doc("Posting Batch", batch)
	doc.check_permission(permission)

	if permission == "write" and doc.status != OPEN:
		frappe.throw(
			_("This batch has been posted and cannot be changed."),
			title=_("Batch Already Posted"),
		)

	return doc


def _find(doc, row_name: str):
	for entry in doc.entries:
		if entry.name == row_name:
			return entry

	frappe.throw(_("This line is no longer part of the batch."))


def _clean(row: dict | str) -> dict:
	"""Keep only the fields the screen is allowed to set.

	Net, tax and the tax accounts are derived on save; letting the browser
	send them would make the ledger depend on what a client believed.
	"""
	if isinstance(row, str):
		row = frappe.parse_json(row)

	return {field: row.get(field) for field in ENTRY_FIELDS if row.get(field) not in (None, "")}


def _row(entry) -> dict:
	return {field: entry.get(field) for field in ROW_FIELDS}


def _totals(doc) -> dict:
	return {
		"entry_count": doc.entry_count,
		"total_amount": doc.total_amount,
		"total_net_amount": doc.total_net_amount,
		"total_tax_amount": doc.total_tax_amount,
		"target_amount": doc.target_amount,
		"difference": doc.difference,
	}
