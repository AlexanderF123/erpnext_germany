# Copyright (c) 2026, ALYF GmbH and contributors
# For license information, please see license.txt

"""The shape of a BWA, independent of where the figures come from.

A BWA is not a balance sheet and not a profit and loss statement. It is the
one sheet a German accountant and a bank look at every month, and its form is
older than any software: revenue, minus what it cost to earn, down to a
provisional result, each line traceable to the accounts behind it.

What makes it worth its own module is that the form is not fixed. Every chart
of accounts groups its accounts differently, and a company that reports by
property or by branch wants its own arrangement. So the arrangement is data,
and this module is what reads it: which accounts a line covers, whether the
line adds or subtracts, and how the result lines are made from the lines
above them.

Kept free of Frappe on purpose, so the arithmetic can be checked without a
site behind it -- and it is the arithmetic that a tax advisor will hold us to.
"""

from typing import NamedTuple

# What a line is made of.
ACCOUNTS = "Accounts"
SUBTOTAL = "Subtotal"
RATIO = "Ratio"
ROW_TYPES = (ACCOUNTS, SUBTOTAL, RATIO)

ADDS = "+"
SUBTRACTS = "-"
SIGNS = (ADDS, SUBTRACTS)

RANGE_SEPARATOR = "-"


class AccountRange(NamedTuple):
	"""A span of account numbers, both ends included."""

	start: int
	end: int

	def covers(self, account_number: str | int | None) -> bool:
		number = as_number(account_number)
		return number is not None and self.start <= number <= self.end


class Row(NamedTuple):
	"""One line of the form, as it was configured.

	``sign`` says which way is up for this line. On an account line it decides
	whether the figure is read as revenue or as cost; on a result line it
	decides whether the running total is printed as it stands or the other way
	round -- which is how a BWA can print a cost total as a positive figure
	and still subtract it from the result below.
	"""

	number: int
	label: str
	row_type: str
	sign: int
	ranges: tuple[AccountRange, ...] = ()
	from_row: int = 0
	to_row: int = 0
	reference_row: int = 0


def as_number(account_number: str | int | None) -> int | None:
	"""An account number as the integer a range is compared against.

	Accounts without a numeric number -- ERPNext allows those -- belong to no
	range, rather than to the first one that happens to start at zero.
	"""
	if account_number is None or account_number == "":
		return None

	text = str(account_number).strip()
	return int(text) if text.isdigit() else None


def parse_ranges(text: str | None) -> tuple[AccountRange, ...]:
	"""Read the account ranges of a line.

	One range per line, either a span like ``4100-4199`` or a single account
	like ``4210``. Written the way a chart of accounts is talked about, so
	that whoever maintains the form can check it against the SKR by reading.
	"""
	ranges = []
	for line in (text or "").splitlines():
		entry = line.strip()
		if not entry or entry.startswith("#"):
			continue

		ranges.append(parse_range(entry))

	return tuple(ranges)


def parse_range(entry: str) -> AccountRange:
	start, separator, end = entry.partition(RANGE_SEPARATOR)
	first = as_number(start)
	last = as_number(end) if separator else first

	if first is None or last is None:
		raise ValueError(f"{entry!r} is not an account number or a range of account numbers")

	if last < first:
		raise ValueError(f"{entry!r} ends before it starts")

	return AccountRange(first, last)


def covered_by(account_number: str | int | None, ranges: tuple[AccountRange, ...]) -> bool:
	return any(one.covers(account_number) for one in ranges)


def row_amount(sign: int, debit: float, credit: float) -> float:
	"""What a line prints, positive in its own direction.

	A BWA prints costs as positive figures and subtracts them; it does not
	print them as negative revenue. So the direction a line reads in follows
	from what the line does to the result, not from the root type of the
	accounts underneath it -- which also means a form can put an account
	wherever its author needs it.
	"""
	return (credit - debit) if sign > 0 else (debit - credit)


def evaluate(rows: list[Row], amounts: dict[int, float]) -> dict[int, float | None]:
	"""Work the form out, top to bottom.

	Result lines add up the account lines above them rather than the result
	lines, so that a running total never counts the same figure twice: in a
	BWA every result line is a further step down the same column, not a sum
	of the steps before it.

	A ratio has no value where its reference is nil. That is left as None
	instead of nought, because a percentage of nothing is not nothing.
	"""
	check_references(rows)
	values: dict[int, float | None] = {}

	for row in rows:
		if row.row_type == ACCOUNTS:
			values[row.number] = amounts.get(row.number, 0.0)
		elif row.row_type == SUBTOTAL:
			values[row.number] = row.sign * span_total(rows, values, row)
		elif row.row_type == RATIO:
			values[row.number] = ratio(
				row.sign * span_total(rows, values, row), values.get(row.reference_row)
			)
		else:
			raise ValueError(f"Unknown row type {row.row_type!r} in row {row.number}")

	return values


def check_references(rows: list[Row]):
	"""Refuse a form that points at a line which is not there.

	Checked before anything is worked out: a BWA that quietly treats a
	missing line as nought is worse than one that says it is broken.
	"""
	numbers = {row.number for row in rows}
	for row in rows:
		if row.row_type == RATIO and row.reference_row not in numbers:
			raise ValueError(f"Row {row.number} refers to row {row.reference_row}, which does not exist")


def span_total(rows: list[Row], values: dict[int, float | None], row: Row) -> float:
	total = 0.0
	for other in rows:
		if other.row_type != ACCOUNTS or not (row.from_row <= other.number <= row.to_row):
			continue

		total += other.sign * (values.get(other.number) or 0.0)

	return total


def ratio(amount: float, reference: float | None) -> float | None:
	if not reference:
		return None

	return 100.0 * amount / reference


def deviation(current: float | None, previous: float | None) -> float | None:
	"""How far this month is from the same month last year, in percent.

	Undefined where last year was nil: everything is infinitely more than
	nothing, which is not a figure anyone can act on.
	"""
	if not previous:
		return None

	return 100.0 * ((current or 0.0) - previous) / abs(previous)
