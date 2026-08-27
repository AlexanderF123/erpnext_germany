import pytest

from .posting import CREDIT, DEBIT, flip, split_amount


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


def test_flip_swaps_the_two_sides():
	"""Every posting has a counter posting."""
	assert flip(split_amount(DEBIT, 119.0)) == split_amount(CREDIT, 119.0)
	assert flip(split_amount(CREDIT, 119.0)) == split_amount(DEBIT, 119.0)
