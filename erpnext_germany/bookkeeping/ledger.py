# Copyright (c) 2026, ALYF GmbH and contributors
# For license information, please see license.txt

"""One way into the ledger for every German evaluation.

The Summen- und Saldenliste is the account-by-account proof behind the BWA;
the two have to agree to the cent, and a tax advisor will check exactly that.
The surest way to make them agree is to give them one and the same reading of
the ledger, including how a general reversal is counted, rather than two that
happen to look alike today.
"""

from datetime import date

import frappe
from frappe.utils.nestedset import get_descendants_of

from erpnext_germany.bookkeeping.reversal import net_of_reversals


def get_totals(
	company: str,
	cost_centers: list[str] | None = None,
	from_date: date | None = None,
	to_date: date | None = None,
	skip_period_closing: bool = False,
) -> dict[str, frappe._dict]:
	"""Debit and credit totals per account for the given period.

	Both bounds are inclusive. A general reversal is read as a minus on the
	side of the entry it undoes, so a corrected mistake leaves the turnover
	figures where they were instead of inflating both sides.
	"""
	gl_entry = frappe.qb.DocType("GL Entry")
	debit, credit = net_of_reversals(gl_entry, company)

	query = (
		frappe.qb.from_(gl_entry)
		.select(gl_entry.account, debit.as_("debit"), credit.as_("credit"))
		.where((gl_entry.company == company) & (gl_entry.is_cancelled == 0))
		.groupby(gl_entry.account)
	)

	if from_date:
		query = query.where(gl_entry.posting_date >= from_date)

	if to_date:
		query = query.where(gl_entry.posting_date <= to_date)

	if skip_period_closing:
		query = query.where(gl_entry.voucher_type != "Period Closing Voucher")

	if cost_centers is not None:
		query = query.where(gl_entry.cost_center.isin(cost_centers))

	return {row.account: row for row in query.run(as_dict=True)}


def get_cost_centers(cost_center: str | None) -> list[str] | None:
	"""The cost center including all of its descendants, or None for no filter."""
	if not cost_center:
		return None

	return [cost_center, *get_descendants_of("Cost Center", cost_center)]
