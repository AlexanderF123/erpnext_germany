# Copyright (c) 2026, ALYF GmbH and contributors
# For license information, please see license.txt

"""One way into the ledger for every German evaluation.

The Summen- und Saldenliste is the account-by-account proof behind the BWA,
and the Kontoblatt is the proof behind the Summen- und Saldenliste. All three
have to agree to the cent, and a tax advisor will check exactly that. The
surest way to make them agree is to give them one and the same reading of the
ledger -- which entries are in scope at all -- rather than three that happen
to look alike today.

Totals come from here. A report that reads rows rather than totals runs a
query of its own, but it cuts that query with the same ``LedgerScope``, so the
sheet and the figure it was opened from cannot drift apart.
"""

from datetime import date
from typing import NamedTuple

import frappe
from frappe.query_builder.functions import Sum
from frappe.utils.nestedset import get_descendants_of


class LedgerScope(NamedTuple):
	"""Which ledger entries an evaluation is asking about.

	One named model rather than a row of optional arguments, because
	``get_totals(company, None, from_date, to_date, True)`` is not something a
	reader can check, and because the Kontoblatt has to cut its own query the
	same way this one is cut or the two answer different questions.

	Both date bounds are inclusive. ``None`` anywhere means "no limit of that
	kind", which is how the opening balance asks for everything ever booked.
	"""

	company: str
	from_date: date | None = None
	to_date: date | None = None
	cost_centers: list[str] | None = None
	accounts: list[str] | None = None
	skip_period_closing: bool = False

	def apply(self, query, gl_entry):
		"""Cut a GL Entry query down to this scope.

		Cancelled entries are never in scope: they were taken back, and an
		evaluation that counted them would show turnover that did not happen.
		"""
		query = query.where((gl_entry.company == self.company) & (gl_entry.is_cancelled == 0))

		if self.from_date:
			query = query.where(gl_entry.posting_date >= self.from_date)

		if self.to_date:
			query = query.where(gl_entry.posting_date <= self.to_date)

		if self.skip_period_closing:
			query = query.where(gl_entry.voucher_type != "Period Closing Voucher")

		if self.cost_centers is not None:
			query = query.where(gl_entry.cost_center.isin(self.cost_centers))

		if self.accounts is not None:
			query = query.where(gl_entry.account.isin(self.accounts))

		return query


def get_totals(scope: LedgerScope) -> dict[str, frappe._dict]:
	"""Debit and credit totals per account, for the entries in scope."""
	gl_entry = frappe.qb.DocType("GL Entry")
	debit = Sum(gl_entry.debit_in_account_currency)
	credit = Sum(gl_entry.credit_in_account_currency)

	query = scope.apply(
		frappe.qb.from_(gl_entry)
		.select(gl_entry.account, debit.as_("debit"), credit.as_("credit"))
		.groupby(gl_entry.account),
		gl_entry,
	)

	return {row.account: row for row in query.run(as_dict=True)}


def get_cost_centers(cost_center: str | None) -> list[str] | None:
	"""The cost center including all of its descendants, or None for no filter."""
	if not cost_center:
		return None

	return [cost_center, *get_descendants_of("Cost Center", cost_center)]
