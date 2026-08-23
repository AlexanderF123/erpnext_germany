from datetime import date

import pytest

from .periods import get_month_range, shift_years


def test_get_month_range_calendar_fiscal_year():
	"""For a calendar fiscal year, month and year line up directly."""
	fy_start = date(2025, 1, 1)

	assert get_month_range(fy_start, 1) == (date(2025, 1, 1), date(2025, 1, 31))
	assert get_month_range(fy_start, 6) == (date(2025, 6, 1), date(2025, 6, 30))
	assert get_month_range(fy_start, 12) == (date(2025, 12, 1), date(2025, 12, 31))


def test_get_month_range_shifted_fiscal_year():
	"""Months before the fiscal year's start month belong to the next calendar year."""
	fy_start = date(2025, 4, 1)

	# April to December stay in the starting year
	assert get_month_range(fy_start, 4) == (date(2025, 4, 1), date(2025, 4, 30))
	assert get_month_range(fy_start, 12) == (date(2025, 12, 1), date(2025, 12, 31))

	# January to March roll over into the following year
	assert get_month_range(fy_start, 1) == (date(2026, 1, 1), date(2026, 1, 31))
	assert get_month_range(fy_start, 3) == (date(2026, 3, 1), date(2026, 3, 31))


def test_get_month_range_february():
	"""February respects leap years."""
	assert get_month_range(date(2024, 1, 1), 2) == (date(2024, 2, 1), date(2024, 2, 29))
	assert get_month_range(date(2025, 1, 1), 2) == (date(2025, 2, 1), date(2025, 2, 28))


def test_get_month_range_invalid_month():
	for month in (0, 13, -1):
		with pytest.raises(ValueError, match="Month must be between 1 and 12"):
			get_month_range(date(2025, 1, 1), month)


def test_shift_years():
	assert shift_years(date(2025, 6, 15), -1) == date(2024, 6, 15)
	assert shift_years(date(2025, 6, 15), 1) == date(2026, 6, 15)


def test_shift_years_leap_day():
	"""February 29 falls back to February 28 when the target year is not a leap year."""
	assert shift_years(date(2024, 2, 29), -1) == date(2023, 2, 28)
	assert shift_years(date(2024, 2, 29), 1) == date(2025, 2, 28)
	assert shift_years(date(2024, 2, 29), 4) == date(2028, 2, 29)
