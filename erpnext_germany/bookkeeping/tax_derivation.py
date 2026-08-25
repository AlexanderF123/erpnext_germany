# Copyright (c) 2026, ALYF GmbH and contributors
# For license information, please see license.txt

"""Tax derivation against master data.

The one place that turns an account, an optional tax key and an amount into
net, tax and gross. Both the booking line and the DATEV export go through it,
so what an accountant sees while typing is by construction what leaves the
system at the end of the month.

The pure arithmetic lives in `tax.py`; this module only looks up the master
data around it.
"""

from typing import NamedTuple

import frappe
from frappe import _
from frappe.utils import getdate

from erpnext_germany.bookkeeping.tax import (
	REVERSE_CHARGE,
	TAX_FREE,
	TaxAmounts,
	resolve_tax_key,
	split_tax,
)


class DerivedTax(NamedTuple):
	"""What the tax key made of one amount."""

	tax_key: str | None
	effect: str | None
	rate: float
	tax_account: str | None
	deductible_tax_account: str | None
	net: float
	tax: float
	gross: float


def get_account_tax_key(account: str) -> str | None:
	"""The tax key that hangs on an account.

	This is the Automatikkonto principle: booking to a revenue or expense
	account is enough, the tax follows from the account.
	"""
	if not account:
		return None

	return frappe.get_cached_value("Account", account, "tax_key")


def derive_tax(
	account: str,
	tax_key: str | None,
	amount: float,
	company: str,
	posting_date=None,
	label: str | None = None,
) -> DerivedTax:
	"""Work out net, tax and gross for one booking line.

	`tax_key` is the exception typed on the line; leaving it empty falls back
	to the key on the account. Contradictions are refused here rather than
	silently resolved, because a booking that nobody can explain afterwards is
	worse than one that was rejected.
	"""
	resolved = resolve_tax_key(get_account_tax_key(account), tax_key)
	if not resolved:
		return DerivedTax(
			tax_key=None,
			effect=None,
			rate=0.0,
			tax_account=None,
			deductible_tax_account=None,
			net=amount,
			tax=0.0,
			gross=amount,
		)

	key = frappe.get_cached_doc("Tax Key", resolved)
	_validate_key_applies(key, tax_key, account, posting_date, label)

	amounts = _split(key, amount, label)
	accounts = _tax_accounts(key, company, amounts, label)

	return DerivedTax(
		tax_key=key.name,
		effect=key.effect,
		rate=key.rate,
		tax_account=accounts[0],
		deductible_tax_account=accounts[1],
		net=amounts.net,
		tax=amounts.tax,
		gross=amounts.gross,
	)


def _validate_key_applies(key, line_key, account, posting_date, label):
	if key.disabled:
		frappe.throw(_("{0}Tax key {1} is disabled.").format(_prefix(label), key.name))

	if posting_date and key.valid_from and getdate(posting_date) < getdate(key.valid_from):
		frappe.throw(
			_("{0}Tax key {1} only applies from {2}.").format(
				_prefix(label), key.name, frappe.format(key.valid_from, {"fieldtype": "Date"})
			)
		)

	# Booking onto a tax account and taxing it again would report the tax
	# twice. The account is already the destination, it cannot also be the
	# source.
	if line_key and _is_tax_account(account):
		frappe.throw(
			_("{0}{1} is a tax account and cannot carry a tax key itself.").format(_prefix(label), account)
		)


def _split(key, amount: float, label) -> TaxAmounts:
	try:
		return split_tax(amount, key.rate, key.effect)
	except ValueError as error:
		frappe.throw(f"{_prefix(label)}{error}")


def _tax_accounts(key, company: str, amounts: TaxAmounts, label) -> tuple[str | None, str | None]:
	"""Where the tax lands, for one company.

	Reverse charge needs two: the tax owed and the input tax that offsets it.
	Everything else needs one.
	"""
	if key.effect == TAX_FREE or not amounts.tax:
		return None, None

	row = key.get_accounts_for(company)
	if not row:
		frappe.throw(
			_("{0}Tax key {1} has no tax account for {2}.").format(_prefix(label), key.name, company)
		)

	if key.effect == REVERSE_CHARGE and not row.deductible_tax_account:
		frappe.throw(
			_("{0}Tax key {1} has no deductible tax account for {2}.").format(
				_prefix(label), key.name, company
			)
		)

	return row.tax_account, row.deductible_tax_account


def _is_tax_account(account: str) -> bool:
	return bool(
		frappe.get_all(
			"Tax Key Account",
			filters={"tax_account": account},
			limit=1,
			ignore_permissions=True,
		)
	)


def _prefix(label: str | None) -> str:
	return f"{label}: " if label else ""


def set_automatic_account_flag(doc, method=None):
	"""Keep the Automatikkonto flag on an account in step with its tax key.

	The flag exists so a bookkeeper can filter for automatic accounts in the
	chart. It is derived, never typed, so the two can never contradict.
	"""
	doc.is_automatic_account = 1 if doc.get("tax_key") else 0
