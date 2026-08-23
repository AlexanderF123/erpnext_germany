# Copyright (c) 2026, ALYF GmbH and contributors
# For license information, please see license.txt

import pytest

from erpnext_germany.bookkeeping.bwa import (
	ACCOUNTS,
	RATIO,
	SUBTOTAL,
	AccountRange,
	Row,
	as_number,
	covered_by,
	deviation,
	evaluate,
	parse_ranges,
	ratio,
	row_amount,
)


def accounts_row(number, label, sign, ranges="", **kwargs):
	return Row(number, label, ACCOUNTS, sign, parse_ranges(ranges), **kwargs)


def subtotal(number, label, from_row, to_row):
	return Row(number, label, SUBTOTAL, 1, from_row=from_row, to_row=to_row)


# --- reading the form -------------------------------------------------------


def test_a_single_account_is_a_range_of_one():
	assert parse_ranges("4210") == (AccountRange(4210, 4210),)


def test_a_span_covers_both_ends():
	span = parse_ranges("4100-4199")[0]

	assert span.covers(4100)
	assert span.covers(4199)
	assert not span.covers(4099)
	assert not span.covers(4200)


def test_a_line_can_list_several_ranges():
	ranges = parse_ranges("4100-4199\n4210\n 4300-4399 ")

	assert ranges == (AccountRange(4100, 4199), AccountRange(4210, 4210), AccountRange(4300, 4399))


def test_blank_lines_and_notes_are_skipped():
	"""Whoever maintains the form should be able to write down why a range is there."""
	ranges = parse_ranges("# Loehne und Gehaelter\n4100-4199\n\n")

	assert ranges == (AccountRange(4100, 4199),)


def test_an_unreadable_range_is_refused_rather_than_ignored():
	for broken in ("Personalkosten", "4100-", "-4199", "4199-4100"):
		with pytest.raises(ValueError):
			parse_ranges(broken)


def test_an_account_without_a_number_belongs_to_no_range():
	"""ERPNext allows accounts without a number; they must not fall into the first range."""
	assert as_number(None) is None
	assert as_number("") is None
	assert as_number("Bank") is None
	assert not covered_by(None, parse_ranges("0-9999"))
	assert not covered_by("Bank", parse_ranges("0-9999"))


def test_membership_asks_every_range_of_the_line():
	ranges = parse_ranges("4100-4199\n4830")

	assert covered_by("4120", ranges)
	assert covered_by(4830, ranges)
	assert not covered_by("4831", ranges)


# --- which direction a line reads in ----------------------------------------


def test_a_line_that_adds_reads_credit_minus_debit():
	"""Revenue is a credit balance, and revenue is what a BWA starts from."""
	assert row_amount(1, debit=0.0, credit=1000.0) == 1000.0


def test_a_line_that_subtracts_reads_debit_minus_credit():
	"""A BWA prints costs as positive figures and takes them off, rather than
	printing them as negative revenue."""
	assert row_amount(-1, debit=400.0, credit=0.0) == 400.0


def test_a_returned_sale_shows_as_a_negative_line():
	assert row_amount(1, debit=1200.0, credit=1000.0) == -200.0


# --- working the form out ---------------------------------------------------


def test_a_result_line_adds_up_the_account_lines_above_it():
	rows = [
		accounts_row(1, "Umsatzerloese", 1),
		accounts_row(2, "Materialaufwand", -1),
		subtotal(3, "Rohertrag", 1, 2),
	]

	values = evaluate(rows, {1: 1000.0, 2: 400.0})

	assert values[3] == 600.0


def test_result_lines_do_not_count_each_other():
	"""Every result line is a further step down the same column.

	An earlier arrangement summed whatever stood above, which counted the
	Rohertrag a second time inside the Betriebsergebnis.
	"""
	rows = [
		accounts_row(1, "Umsatzerloese", 1),
		accounts_row(2, "Materialaufwand", -1),
		subtotal(3, "Rohertrag", 1, 2),
		accounts_row(4, "Personalkosten", -1),
		subtotal(5, "Betriebsergebnis", 1, 4),
	]

	values = evaluate(rows, {1: 1000.0, 2: 400.0, 4: 300.0})

	assert values[3] == 600.0
	assert values[5] == 300.0


def test_an_account_line_with_no_movement_counts_as_nought():
	rows = [accounts_row(1, "Umsatzerloese", 1), subtotal(2, "Gesamtleistung", 1, 1)]

	assert evaluate(rows, {}) == {1: 0.0, 2: 0.0}


def test_a_ratio_is_its_span_against_its_reference():
	rows = [
		accounts_row(1, "Umsatzerloese", 1),
		accounts_row(2, "Personalkosten", -1),
		subtotal(3, "Gesamtleistung", 1, 1),
		Row(4, "Personalkostenquote", RATIO, 1, from_row=2, to_row=2, reference_row=3),
	]

	values = evaluate(rows, {1: 1000.0, 2: 250.0})

	# The span carries the line's own sign, so a cost quota reads negative.
	assert values[4] == -25.0


def test_a_ratio_against_nothing_has_no_value():
	"""Not nought: a percentage of nothing is not nothing."""
	assert ratio(250.0, 0.0) is None
	assert ratio(250.0, None) is None


def test_a_form_that_points_at_a_missing_line_is_refused():
	rows = [
		accounts_row(1, "Umsatzerloese", 1),
		Row(2, "Quote", RATIO, 1, from_row=1, to_row=1, reference_row=99),
	]

	with pytest.raises(ValueError, match="99"):
		evaluate(rows, {1: 1000.0})


def test_an_unknown_row_type_is_refused():
	with pytest.raises(ValueError, match="Zwischensumme"):
		evaluate([Row(1, "?", "Zwischensumme", 1)], {})


def test_the_standard_shape_comes_out_as_an_accountant_would_add_it_up():
	"""Read as a tax advisor reads it: down the column, one step at a time."""
	rows = [
		accounts_row(1, "Umsatzerloese", 1),
		accounts_row(2, "Bestandsveraenderung", 1),
		subtotal(3, "Gesamtleistung", 1, 2),
		accounts_row(4, "Materialaufwand", -1),
		subtotal(5, "Rohertrag", 1, 4),
		accounts_row(6, "Personalkosten", -1),
		accounts_row(7, "Raumkosten", -1),
		accounts_row(8, "Sonstige Kosten", -1),
		subtotal(9, "Betriebsergebnis", 1, 8),
		accounts_row(10, "Zinsaufwand", -1),
		subtotal(11, "Vorlaeufiges Ergebnis", 1, 10),
	]

	values = evaluate(
		rows, {1: 100_000.0, 2: 5_000.0, 4: 40_000.0, 6: 30_000.0, 7: 6_000.0, 8: 4_000.0, 10: 2_000.0}
	)

	assert values[3] == 105_000.0
	assert values[5] == 65_000.0
	assert values[9] == 25_000.0
	assert values[11] == 23_000.0


# --- the comparison with last year ------------------------------------------


def test_deviation_is_a_percentage_of_last_year():
	assert deviation(110.0, 100.0) == 10.0
	assert deviation(90.0, 100.0) == -10.0


def test_deviation_reads_growth_as_growth_even_below_the_line():
	"""A loss of 50 after a loss of 100 is an improvement, and has to read as one."""
	assert deviation(-50.0, -100.0) == 50.0


def test_there_is_no_deviation_from_nothing():
	assert deviation(100.0, 0.0) is None
	assert deviation(100.0, None) is None


def test_a_cost_total_can_be_printed_the_way_a_BWA_prints_it():
	"""Gesamtkosten stands positive on the sheet and is still taken off below.

	The line's own sign is what turns it round, so the arrangement says so
	instead of the report knowing which lines are cost lines.
	"""
	rows = [
		accounts_row(1, "Umsatzerloese", 1),
		accounts_row(2, "Personalkosten", -1),
		accounts_row(3, "Raumkosten", -1),
		Row(4, "Gesamtkosten", SUBTOTAL, -1, from_row=2, to_row=3),
		subtotal(5, "Betriebsergebnis", 1, 3),
	]

	values = evaluate(rows, {1: 1000.0, 2: 300.0, 3: 100.0})

	assert values[4] == 400.0
	assert values[5] == 600.0
