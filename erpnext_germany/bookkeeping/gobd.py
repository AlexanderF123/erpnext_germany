# Copyright (c) 2026, ALYF GmbH and contributors
# For license information, please see license.txt

"""The shape of a tax audit data package, without any data in it yet.

When a Betriebspruefer asks for the books, they do not want a report. They
want the data, in files their own software can read, together with a
description of what is in each column -- the Beschreibungsstandard that has
accompanied German audit exports since 2004.

The description is the part that is easy to get subtly wrong and impossible
to notice: an export whose index says a column holds a date when it holds a
number is accepted by nobody and rejected with no explanation. So the tables
are declared once, and both the data and its description are written from the
same declaration. They cannot disagree.

Free of Frappe on purpose. What the files must look like is a question of
German audit law, not of any database.
"""

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import NamedTuple
from xml.sax.saxutils import escape

# What the audit software is told about a column.
ALPHANUMERIC = "AlphaNumeric"
NUMERIC = "Numeric"
DATE = "Date"
COLUMN_TYPES = (ALPHANUMERIC, NUMERIC, DATE)

# The description standard the package declares itself against.
DTD = "gdpdu-01-09-2004.dtd"

# German audit files are semicolon separated with a comma for the decimal
# point. Not a preference -- it is what the reading software expects.
DELIMITER = ";"
DECIMAL_SEPARATOR = ","
THOUSANDS_SEPARATOR = ""
RECORD_SEPARATOR = "\r\n"
TEXT_QUOTE = '"'
DATE_FORMAT = "DD.MM.YYYY"

CENT = Decimal("0.01")


class Column(NamedTuple):
	"""One column, as the data and as the description of the data."""

	name: str
	label: str
	type: str = ALPHANUMERIC


class Table(NamedTuple):
	"""One file of the package, and what is in it."""

	name: str
	label: str
	columns: tuple[Column, ...]

	@property
	def file_name(self) -> str:
		return f"{self.name}.csv"


def format_value(value, column_type: str) -> str:
	"""One value, the way the reading software expects to find it."""
	if value is None:
		return ""

	if column_type == NUMERIC:
		return format_amount(value)

	if column_type == DATE:
		return format_date(value)

	return format_text(value)


def format_amount(value) -> str:
	"""Two decimals with a comma, and no thousands separator to trip over."""
	amount = Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
	return f"{amount}".replace(".", DECIMAL_SEPARATOR)


def format_date(value) -> str:
	if isinstance(value, datetime):
		value = value.date()

	if isinstance(value, date):
		return value.strftime("%d.%m.%Y")

	# Already a string. Dates arrive from the database as ISO and have to be
	# turned round; anything else is passed through rather than guessed at.
	text = str(value).strip()[:10]
	parts = text.split("-")
	if len(parts) == 3 and all(part.isdigit() for part in parts):
		return f"{parts[2]}.{parts[1]}.{parts[0]}"

	return text


def format_text(value) -> str:
	"""Anything that could break a line or a field is taken out.

	Not escaped: the reading software of a tax office is not a CSV parser with
	opinions about quoting, and a newline inside a booking text has cost more
	audits than it has ever explained anything.
	"""
	text = str(value)
	for character in ("\r\n", "\r", "\n", "\t"):
		text = text.replace(character, " ")

	return text.replace(TEXT_QUOTE, "'").strip()


def to_csv(table: Table, rows: list[dict]) -> str:
	"""One file of the package: a header line, then the data."""
	lines = [DELIMITER.join(quoted(column.label) for column in table.columns)]
	for row in rows:
		lines.append(
			DELIMITER.join(
				quoted(format_value(row.get(column.name), column.type)) for column in table.columns
			)
		)

	return RECORD_SEPARATOR.join(lines) + RECORD_SEPARATOR


def quoted(value: str) -> str:
	return f"{TEXT_QUOTE}{value}{TEXT_QUOTE}"


def build_index(name: str, description: str, tables: list[Table]) -> str:
	"""The index the audit software reads before it reads anything else.

	Written from the same table declarations as the data, so the description
	and the files cannot drift apart -- which is the one failure in an export
	that nobody catches by looking.
	"""
	parts = [
		'<?xml version="1.0" encoding="UTF-8"?>',
		f'<!DOCTYPE DataSet SYSTEM "{DTD}">',
		"<DataSet>",
		f"<Version>1.0</Version><DataSupplier><Name>{escape(name)}</Name>",
		f"<Location>{escape(name)}</Location><Comment>{escape(description)}</Comment></DataSupplier>",
	]

	for table in tables:
		parts.append("<Media><Name>1</Name><Table>")
		parts.append(f"<URL>{escape(table.file_name)}</URL>")
		parts.append(f"<Name>{escape(table.label)}</Name>")
		parts.append(f"<Description>{escape(table.label)}</Description>")
		parts.append(f"<Validity><Range><From/><To/></Range><Format>{DATE_FORMAT}</Format></Validity>")
		parts.append(f"<DecimalSymbol>{DECIMAL_SEPARATOR}</DecimalSymbol>")
		parts.append(f"<DigitGroupingSymbol>{THOUSANDS_SEPARATOR}</DigitGroupingSymbol>")
		parts.append("<VariableLength>")
		parts.append(f"<ColumnDelimiter>{escape(DELIMITER)}</ColumnDelimiter>")
		parts.append("<RecordDelimiter>&#13;&#10;</RecordDelimiter>")
		parts.append(f"<TextEncapsulator>{escape(TEXT_QUOTE)}</TextEncapsulator>")
		for column in table.columns:
			parts.append(column_element(column))

		parts.append("</VariableLength></Table></Media>")

	parts.append("</DataSet>")
	return "\n".join(parts)


def column_element(column: Column) -> str:
	label = escape(column.label)
	kind = {
		NUMERIC: "<Numeric><Accuracy>2</Accuracy></Numeric>",
		DATE: f"<Date><Format>{DATE_FORMAT}</Format></Date>",
	}.get(column.type, "<AlphaNumeric/>")

	return f"<VariableColumn><Name>{label}</Name>{kind}</VariableColumn>"
