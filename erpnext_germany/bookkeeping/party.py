# Copyright (c) 2026, ALYF GmbH and contributors
# For license information, please see license.txt

"""Which side of a line is a person, and which of their invoices it settles.

Two things that belong together and were both missing.

ERPNext refuses a ledger entry on a receivable or payable account unless it
names a party. Until a batch line could name one, it simply could not book
against a debtor or a creditor -- the whole side of bookkeeping that a
property manager spends most of its time in.

The second is the offene Posten. A payment that lands on the right account
but does not point at the invoice it settles leaves that invoice open, and
the tenant keeps being dunned for money they have already paid. Pointing at
it is what turns a posting into a settlement.

The line never asks which kind of party it is dealing with. That follows from
the account: a receivable account is a customer, a payable account is a
supplier. Asking would be asking somebody to repeat what they already said by
choosing the account.
"""

from typing import NamedTuple

import frappe
from frappe import _

RECEIVABLE = "Receivable"
PAYABLE = "Payable"

# What kind of person sits behind each kind of account, and which document of
# theirs a booking can settle.
PARTY_TYPES = {RECEIVABLE: "Customer", PAYABLE: "Supplier"}
OPEN_ITEM_TYPES = {"Customer": "Sales Invoice", "Supplier": "Purchase Invoice"}


class DerivedParty(NamedTuple):
	"""The party side of a line, as far as the accounts alone decide it."""

	account: str | None
	party_type: str | None
	reference_type: str | None

	@property
	def wanted(self) -> bool:
		"""Whether this line has to name a party at all."""
		return bool(self.account)


def party_account_type(account: str | None) -> str | None:
	"""Receivable or Payable, where the account is one of those."""
	if not account:
		return None

	kind = frappe.get_cached_value("Account", account, "account_type")
	return kind if kind in PARTY_TYPES else None


def derive_party(account: str, against_account: str, label: str = "") -> DerivedParty:
	"""Find the person's side of the line, if there is one.

	Exactly one of the two accounts may be a personal account. Both would be a
	transfer between two people, which is two bookings and not one, and no
	single party field could describe it honestly.
	"""
	kinds = {name: party_account_type(name) for name in (account, against_account)}
	personal = [name for name, kind in kinds.items() if kind]

	if len(personal) > 1:
		frappe.throw(
			_("{0}: Only one side of a booking can be a personal account.").format(label)
			if label
			else _("Only one side of a booking can be a personal account.")
		)

	if not personal:
		return DerivedParty(None, None, None)

	party_account = personal[0]
	party_type = PARTY_TYPES[kinds[party_account]]
	return DerivedParty(party_account, party_type, OPEN_ITEM_TYPES[party_type])


def apply_party(entry, label: str = ""):
	"""Write the party side of a line onto the line, and check what was given.

	Neither `party_type` nor `reference_type` is filled in here -- both are
	checked. Frappe validates a dynamic link before it runs any hook of ours,
	so a value that arrives without its type is refused by the framework long
	before this code sees it. Both therefore come in as a pair, the same rule
	a Journal Entry Account has carried for as long as ERPNext has existed;
	the form fills them in as soon as an account is chosen.

	What this does own is the answer the accounts imply: which of the two is
	the personal one, and which kind of document it can settle.
	"""
	derived = derive_party(entry.account, entry.against_account, label)

	entry.party_account = derived.account

	if not derived.wanted:
		# A line that stopped touching a personal account must not keep a
		# person, or the ledger would carry a party nothing points at.
		entry.party_type = None
		entry.party = None
		entry.reference_type = None
		entry.reference_name = None
		return

	check_type(entry.party_type, derived.party_type, derived.account, label)
	entry.party_type = derived.party_type

	if not entry.reference_name:
		entry.reference_type = None
		return

	check_type(entry.reference_type, derived.reference_type, derived.account, label)
	entry.reference_type = derived.reference_type


def check_type(given: str | None, expected: str, account: str, label: str):
	"""Refuse a type that contradicts what the account says.

	Correcting it silently would be worse: somebody chose the wrong one, and
	the booking they get would not be the booking they described.

	Both names are run through `_()` because they are DocType names, which
	Frappe translates -- otherwise a German message would end in English.
	"""
	if given and given != expected:
		frappe.throw(_("{0}: {1} implies {2}, not {3}.").format(label, account, _(expected), _(given)))


def validate_party(entry, company: str, label: str):
	"""A personal account needs a person, and nothing else may claim one.

	Reads what `apply_party` wrote rather than deriving again, so the check and
	the posting can never be looking at two different answers.
	"""
	if entry.party_account and not entry.party:
		frappe.throw(
			_("{0}: {1} is a personal account and needs a party.").format(label, entry.party_account)
		)

	if not entry.party_account and entry.party:
		frappe.throw(
			_("{0}: Neither account is a personal account, so there is nobody to book against.").format(label)
		)

	if entry.reference_name:
		validate_open_item(entry, company, label)


def validate_open_item(entry, company: str, label: str):
	"""The document being settled has to be this party's, and still open.

	Checked here rather than left to ERPNext, because ERPNext would accept the
	reference and quietly settle nothing. A wrong open item is not a posting
	error, it is a dunning letter three weeks later.
	"""
	if not entry.party_account:
		frappe.throw(_("{0}: An open item needs a personal account.").format(label))

	document = frappe.db.get_value(
		entry.reference_type,
		entry.reference_name,
		["company", "docstatus", "outstanding_amount", party_field(entry.party_type)],
		as_dict=True,
	)
	if not document:
		frappe.throw(
			_("{0}: {1} {2} does not exist.").format(label, entry.reference_type, entry.reference_name)
		)

	if document.company != company:
		frappe.throw(_("{0}: {1} belongs to another company.").format(label, entry.reference_name))

	if document.docstatus != 1:
		frappe.throw(_("{0}: {1} is not posted.").format(label, entry.reference_name))

	if document.get(party_field(entry.party_type)) != entry.party:
		frappe.throw(_("{0}: {1} does not belong to {2}.").format(label, entry.reference_name, entry.party))

	if not document.outstanding_amount:
		frappe.throw(_("{0}: {1} is already settled.").format(label, entry.reference_name))


def party_field(party_type: str) -> str:
	return "customer" if party_type == "Customer" else "supplier"


@frappe.whitelist()
def get_open_items(company: str, party_type: str, party: str) -> list[dict]:
	"""This party's unsettled documents, oldest first.

	Oldest first because that is the order they are settled in unless somebody
	says otherwise, so the one being looked for is usually near the top.
	"""
	reference_type = OPEN_ITEM_TYPES.get(party_type)
	if not reference_type or not party:
		return []

	frappe.has_permission(reference_type, throw=True)

	rows = frappe.get_all(
		reference_type,
		filters={
			"company": company,
			party_field(party_type): party,
			"docstatus": 1,
			"outstanding_amount": ("!=", 0),
		},
		fields=["name", "posting_date", "due_date", "grand_total", "outstanding_amount"],
		order_by="due_date asc, posting_date asc",
		limit=50,
	)

	return [dict(row) for row in rows]
