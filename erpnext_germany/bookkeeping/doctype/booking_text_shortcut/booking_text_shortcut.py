# Copyright (c) 2026, ALYF GmbH and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class BookingTextShortcut(Document):
	"""A short code that expands into a booking text while typing.

	The same idea as the text constants in DATEV: recurring texts are typed
	twice, not twenty times.
	"""

	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		disabled: DF.Check
		shortcut: DF.Data
		text: DF.Data
	# end: auto-generated types

	def validate(self):
		# Matched case insensitively while typing, so the stored form is
		# unambiguous.
		self.shortcut = (self.shortcut or "").strip().upper()

		if not self.shortcut:
			frappe.throw(frappe._("A shortcut cannot be empty."))
