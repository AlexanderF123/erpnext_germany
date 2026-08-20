# Copyright (c) 2026, ALYF GmbH and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from erpnext_germany.bookkeeping.tax import EFFECTS, REVERSE_CHARGE, TAX_FREE


class TaxKey(Document):
	"""A tax key as an accountant knows it from DATEV.

	Rate and effect follow from the law and are therefore the same in every
	company; only the account the tax lands on depends on the chart of
	accounts, which is why the accounts sit in a child table instead of on the
	key itself. The same key feeds the derivation during entry and the DATEV
	export, so the two can never drift apart.
	"""

	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from erpnext_germany.bookkeeping.doctype.tax_key_account.tax_key_account import TaxKeyAccount

		accounts: DF.Table[TaxKeyAccount]
		description: DF.SmallText | None
		disabled: DF.Check
		effect: DF.Literal["Input Tax", "Output Tax", "Reverse Charge", "Tax Free"]
		key_number: DF.Data
		rate: DF.Percent
		tax_key_name: DF.Data
		valid_from: DF.Date | None
	# end: auto-generated types

	def validate(self):
		self.validate_effect()
		self.validate_rate()
		self.validate_accounts()

	def validate_effect(self):
		if self.effect not in EFFECTS:
			frappe.throw(_("{0} is not a known tax effect.").format(self.effect))

		if self.effect == TAX_FREE and self.rate:
			frappe.throw(_("A tax free key cannot carry a tax rate."))

	def validate_rate(self):
		if not 0 <= self.rate <= 100:
			frappe.throw(_("The tax rate must be between 0 and 100 percent."))

	def validate_accounts(self):
		seen = set()
		for row in self.accounts:
			if row.company in seen:
				frappe.throw(
					_("Row {0}: {1} already has a tax account for this key.").format(row.idx, row.company)
				)
			seen.add(row.company)

			if self.effect == REVERSE_CHARGE and not row.deductible_tax_account:
				frappe.throw(
					_(
						"Row {0}: Reverse charge needs a deductible tax account as well, otherwise the"
						" entry does not balance."
					).format(row.idx)
				)

			if self.effect != REVERSE_CHARGE and row.deductible_tax_account:
				frappe.throw(
					_("Row {0}: A deductible tax account only applies to reverse charge.").format(row.idx)
				)

			for account in (row.tax_account, row.deductible_tax_account):
				self.validate_tax_account(row, account)

	def validate_tax_account(self, row, account: str | None):
		if not account:
			return

		details = frappe.get_cached_value("Account", account, ["company", "is_group"], as_dict=True)
		if not details:
			return

		if details.company != row.company:
			frappe.throw(_("Row {0}: {1} does not belong to {2}.").format(row.idx, account, row.company))

		if details.is_group:
			frappe.throw(
				_("Row {0}: {1} is a group account and cannot be posted to.").format(row.idx, account)
			)

	def get_accounts_for(self, company: str):
		"""The tax accounts this key uses in one company, or None."""
		for row in self.accounts:
			if row.company == company:
				return row

		return None
