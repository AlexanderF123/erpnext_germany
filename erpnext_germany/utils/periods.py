"""Date helpers for period-based reports.

This module deliberately has no Frappe dependency so that it can be unit tested
without a bench.
"""

from calendar import monthrange
from datetime import date


def get_month_range(fiscal_year_start: date, month: int) -> tuple[date, date]:
	"""Return first and last day of the given calendar month within a fiscal year.

	The month is a calendar month (1-12). For a shifted fiscal year, a month
	smaller than the fiscal year's start month belongs to the following
	calendar year. Example: for a fiscal year starting on 2025-04-01, month 2
	(February) resolves to February 2026, not February 2025.
	"""
	if not 1 <= month <= 12:
		raise ValueError(f"Month must be between 1 and 12, got {month}")

	year = fiscal_year_start.year if month >= fiscal_year_start.month else fiscal_year_start.year + 1
	month_start = date(year, month, 1)
	month_end = date(year, month, monthrange(year, month)[1])
	return month_start, month_end


def shift_years(day: date, years: int) -> date:
	"""Return the same day, shifted by the given number of years.

	February 29 is mapped to February 28 in non-leap years.
	"""
	try:
		return day.replace(year=day.year + years)
	except ValueError:
		# February 29 in a non-leap target year
		return day.replace(year=day.year + years, day=28)
