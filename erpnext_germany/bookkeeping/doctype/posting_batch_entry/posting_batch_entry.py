# Copyright (c) 2026, ALYF GmbH and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class PostingBatchEntry(Document):
	"""One line of a posting batch: a complete double entry.

	The amount is entered once, together with the side it applies to the
	account. The contra account always receives the opposite side, so a line is
	balanced by construction and can be typed without leaving the keyboard.

	Net, tax and tax account are never typed. They follow from the tax key of
	the account, or from the key on the line where the booking deviates from it.
	"""

	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		account: DF.Link
		applied_tax_key: DF.Link | None
		against_account: DF.Link
		amount: DF.Currency
		cost_center: DF.Link | None
		deductible_tax_account: DF.Link | None
		direction: DF.Literal["Debit", "Credit"]
		document_number: DF.Data | None
		document_number_2: DF.Data | None
		journal_entry: DF.Link | None
		net_amount: DF.Currency
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		party: DF.DynamicLink | None
		party_account: DF.Link | None
		party_type: DF.Link | None
		posting_date: DF.Date
		reference_name: DF.DynamicLink | None
		reference_type: DF.Link | None
		remark: DF.Data | None
		tax_account: DF.Link | None
		tax_amount: DF.Currency
		tax_key: DF.Link | None
	# end: auto-generated types

	pass
