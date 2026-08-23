# Copyright (c) 2026, ALYF GmbH and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class TaxKeyAccount(Document):
	"""The account a tax key books its tax to, in one company."""

	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		company: DF.Link
		deductible_tax_account: DF.Link | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		tax_account: DF.Link
	# end: auto-generated types

	pass
