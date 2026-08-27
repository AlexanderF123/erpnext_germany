"""Pure bookkeeping rules for posting batches.

Kept free of Frappe imports so the rules can be unit tested without a bench.
Anything that touches the database belongs in the controllers.
"""

DEBIT = "Debit"
CREDIT = "Credit"


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


def flip(sides: tuple[float, float]) -> tuple[float, float]:
	"""Swap debit and credit.

	Every posting has a counter posting; this is that counter posting.
	"""
	debit, credit = sides
	return credit, debit
