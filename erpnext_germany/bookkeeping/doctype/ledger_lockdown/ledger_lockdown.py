# Copyright (c) 2026, ALYF GmbH and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.query_builder.functions import Count, Sum
from frappe.utils import format_date, getdate, now_datetime

from erpnext_germany.bookkeeping.lockdown import clear_lockdown_cache, get_locked_up_to


class LedgerLockdown(Document):
	"""Closes a period: everything posted up to a date becomes unchangeable.

	A lockdown is a record of fact, not a setting. It cannot be edited or
	deleted once written, and it records the control totals of the period it
	closed so that a later audit can tell whether the ledger still matches.
	Corrections after a lockdown are booked as a general reversal.
	"""

	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		company: DF.Link
		entry_count: DF.Int
		locked_by: DF.Link | None
		locked_on: DF.Datetime | None
		locked_up_to: DF.Date
		remarks: DF.SmallText | None
		title: DF.Data | None
		total_credit: DF.Currency
		total_debit: DF.Currency
	# end: auto-generated types

	def validate(self):
		if not self.is_new():
			frappe.throw(
				_("A lockdown cannot be changed. Create a new one to close a later period."),
				title=_("Lockdown Is Final"),
			)

		self.validate_direction()
		self.set_control_totals()
		self.set_title()

	def validate_direction(self):
		"""A lockdown may only move forward. Reopening a closed period is not a save."""
		previous = get_locked_up_to(self.company)
		if previous and getdate(self.locked_up_to) <= previous:
			frappe.throw(
				_("{0} is already locked up to {1}. A lockdown can only move forward.").format(
					self.company, format_date(previous)
				),
				title=_("Period Already Locked"),
			)

	def set_control_totals(self):
		totals = get_ledger_totals(self.company, self.locked_up_to)
		self.entry_count = totals.entry_count or 0
		self.total_debit = totals.total_debit or 0
		self.total_credit = totals.total_credit or 0

	def set_title(self):
		self.title = f"{self.company} — {format_date(self.locked_up_to)}"

	def before_insert(self):
		self.locked_on = now_datetime()
		self.locked_by = frappe.session.user

	def on_update(self):
		clear_lockdown_cache(self.company)

	def on_trash(self):
		frappe.throw(
			_("A lockdown cannot be deleted. It is the record that a period was closed."),
			title=_("Lockdown Is Final"),
		)


def get_ledger_totals(company: str, up_to_date) -> frappe._dict:
	"""Return entry count and debit/credit totals of the period being closed.

	Aggregated in the database on purpose: a closed period can hold hundreds of
	thousands of ledger entries, and loading them as documents to add up two
	columns would be the wrong tool. Nothing is written here.
	"""
	gl_entry = frappe.qb.DocType("GL Entry")

	rows = (
		frappe.qb.from_(gl_entry)
		.select(
			Count(gl_entry.name).as_("entry_count"),
			Sum(gl_entry.debit).as_("total_debit"),
			Sum(gl_entry.credit).as_("total_credit"),
		)
		.where(
			(gl_entry.company == company)
			& (gl_entry.is_cancelled == 0)
			& (gl_entry.posting_date <= up_to_date)
		)
	).run(as_dict=True)

	return rows[0] if rows else frappe._dict()
