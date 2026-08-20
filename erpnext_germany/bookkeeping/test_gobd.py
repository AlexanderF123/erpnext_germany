# Copyright (c) 2026, ALYF GmbH and contributors
# For license information, please see license.txt

from datetime import date, datetime

from erpnext_germany.bookkeeping.gobd import (
	ALPHANUMERIC,
	DATE,
	NUMERIC,
	Column,
	Table,
	build_index,
	format_amount,
	format_date,
	format_text,
	format_value,
	to_csv,
)

JOURNAL = Table(
	"journal",
	"Buchungsjournal",
	(
		Column("voucher", "Beleg"),
		Column("posting_date", "Buchungsdatum", DATE),
		Column("debit", "Soll", NUMERIC),
	),
)


# --- how a value is written -------------------------------------------------


def test_an_amount_is_written_with_a_comma_and_two_decimals():
	"""Not a preference: it is what the reading software expects."""
	assert format_amount(1234.5) == "1234,50"
	assert format_amount(0) == "0,00"
	assert format_amount(-19.005) == "-19,01"


def test_an_amount_carries_no_thousands_separator():
	"""One that the reader does not expect turns one figure into two."""
	assert format_amount(1234567.89) == "1234567,89"


def test_a_date_is_written_the_german_way():
	assert format_date(date(2026, 3, 5)) == "05.03.2026"
	assert format_date(datetime(2026, 3, 5, 14, 30)) == "05.03.2026"


def test_a_date_that_arrives_as_text_is_turned_round():
	"""Dates come out of the database as ISO and have to be turned round."""
	assert format_date("2026-03-05") == "05.03.2026"
	assert format_date("2026-03-05 14:30:00") == "05.03.2026"


def test_something_that_is_not_a_date_is_passed_through_rather_than_guessed_at():
	assert format_date("laufend") == "laufend"


def test_a_line_break_in_a_booking_text_is_taken_out():
	"""A newline inside a field has cost more audits than it has explained."""
	assert format_text("Miete\nJanuar") == "Miete Januar"
	assert format_text("Miete\r\nJanuar") == "Miete Januar"
	assert format_text('Rechnung "4711"') == "Rechnung '4711'"


def test_nothing_is_written_as_nothing():
	assert format_value(None, ALPHANUMERIC) == ""
	assert format_value(None, NUMERIC) == ""
	assert format_value(None, DATE) == ""


# --- how a file is written --------------------------------------------------


def test_a_file_starts_with_its_column_labels():
	csv = to_csv(JOURNAL, [])

	assert csv == '"Beleg";"Buchungsdatum";"Soll"\r\n'


def test_a_row_is_written_in_the_order_the_table_declares():
	csv = to_csv(JOURNAL, [{"debit": 100, "voucher": "JV-1", "posting_date": date(2026, 3, 5)}])

	assert csv.splitlines()[1] == '"JV-1";"05.03.2026";"100,00"'


def test_a_missing_field_is_written_as_an_empty_one():
	"""A short row would shift every column after it."""
	csv = to_csv(JOURNAL, [{"voucher": "JV-1"}])

	assert csv.splitlines()[1] == '"JV-1";"";""'


def test_a_field_the_table_does_not_declare_is_left_out():
	csv = to_csv(JOURNAL, [{"voucher": "JV-1", "secret": "x"}])

	assert "secret" not in csv
	assert "x" not in csv


# --- how the package describes itself ---------------------------------------


def test_the_index_names_every_file_of_the_package():
	index = build_index("Musterfirma", "Wirtschaftsjahr 2026", [JOURNAL])

	assert "journal.csv" in index
	assert "Buchungsjournal" in index


def test_the_index_declares_the_type_of_every_column():
	"""An index that says date where the file holds a number is rejected
	without explanation, so it is written from the same declaration."""
	index = build_index("Musterfirma", "", [JOURNAL])

	assert "<Name>Soll</Name><Numeric>" in index
	assert "<Name>Buchungsdatum</Name><Date>" in index
	assert "<Name>Beleg</Name><AlphaNumeric/>" in index


def test_the_index_states_the_separators_the_files_actually_use():
	index = build_index("Musterfirma", "", [JOURNAL])

	assert "<DecimalSymbol>,</DecimalSymbol>" in index
	assert "<ColumnDelimiter>;</ColumnDelimiter>" in index
	assert "<DigitGroupingSymbol></DigitGroupingSymbol>" in index


def test_the_index_declares_the_description_standard():
	index = build_index("Musterfirma", "", [JOURNAL])

	assert "gdpdu-01-09-2004.dtd" in index
	assert index.startswith('<?xml version="1.0" encoding="UTF-8"?>')


def test_a_company_name_with_an_ampersand_does_not_break_the_index():
	index = build_index("Meier & Sohn", "", [JOURNAL])

	assert "Meier &amp; Sohn" in index
	assert "Meier & Sohn" not in index
