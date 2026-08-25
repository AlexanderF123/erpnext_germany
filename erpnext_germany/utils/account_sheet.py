# Copyright (c) 2026, ALYF GmbH and contributors
# For license information, please see license.txt

"""What a Kontoblatt is made of, before any of it comes out of a database.

A Kontoblatt is read down the page: the balance carried in at the top, then
every movement in order, and after each one the balance as it stood at that
moment. That running balance is the whole point of the sheet -- it is how a
bookkeeper finds the entry that made an account go wrong, by reading until
the figure stops matching what they expected.

Which is why it is worked out here rather than in the query: a running total
depends on the order of what came before it, and an order that lives in a SQL
clause is one nobody can test.
"""

from typing import NamedTuple

# Which field on a voucher carries the document number a bookkeeper wrote on
# the paper. Everything not listed falls back to the document's own name,
# which is what the system called it rather than what the desk called it.

DEBIT_ROOT_TYPES = ("Asset", "Expense")

# What a balance sheet carries from one year into the next. Everything else is
# a profit and loss account, and those begin every fiscal year at nought.
BALANCE_SHEET_ROOT_TYPES = ("Asset", "Liability", "Equity")


def starts_each_year_at_zero(root_type: str) -> bool:
	"""Whether an account begins every fiscal year at nought.

	Income and expense do: last year's result is closed into equity, and an
	account that carried it forward as well would count it twice. A balance
	sheet account carries everything ever booked to it.

	A fact about what an account is, so it is stated once and read by every
	evaluation. Kept here rather than in the report that needed it first --
	an evaluation that does not know this rule shows a balance that does not
	tie to the one next to it.
	"""
	return root_type not in BALANCE_SHEET_ROOT_TYPES


class Movement(NamedTuple):
	"""One line of the sheet, before the balance is put behind it."""

	debit: float
	credit: float


def running_balances(opening: float, movements: list[Movement]) -> list[float]:
	"""The balance after each movement, starting from what was carried in.

	Debit minus credit throughout, in the ledger's own direction. Which side
	that reads as is a question for the account, not for the arithmetic.
	"""
	balance = opening
	balances = []
	for movement in movements:
		balance += movement.debit - movement.credit
		balances.append(balance)

	return balances


def in_natural_direction(root_type: str, amount: float) -> float:
	"""Put a debit-minus-credit balance the way the account normally carries it.

	An expense account with 500 booked to it stands at 500, not at minus 500.
	Everything else about the sheet stays in the ledger's direction, so only
	the figure a person reads is turned round.
	"""
	return amount if root_type in DEBIT_ROOT_TYPES else -amount
