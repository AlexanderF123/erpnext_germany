# Copyright (c) 2026, ALYF GmbH and contributors
# For license information, please see license.txt

from datetime import date

from erpnext_germany.bookkeeping.document_ranges import (
	Gap,
	belongs_to,
	describe_gap,
	find_duplicates,
	find_gaps,
	out_of_period,
	parse_number,
)

# --- reading a number -------------------------------------------------------


def test_a_number_is_split_into_its_prefix_and_its_counting_part():
	parsed = parse_number("RE-2026-0042")

	assert parsed.prefix == "RE-2026-"
	assert parsed.number == 42
	assert parsed.counts


def test_a_number_that_is_only_digits_has_no_prefix():
	assert parse_number("4711").number == 4711
	assert parse_number("4711").prefix == ""


def test_leading_zeros_do_not_change_what_a_number_counts_as():
	"""0042 and 42 are the same place in the sequence."""
	assert parse_number("RE-0042").number == parse_number("RE-42").number


def test_a_number_ending_in_no_digits_does_not_count():
	"""Guessing at it would invent gaps that are not there."""
	assert not parse_number("Storno").counts
	assert not parse_number("").counts
	assert not parse_number(None).counts


def test_a_number_from_another_range_does_not_count_in_this_one():
	assert not parse_number("AR-2026-0001", prefix="RE-2026-").counts
	assert parse_number("RE-2026-0001", prefix="RE-2026-").counts


def test_only_the_trailing_digits_count():
	"""A year in the prefix must not be read as the number."""
	assert parse_number("RE-2026-0007").number == 7


# --- what is missing --------------------------------------------------------


def test_an_unbroken_run_has_no_gaps():
	assert find_gaps([1, 2, 3, 4]) == []


def test_a_single_missing_number_is_one_gap():
	assert find_gaps([1, 2, 4]) == [Gap(3, 3)]


def test_several_missing_numbers_in_a_row_are_one_gap():
	assert find_gaps([1, 5]) == [Gap(2, 4)]


def test_gaps_are_only_looked_for_between_the_first_and_the_last():
	"""A sequence that starts at 5 is not missing 1 to 4: nobody said it had to."""
	assert find_gaps([5, 6, 7]) == []


def test_a_run_of_one_has_nothing_to_be_missing_from_it():
	assert find_gaps([7]) == []
	assert find_gaps([]) == []


def test_the_same_number_twice_does_not_make_a_gap():
	assert find_gaps([1, 1, 2]) == []


# --- what is there twice ----------------------------------------------------


def test_a_number_used_twice_is_reported():
	"""A sequence can be unbroken and still be wrong."""
	assert find_duplicates([1, 2, 2, 3]) == [2]


def test_a_number_used_three_times_is_reported_once():
	assert find_duplicates([2, 2, 2]) == [2]


def test_a_clean_run_has_no_duplicates():
	assert find_duplicates([1, 2, 3]) == []


# --- how a gap is printed ---------------------------------------------------


def test_a_single_missing_number_is_printed_as_itself():
	assert describe_gap(Gap(3, 3), "RE-2026-") == "RE-2026-3"


def test_a_run_is_printed_as_a_span():
	assert describe_gap(Gap(3, 7), "RE-2026-") == "RE-2026-3 - RE-2026-7"


# --- what is dated outside its year -----------------------------------------


def test_a_document_dated_outside_the_period_is_reported():
	"""Either misfiled or backdated, and both are worth a question."""
	entries = [
		("RE-1", date(2026, 6, 1)),
		("RE-2", date(2025, 12, 31)),
		("RE-3", date(2027, 1, 1)),
	]

	loose = out_of_period(entries, date(2026, 1, 1), date(2026, 12, 31))

	assert [entry[0] for entry in loose] == ["RE-2", "RE-3"]


def test_a_document_on_the_boundary_is_inside_it():
	entries = [("RE-1", date(2026, 1, 1)), ("RE-2", date(2026, 12, 31))]

	assert out_of_period(entries, date(2026, 1, 1), date(2026, 12, 31)) == []


# --- what belongs to a range at all -----------------------------------------


def test_a_number_with_the_range_prefix_belongs_to_it():
	assert belongs_to("RE-2026-0001", "RE-2026-")


def test_a_number_from_another_range_does_not_belong():
	"""Otherwise every other range's numbers would read as gaps in this one."""
	assert not belongs_to("AR-2026-0001", "RE-2026-")


def test_a_range_without_a_prefix_takes_everything_it_is_given():
	assert belongs_to("4711")
	assert belongs_to("Storno")


def test_an_empty_number_belongs_to_nothing():
	assert not belongs_to("", "RE-")
	assert not belongs_to(None)
	assert not belongs_to("   ")


def test_belonging_and_counting_are_different_questions():
	"""A number of this range that ends in no digits is this range's problem."""
	assert belongs_to("RE-2026-Storno", "RE-2026-")
	assert not parse_number("RE-2026-Storno").counts
