# Copyright (c) 2026, ALYF GmbH and contributors
# For license information, please see license.txt

"""General reversal (Generalumkehr) of a posted entry.

A posted entry is never deleted and never edited. It is reversed, and the
reversal says why. What sets a general reversal apart from an ordinary counter
posting is what it does to the turnover figures: an accountant who books 100 by
mistake and corrects it must not end the year with 200 of turnover on that
account and a balance of nil.

DATEV achieves that by booking the correction with a minus on the same side.
ERPNext cannot: its ledger stores debit and credit as positive amounts and
normalises a negative debit into a positive credit while writing the entry --
which is precisely the counter posting we are trying to avoid. Verified against
this ERPNext version rather than assumed.

So the minus lives one level up. The reversal is booked as the counter posting
the ledger can represent, and is marked as a reversal. Every evaluation in this
app then reads a reversal as a negative amount on the original side, which
reproduces the German figures exactly. Reports outside this app still see two
movements, because that is what the ledger holds.
"""

import frappe
from frappe import _
from frappe.query_builder import Case
from frappe.query_builder.functions import Sum

from erpnext_germany.bookkeeping.lockdown import ensure_can_post

REVERSAL_REMARK = "Generalumkehr"


@frappe.whitelist()
def reverse_entry(journal_entry: str, reason: str, posting_date: str | None = None) -> str:
	"""Reverse a posted entry and say why.

	The reversal is dated today by default, not on the original date: the
	period the mistake sits in is usually closed by the time it is found, and
	a correction belongs in the period it is made in.
	"""
	original = frappe.get_doc("Journal Entry", journal_entry)
	original.check_permission("submit")

	reason = (reason or "").strip()
	if not reason:
		frappe.throw(_("A reversal needs a reason."), title=_("Reason Required"))

	_validate_can_reverse(original)

	posting_date = posting_date or frappe.utils.nowdate()
	ensure_can_post(original.company, posting_date)

	reversal = _build_reversal(original, reason, posting_date)
	reversal.insert()
	reversal.submit()

	# Written through the document so the link is versioned like any other
	# change; both fields are editable after submit for exactly this purpose.
	original.general_reversal_by = reversal.name
	original.save()

	frappe.msgprint(
		_("Reversed by {0}.").format(frappe.utils.get_link_to_form("Journal Entry", reversal.name)),
		title=_("Entry Reversed"),
		indicator="green",
	)

	return reversal.name


def _validate_can_reverse(original):
	if original.docstatus != 1:
		frappe.throw(_("Only a posted entry can be reversed."))

	if original.get("general_reversal_by"):
		frappe.throw(
			_("This entry was already reversed by {0}.").format(original.general_reversal_by),
			title=_("Already Reversed"),
		)

	if original.get("general_reversal_of"):
		# Reversing a reversal would leave two entries that each claim to undo
		# the other. A correction of a correction is a new booking.
		frappe.throw(
			_("A reversal cannot itself be reversed. Book the correction as a new entry."),
			title=_("Already A Reversal"),
		)


def _build_reversal(original, reason: str, posting_date: str):
	reversal = frappe.new_doc("Journal Entry")
	reversal.voucher_type = original.voucher_type
	reversal.company = original.company
	reversal.posting_date = posting_date
	reversal.bill_no = original.bill_no
	reversal.cheque_no = original.cheque_no
	reversal.cheque_date = original.cheque_date
	reversal.general_reversal_of = original.name
	reversal.reversal_reason = reason
	reversal.user_remark = f"{REVERSAL_REMARK}: {reason}"

	for row in original.accounts:
		reversal.append(
			"accounts",
			{
				"account": row.account,
				"party_type": row.party_type,
				"party": row.party,
				"cost_center": row.cost_center,
				# Same accounts, opposite sides: the only reversal the ledger
				# can hold. The minus is applied when reading, not when writing.
				"debit_in_account_currency": row.credit_in_account_currency,
				"credit_in_account_currency": row.debit_in_account_currency,
				"user_remark": row.user_remark,
			},
		)

	return reversal


def reversal_vouchers(company: str):
	"""The reversals of this company, as a subquery over voucher names.

	A subquery rather than a list of names: an evaluation asks this question
	inside a ledger aggregate, and handing thousands of names back through
	Python only to send them out again would be the slow way round.
	"""
	journal_entry = frappe.qb.DocType("Journal Entry")
	return (
		frappe.qb.from_(journal_entry)
		.select(journal_entry.name)
		.where(journal_entry.company == company)
		.where(journal_entry.docstatus == 1)
		.where(journal_entry.general_reversal_of.notnull())
		.where(journal_entry.general_reversal_of != "")
	)


def reversal_sides(gl_entry, company: str) -> tuple:
	"""Debit and credit of a single ledger row, read the German way.

	An ordinary entry counts on the side it was booked on. A reversal counts
	as a minus on the opposite side -- the side the mistake was booked on --
	so correcting a booking of 100 leaves the account at nil turnover instead
	of 100 debit and 100 credit.

	Per row rather than per total, because a Kontoblatt shows the rows and an
	evaluation shows the totals, and the two are only the same books if they
	are the same reading. A sheet that shows a reversal as a credit while the
	Summen- und Saldenliste counts it as a negative debit agrees on the
	balance and disagrees on the turnover -- and the turnover is the figure a
	tax advisor compares.
	"""
	# The voucher type is part of the test as well: a name only identifies a
	# document together with its doctype.
	is_reversal = (gl_entry.voucher_type == "Journal Entry") & gl_entry.voucher_no.isin(
		reversal_vouchers(company)
	)

	debit = (
		Case()
		.when(is_reversal, 0 - gl_entry.credit_in_account_currency)
		.else_(gl_entry.debit_in_account_currency)
	)
	credit = (
		Case()
		.when(is_reversal, 0 - gl_entry.debit_in_account_currency)
		.else_(gl_entry.credit_in_account_currency)
	)

	return debit, credit


def reversal_links(names: list[str]) -> dict[str, str]:
	"""Which of these Journal Entries reverse another one, and which.

	Asked here rather than alongside the document numbers, because a reversal
	link is not something written on a document -- it is what this module
	knows and nothing else does.
	"""
	if not names:
		return {}

	return {
		row.name: row.general_reversal_of
		for row in frappe.get_all(
			"Journal Entry",
			filters={"name": ("in", sorted(names)), "general_reversal_of": ("is", "set")},
			fields=["name", "general_reversal_of"],
		)
	}


def net_of_reversals(gl_entry, company: str) -> tuple:
	"""The same reading, summed over an aggregate."""
	debit, credit = reversal_sides(gl_entry, company)
	return Sum(debit), Sum(credit)


def set_reversal_reason_mandatory(doc, method=None):
	"""A reversal without a reason is not auditable."""
	if doc.get("general_reversal_of") and not (doc.get("reversal_reason") or "").strip():
		frappe.throw(_("A reversal needs a reason."), title=_("Reason Required"))
