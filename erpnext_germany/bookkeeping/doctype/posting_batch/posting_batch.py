# Copyright (c) 2026, ALYF GmbH and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import format_date, getdate, now_datetime

from erpnext_germany.bookkeeping.lockdown import ensure_can_post
from erpnext_germany.bookkeeping.posting import split_amount, summarize

POSTED = "Posted"
OPEN = "Open"


class PostingBatch(Document):
	"""A collection of entries that is prepared before it reaches the ledger.

	Entries are typed, reviewed and corrected inside the batch without touching
	the books. Posting turns every line into its own Journal Entry, which keeps
	each document individually traceable and individually reversible.
	"""

	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from erpnext_germany.bookkeeping.doctype.posting_batch_entry.posting_batch_entry import (
			PostingBatchEntry,
		)

		company: DF.Link
		entries: DF.Table[PostingBatchEntry]
		entry_count: DF.Int
		fiscal_year: DF.Link
		from_date: DF.Date
		naming_series: DF.Literal["BATCH-.YYYY.-"]
		posted_by: DF.Link | None
		posted_on: DF.Datetime | None
		remarks: DF.SmallText | None
		status: DF.Literal["Open", "Posted"]
		title: DF.Data | None
		to_date: DF.Date
		total_credit: DF.Currency
		total_debit: DF.Currency
		voucher_circle: DF.Literal["", "Cash", "Bank", "Purchase Invoices", "Sales Invoices", "Other"]
	# end: auto-generated types

	def validate(self):
		self.validate_not_posted()
		self.validate_period()
		self.validate_entries()
		self.set_totals()
		self.set_title()

	def validate_not_posted(self):
		"""A posted batch is history. Corrections go through a general reversal.

		The stored state comes from the document Frappe loaded before this save,
		so the check sees what is actually in the books rather than what the
		caller handed in.
		"""
		if self.is_new():
			return

		previous = self.get_doc_before_save()
		if previous and previous.status == POSTED:
			frappe.throw(
				_("This batch has been posted and cannot be changed."),
				title=_("Batch Already Posted"),
			)

	def validate_period(self):
		if getdate(self.from_date) > getdate(self.to_date):
			frappe.throw(_("From Date must be on or before To Date."))

	def validate_entries(self):
		for entry in self.entries:
			self.validate_entry(entry)

	def validate_entry(self, entry):
		label = _("Row {0}").format(entry.idx)

		if entry.amount <= 0:
			frappe.throw(
				_("{0}: Amount must be greater than zero. Book a correction as a general reversal.").format(
					label
				)
			)

		posting_date = getdate(entry.posting_date)
		if not getdate(self.from_date) <= posting_date <= getdate(self.to_date):
			frappe.throw(
				_("{0}: Posting date {1} is outside the batch period.").format(
					label, format_date(posting_date)
				)
			)

		if entry.account == entry.against_account:
			frappe.throw(_("{0}: Account and contra account must be different.").format(label))

		for fieldname in ("account", "against_account"):
			self.validate_account(label, entry.get(fieldname))

	def validate_account(self, label: str, account: str):
		details = frappe.get_cached_value(
			"Account", account, ["company", "is_group", "disabled"], as_dict=True
		)
		if not details:
			return

		if details.company != self.company:
			frappe.throw(_("{0}: {1} does not belong to {2}.").format(label, account, self.company))

		if details.is_group:
			frappe.throw(_("{0}: {1} is a group account and cannot be posted to.").format(label, account))

		if details.disabled:
			frappe.throw(_("{0}: {1} is disabled.").format(label, account))

	def set_totals(self):
		self.total_debit, self.total_credit, _difference = summarize(self.entries)
		self.entry_count = len(self.entries)

	def set_title(self):
		if self.title:
			return

		circle = self.voucher_circle or _("Posting Batch")
		self.title = f"{circle} {format_date(self.from_date)} - {format_date(self.to_date)}"

	def on_trash(self):
		if self.status == POSTED:
			frappe.throw(
				_("A posted batch cannot be deleted."),
				title=_("Batch Already Posted"),
			)

	@frappe.whitelist()
	def post(self):
		"""Turn every entry into a submitted Journal Entry.

		Runs in one transaction: either the whole batch reaches the ledger or
		none of it does, so a batch can never end up half posted.
		"""
		self.check_permission("write")

		if self.status == POSTED:
			frappe.throw(_("This batch has already been posted."), title=_("Batch Already Posted"))

		if not self.entries:
			frappe.throw(_("There is nothing to post."))

		for entry in self.entries:
			ensure_can_post(self.company, entry.posting_date)

		for entry in self.entries:
			entry.journal_entry = self.create_journal_entry(entry).name

		self.status = POSTED
		self.posted_on = now_datetime()
		self.posted_by = frappe.session.user

		# Saved through the document, not written past it: validation, hooks and
		# the version history have to see this change like any other.
		self.save()

		frappe.msgprint(
			_("{0} entries posted.").format(len(self.entries)),
			title=_("Batch Posted"),
			indicator="green",
		)

		return self.name

	def create_journal_entry(self, entry):
		"""Create and submit the Journal Entry for a single batch line."""
		debit, credit = split_amount(entry.direction, entry.amount)

		journal_entry = frappe.new_doc("Journal Entry")
		journal_entry.voucher_type = "Journal Entry"
		journal_entry.company = self.company
		journal_entry.posting_date = entry.posting_date
		journal_entry.user_remark = entry.remark
		journal_entry.bill_no = entry.document_number
		journal_entry.cheque_no = entry.document_number_2

		# The amount applies to the account as entered; the contra account
		# always takes the opposite side.
		journal_entry.append(
			"accounts",
			{
				"account": entry.account,
				"cost_center": entry.cost_center,
				"debit_in_account_currency": debit,
				"credit_in_account_currency": credit,
				"user_remark": entry.remark,
			},
		)
		journal_entry.append(
			"accounts",
			{
				"account": entry.against_account,
				"cost_center": entry.cost_center,
				"debit_in_account_currency": credit,
				"credit_in_account_currency": debit,
				"user_remark": entry.remark,
			},
		)

		journal_entry.insert()
		journal_entry.submit()
		return journal_entry
