# Copyright (c) 2026, ALYF GmbH and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class BWARow(Document):
	"""One line of a BWA form.

	Either a line that covers accounts, or a result line that adds up the
	account lines above it, or a ratio that puts one against another. What a
	line may say follows from its type; the form as a whole is checked on the
	BWA Schema, where the lines can be seen together.
	"""

	pass
