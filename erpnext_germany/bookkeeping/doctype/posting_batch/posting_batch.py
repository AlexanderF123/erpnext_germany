# Copyright (c) 2026, ALYF GmbH and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, format_date, getdate, now_datetime

from erpnext_germany.bookkeeping.lockdown import ensure_can_post
from erpnext_germany.bookkeeping.party import apply_party, validate_party
from erpnext_germany.bookkeeping.posting import flip, split_amount
from erpnext_germany.bookkeeping.tax_derivation import derive_tax

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
		difference: DF.Currency
		entries: DF.Table[PostingBatchEntry]
		entry_count: DF.Int
		fiscal_year: DF.Link
		from_date: DF.Date
		naming_series: DF.Literal["BATCH-.YYYY.-"]
		posted_by: DF.Link | None
		posted_on: DF.Datetime | None
		remarks: DF.SmallText | None
		status: DF.Literal["Open", "Posted"]
		target_amount: DF.Currency
		title: DF.Data | None
		to_date: DF.Date
		total_amount: DF.Currency
		total_net_amount: DF.Currency
		total_tax_amount: DF.Currency
		voucher_circle: DF.Literal["", "Cash", "Bank", "Purchase Invoices", "Sales Invoices", "Other"]
	# end: auto-generated types

	def validate(self):
		self.validate_not_posted()
		self.validate_period()
		self.run_method("enrich_entries")
		self.set_parties()
		# Frappe checks link fields before it runs validate, so anything filled
		# in above would otherwise never be checked against what it points at.
		# Checked with Frappe's own machinery rather than by hand, so a derived
		# value faces exactly the check a typed one faces.
		self._validate_links()
		self.validate_entries()
		self.set_totals()
		self.set_title()

	def set_parties(self):
		"""Work out whose account each line touches.

		Before the link check rather than inside validate_entry: `party` is a
		dynamic link and Frappe cannot check it until `party_type` stands next
		to it. What the derivation produced is then checked like anything else.
		"""
		for entry in self.entries:
			apply_party(entry, _("Row {0}").format(entry.idx))

	def enrich_entries(self):
		"""Where another app fills in what only it can know.

		This module knows what a booking is. It does not know that account
		4830 on this line belongs to a particular building, or which lease a
		supplier invoice came out of -- that is knowledge of the app that
		manages the properties, and putting it here would make a regional
		bookkeeping module depend on one industry.

		So the line has a hook rather than an answer. An app hooks
		``doc_events`` on "Posting Batch" for this method and fills whatever
		it can on ``self.entries`` -- in practice the cost center, which is
		how an object is told apart in the ledger; anything it leaves alone
		stays as typed.

		Deliberately before the entries are validated: a cost center derived
		here has to face the same checks as one typed by hand, or a derived
		value would be the one thing in the batch nobody looked at.
		"""

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

		validate_party(entry, self.company, label)
		self.set_tax(entry, label)

	def set_tax(self, entry, label: str):
		"""Derive net, tax and tax account from the key of the account or line.

		Written onto the line so the split is visible while typing and stays
		readable afterwards, instead of being recomputed at posting time out of
		master data that may have moved on since.
		"""
		derived = derive_tax(
			account=entry.account,
			tax_key=entry.tax_key,
			amount=entry.amount,
			company=self.company,
			posting_date=entry.posting_date,
			label=label,
		)

		# The typed key stays as typed -- empty means the account decided, which
		# is how a DATEV booking line reads. What actually applied is recorded
		# separately, so an override can be traced afterwards.
		entry.applied_tax_key = derived.tax_key
		entry.net_amount = derived.net
		entry.tax_amount = derived.tax
		entry.tax_account = derived.tax_account
		entry.deductible_tax_account = derived.deductible_tax_account

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
		"""Control totals of the batch: how many entries and how much in total.

		Debit and credit sums are deliberately not shown. Every entry is a
		complete double entry, so both would always equal the total amount and
		their difference would always be zero -- two columns that can never
		disagree are not a control, they are noise.

		The one figure that can disagree is the difference to a target somebody
		wrote down beforehand, so that is the one worth showing.
		"""
		self.entry_count = len(self.entries)
		self.total_amount = sum(flt(entry.amount) for entry in self.entries)
		self.total_net_amount = sum(flt(entry.net_amount) for entry in self.entries)
		self.total_tax_amount = sum(flt(entry.tax_amount) for entry in self.entries)
		self.difference = difference(self.target_amount, self.total_amount)

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
		journal_entry = frappe.new_doc("Journal Entry")
		journal_entry.voucher_type = "Journal Entry"
		journal_entry.company = self.company
		journal_entry.posting_date = entry.posting_date
		journal_entry.user_remark = entry.remark
		journal_entry.bill_no = entry.document_number
		journal_entry.cheque_no = entry.document_number_2
		if entry.document_number_2:
			# ERPNext refuses a reference number without a date. Belegfeld 2 has no
			# date of its own in DATEV, so the booking date stands in -- which is
			# also the only date the line was ever given.
			journal_entry.cheque_date = entry.posting_date

		for account, debit, credit in self.get_ledger_rows(entry):
			row = {
				"account": account,
				"cost_center": entry.cost_center,
				"debit_in_account_currency": debit,
				"credit_in_account_currency": credit,
				"user_remark": entry.remark,
			}
			# Only the row that actually hits the personal account carries the
			# person. Putting the party on the contra side would make ERPNext
			# settle against an account the party does not have.
			if entry.party_account and account == entry.party_account:
				row.update(
					{
						"party_type": entry.party_type,
						"party": entry.party,
						"reference_type": entry.reference_type,
						"reference_name": entry.reference_name,
					}
				)

			journal_entry.append("accounts", row)

		journal_entry.insert()
		journal_entry.submit()
		return journal_entry

	def get_ledger_rows(self, entry) -> list[tuple[str, float, float]]:
		"""The ledger rows one batch line turns into.

		Without tax this is the plain double entry. With input or output tax the
		account keeps the net, the tax account takes the tax on the same side and
		the contra account settles the gross -- exactly how the amount reads on
		the document. Under reverse charge nothing extra passes between the two
		accounts; the tax owed and the deductible input tax are added as their
		own pair, which is what makes the entry balance again.
		"""
		net = flt(entry.net_amount)
		tax = flt(entry.tax_amount)

		# A deductible tax account is set exactly for reverse charge, where the
		# tax is settled between the two tax accounts instead of riding along
		# with the amount.
		reverse_charge = bool(entry.deductible_tax_account)
		tax_in_amount = tax if tax and entry.tax_account and not reverse_charge else 0.0

		rows = [(entry.account, *split_amount(entry.direction, net))]

		if tax_in_amount:
			rows.append((entry.tax_account, *split_amount(entry.direction, tax_in_amount)))

		rows.append((entry.against_account, *flip(split_amount(entry.direction, net + tax_in_amount))))

		if tax and reverse_charge:
			rows.append((entry.tax_account, *flip(split_amount(entry.direction, tax))))
			rows.append((entry.deductible_tax_account, *split_amount(entry.direction, tax)))

		return rows


def difference(target: float, total: float) -> float:
	"""How far a batch is from what it was supposed to add up to.

	Without a target there is nothing to be off by, and a difference equal to
	the whole batch would read as an error where none was claimed.
	"""
	if not flt(target):
		return 0.0

	return flt(target) - flt(total)
