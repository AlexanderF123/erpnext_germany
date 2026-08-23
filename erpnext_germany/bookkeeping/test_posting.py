from datetime import date

import pytest

from .posting import CREDIT, DEBIT, is_locked, split_amount


def test_split_amount_debit():
	assert split_amount(DEBIT, 119.0) == (119.0, 0.0)


def test_split_amount_credit():
	assert split_amount(CREDIT, 119.0) == (0.0, 119.0)


def test_split_amount_rejects_unknown_direction():
	with pytest.raises(ValueError, match="Direction must be"):
		split_amount("Soll", 119.0)


def test_split_amount_rejects_non_positive():
	"""A negative or zero turnover is a data error, not a reversal.

	Reversals are booked as a general reversal against the original entry, not
	by typing a minus sign.
	"""
	for amount in (0, -1, -119.0):
		with pytest.raises(ValueError, match="Amount must be greater than zero"):
			split_amount(DEBIT, amount)


def test_split_amount_is_balanced_either_way():
	"""Whatever the direction, the two sides of one entry cancel out.

	This is why a batch never needs a difference column: every entry is a
	complete double entry on its own.
	"""
	for direction in (DEBIT, CREDIT):
		debit, credit = split_amount(direction, 119.0)
		assert debit + credit == 119.0
		assert min(debit, credit) == 0.0


def test_is_locked_includes_the_lockdown_date():
	"""Locking up to 31 March closes March itself."""
	locked_up_to = date(2026, 3, 31)

	assert is_locked(date(2026, 3, 31), locked_up_to)
	assert is_locked(date(2026, 2, 1), locked_up_to)
	assert not is_locked(date(2026, 4, 1), locked_up_to)


def test_is_locked_without_lockdown():
	"""Without a lockdown nothing is closed."""
	assert not is_locked(date(2020, 1, 1), None)
