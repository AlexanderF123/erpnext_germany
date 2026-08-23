# Copyright (c) 2026, ALYF GmbH and contributors
# For license information, please see license.txt

"""Reading a run of document numbers for what is missing from it.

An outgoing invoice number has to be fortlaufend -- unbroken. That is not a
tidiness rule: a gap in the numbering is what an auditor takes as evidence
that an invoice was written and then made to disappear, and the burden of
explaining it falls on the company.

So the question this module answers is narrow and precise: given the numbers
that exist, which numbers between the first and the last do not. Not "which
documents are cancelled" -- a cancelled document still occupies its number and
is still there to be shown. A gap is a number nothing at all was ever written
under.

Kept free of Frappe: what counts as a gap is a matter of German bookkeeping
law, and the answer should be checkable without a database behind it.
"""

import re
from itertools import pairwise
from typing import NamedTuple

# The trailing digits of a document number, with whatever came before them.
# Deliberately anchored at the end: prefixes vary, and it is the counting part
# that matters.
TRAILING_DIGITS = re.compile(r"^(?P<prefix>.*?)(?P<number>\d+)$")


class DocumentNumber(NamedTuple):
	"""One document number, split into the part that counts and the rest."""

	raw: str
	prefix: str
	number: int | None

	@property
	def counts(self) -> bool:
		return self.number is not None


class Gap(NamedTuple):
	"""A run of numbers nothing was written under."""

	start: int
	end: int

	@property
	def size(self) -> int:
		return self.end - self.start + 1


def parse_number(raw: str | None, prefix: str = "") -> DocumentNumber:
	"""Split a document number into its prefix and its counting part.

	A number that does not belong to the expected prefix, or that ends in no
	digits at all, is returned uncounted rather than forced into the sequence.
	Guessing at it would invent gaps that are not there.
	"""
	text = (raw or "").strip()
	if not text:
		return DocumentNumber("", "", None)

	if prefix and not text.startswith(prefix):
		return DocumentNumber(text, "", None)

	match = TRAILING_DIGITS.match(text)
	if not match:
		return DocumentNumber(text, text, None)

	return DocumentNumber(text, match.group("prefix"), int(match.group("number")))


def belongs_to(raw: str | None, prefix: str = "") -> bool:
	"""Whether a document number is part of this range at all.

	Kept apart from whether it can be counted, because the two mean opposite
	things. A number from another range is not this range's problem and must
	not appear on its sheet; a number of this range that ends in no digits is
	exactly this range's problem and has to be said out loud.
	"""
	text = (raw or "").strip()
	if not text:
		return False

	return text.startswith(prefix) if prefix else True


def find_gaps(numbers: list[int]) -> list[Gap]:
	"""The runs of missing numbers between the first and the last.

	Only between: a sequence that starts at 5 is not missing 1 to 4, because
	nobody said it had to start at 1. Where a range says where it starts, the
	caller passes that in as a number of its own.
	"""
	present = sorted(set(numbers))
	if len(present) < 2:
		return []

	gaps = []
	for lower, upper in pairwise(present):
		if upper - lower > 1:
			gaps.append(Gap(lower + 1, upper - 1))

	return gaps


def find_duplicates(numbers: list[int]) -> list[int]:
	"""Numbers written under more than once.

	The other half of the same question: a sequence can be unbroken and still
	be wrong if the same number was used twice.
	"""
	seen = set()
	twice = set()
	for number in numbers:
		if number in seen:
			twice.add(number)

		seen.add(number)

	return sorted(twice)


def describe_gap(gap: Gap, prefix: str = "") -> str:
	"""A gap as it should be printed: one number, or a span."""
	if gap.start == gap.end:
		return f"{prefix}{gap.start}"

	return f"{prefix}{gap.start} - {prefix}{gap.end}"


def out_of_period(entries: list[tuple], from_date, to_date) -> list[tuple]:
	"""Documents whose date falls outside the range they were counted in.

	A number belongs to a year. One dated outside it is either misfiled or
	backdated, and both are worth a question.
	"""
	return [entry for entry in entries if entry[1] < from_date or entry[1] > to_date]
