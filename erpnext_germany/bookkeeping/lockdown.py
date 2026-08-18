"""Enforcement of ledger lockdowns.

A Ledger Lockdown closes a period. From then on nothing may be posted into it
and nothing already in it may be taken back -- that is what makes the books
unchangeable. Corrections are booked as a general reversal in an open period
instead.

Without a single Ledger Lockdown record nothing is blocked, so the enforcement
is inert until a company starts closing periods.
"""

from datetime import date

import frappe
from frappe import _
from frappe.utils import format_date, getdate

from erpnext_germany.bookkeeping.posting import is_locked

CACHE_KEY = "erpnext_germany_ledger_lockdown"


def get_locked_up_to(company: str) -> date | None:
	"""Return the date up to which the company's ledger is closed, or None.

	Cached per company, because this is checked on every single ledger entry.
	"""
	if not company:
		return None

	cache = frappe.cache()
	cached = cache.hget(CACHE_KEY, company)
	if cached is not None:
		return getdate(cached) if cached else None

	locked_up_to = frappe.db.get_value(
		"Ledger Lockdown",
		{"company": company},
		"locked_up_to",
		order_by="locked_up_to desc",
	)

	# Store "" rather than None so that "no lockdown" is cached too.
	cache.hset(CACHE_KEY, company, locked_up_to or "")
	return getdate(locked_up_to) if locked_up_to else None


def clear_lockdown_cache(company: str | None = None):
	cache = frappe.cache()
	if company:
		cache.hdel(CACHE_KEY, company)
	else:
		cache.delete_key(CACHE_KEY)


def get_lockdown_date(company: str, posting_date) -> date | None:
	"""Return the lockdown date if this posting date is closed, otherwise None."""
	locked_up_to = get_locked_up_to(company)
	return locked_up_to if is_locked(getdate(posting_date), locked_up_to) else None


def ensure_can_post(company: str, posting_date):
	"""Raise if something would be posted into a closed period."""
	locked_up_to = get_lockdown_date(company, posting_date)
	if not locked_up_to:
		return

	frappe.throw(
		_("{0} is locked up to {1}. Nothing can be posted into a closed period.").format(
			company, format_date(locked_up_to)
		),
		title=_("Period Is Locked"),
	)


def ensure_can_cancel(company: str, posting_date):
	"""Raise if a document in a closed period would be cancelled."""
	locked_up_to = get_lockdown_date(company, posting_date)
	if not locked_up_to:
		return

	frappe.throw(
		_(
			"{0} is locked up to {1}. Documents in a closed period cannot be cancelled. "
			"Book a general reversal instead."
		).format(company, format_date(locked_up_to)),
		title=_("Period Is Locked"),
	)


def block_gl_entry_in_locked_period(doc, method=None):
	"""Refuse a ledger entry dated into a closed period.

	Hooked on GL Entry rather than on the individual vouchers so that every
	route into the ledger is covered, including the reversal entries that a
	cancellation produces.
	"""
	ensure_can_post(doc.company, doc.posting_date)


def block_cancellation_in_locked_period(doc, method=None):
	"""Refuse to cancel a voucher that sits in a closed period."""
	ensure_can_cancel(doc.company, doc.posting_date)
