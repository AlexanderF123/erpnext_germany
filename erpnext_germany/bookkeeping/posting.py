"""Pure bookkeeping rules for posting batches.

Kept free of Frappe imports so the arithmetic can be unit tested without a
bench. Anything that touches the database belongs in the controllers.
"""

from datetime import date

DEBIT = "Debit"
CREDIT = "Credit"

# Amounts below this are treated as zero when comparing totals.
ROUNDING_TOLERANCE = 0.005


def split_amount(direction: str, amount: float) -> tuple[float, float]:
	"""Return (debit, credit) for one entry.

	A batch entry carries a single amount plus the direction it applies to its
	account, the way an accountant reads it off a document. The contra account
	always receives the opposite side, so one entry is a complete, balanced
	double entry.
	"""
	if direction not in (DEBIT, CREDIT):
		raise ValueError(f"Direction must be {DEBIT!r} or {CREDIT!r}, got {direction!r}")

	if amount <= 0:
		raise ValueError(f"Amount must be greater than zero, got {amount!r}")

	return (amount, 0.0) if direction == DEBIT else (0.0, amount)


def summarize(entries) -> tuple[float, float, float]:
	"""Return (total debit, total credit, difference) over the given entries.

	Each entry needs a ``direction`` and an ``amount``. Entries that carry
	neither are skipped, so a half-filled row in the grid does not blow up the
	running total while it is being typed.
	"""
	total_debit = 0.0
	total_credit = 0.0

	for entry in entries:
		direction = getattr(entry, "direction", None)
		amount = getattr(entry, "amount", None)
		if not direction or not amount:
			continue

		debit, credit = split_amount(direction, amount)
		total_debit += debit
		total_credit += credit

	return total_debit, total_credit, total_debit - total_credit


def is_balanced(total_debit: float, total_credit: float) -> bool:
	return abs(total_debit - total_credit) < ROUNDING_TOLERANCE


def is_locked(posting_date: date, locked_up_to: date | None) -> bool:
	"""Return True if the date falls into a period that has been locked down.

	The lockdown date itself is included: locking up to 31 March closes March.
	"""
	if not locked_up_to:
		return False

	return posting_date <= locked_up_to
