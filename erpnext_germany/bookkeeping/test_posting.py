from datetime import date

import pytest

from .posting import CREDIT, DEBIT, is_balanced, is_locked, split_amount, summarize


class Entry:
	"""Stand-in for a Posting Batch Entry row."""

	def __init__(self, direction=None, amount=None):
		self.direction = direction
		self.amount = amount


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


def test_summarize_balances_by_construction():
	"""Every entry is a complete double entry, so a batch is always balanced."""
	entries = [Entry(DEBIT, 119.0), Entry(CREDIT, 500.0), Entry(DEBIT, 42.5)]

	total_debit, total_credit, difference = summarize(entries)

	assert total_debit == 161.5
	assert total_credit == 500.0
	assert difference == pytest.approx(-338.5)


def test_summarize_skips_incomplete_rows():
	"""A row that is still being typed must not break the running total."""
	entries = [Entry(DEBIT, 100.0), Entry(None, None), Entry(DEBIT, None), Entry(None, 50.0)]

	assert summarize(entries) == (100.0, 0.0, 100.0)


def test_summarize_empty():
	assert summarize([]) == (0.0, 0.0, 0.0)


def test_is_balanced_within_tolerance():
	assert is_balanced(100.0, 100.0)
	assert is_balanced(100.0, 100.004)
	assert not is_balanced(100.0, 100.01)


def test_is_locked_includes_the_lockdown_date():
	"""Locking up to 31 March closes March itself."""
	locked_up_to = date(2026, 3, 31)

	assert is_locked(date(2026, 3, 31), locked_up_to)
	assert is_locked(date(2026, 2, 1), locked_up_to)
	assert not is_locked(date(2026, 4, 1), locked_up_to)


def test_is_locked_without_lockdown():
	"""Without a lockdown nothing is closed."""
	assert not is_locked(date(2020, 1, 1), None)
