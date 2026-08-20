"""Pure tax rules for German bookkeeping.

Kept free of Frappe imports so the rules can be unit tested without a bench.
Anything that reads master data belongs in the controllers.

The rules follow the way an accountant reads a document: one amount is typed,
and the tax follows from the account it is booked to. What that amount means
depends on the effect of the tax key:

* Input tax and output tax are the ordinary domestic cases. The invoice total
  contains the tax, so the amount is gross and the tax is taken out of it.
* Reverse charge (§ 13b UStG) shifts the tax to the recipient. The supplier
  bills the net amount, so that is what is typed, and the tax is added on top
  as a separate pair of postings that offset each other.
* Tax free bookings carry no tax at all.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import NamedTuple

INPUT_TAX = "Input Tax"
OUTPUT_TAX = "Output Tax"
REVERSE_CHARGE = "Reverse Charge"
TAX_FREE = "Tax Free"

EFFECTS = (INPUT_TAX, OUTPUT_TAX, REVERSE_CHARGE, TAX_FREE)

# Effects where the amount on the document already contains the tax.
GROSS_EFFECTS = (INPUT_TAX, OUTPUT_TAX)

CENT = Decimal("0.01")


class TaxAmounts(NamedTuple):
	"""The three amounts of one booking line.

	`gross` is what moves between the account and its contra account, so for
	reverse charge it equals `net`: the tax never touches that pair, it is
	booked to the tax accounts instead.
	"""

	net: float
	tax: float
	gross: float


def split_tax(amount: float, rate: float, effect: str) -> TaxAmounts:
	"""Split one amount into net, tax and gross.

	Rounded commercially to the cent, the way German invoices are. The split is
	derived rather than rounded twice, so `net` and `tax` always add up to
	`gross` exactly and a line can never end up a cent out of balance.
	"""
	if effect not in EFFECTS:
		raise ValueError(f"Unknown tax effect {effect!r}, expected one of {', '.join(EFFECTS)}")

	if amount < 0:
		raise ValueError(f"Amount must not be negative, got {amount!r}")

	if rate < 0:
		raise ValueError(f"Tax rate must not be negative, got {rate!r}")

	if effect == TAX_FREE:
		if rate:
			raise ValueError("A tax free key cannot carry a tax rate.")

		return TaxAmounts(net=_cents(amount), tax=0.0, gross=_cents(amount))

	entered = _decimal(amount)
	percent = _decimal(rate)

	if effect in GROSS_EFFECTS:
		tax = _round(entered * percent / (100 + percent))
		net = _round(entered) - tax
		gross = _round(entered)
	else:
		# Reverse charge: the supplier bills net, the recipient owes the tax.
		net = _round(entered)
		tax = _round(net * percent / 100)
		gross = net

	return TaxAmounts(net=float(net), tax=float(tax), gross=float(gross))


def resolve_tax_key(account_key: str | None, line_key: str | None) -> str | None:
	"""Return the tax key that applies to a line.

	The account carries the default -- this is the Automatikkonto principle:
	booking to a revenue or expense account is enough to get the right tax. A
	key on the line overrides it for the exceptions, which is why the resolved
	key is stored on the line: the override has to be visible afterwards.
	"""
	return line_key or account_key


def _decimal(value: float) -> Decimal:
	return Decimal(str(value))


def _round(value: Decimal) -> Decimal:
	return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _cents(value: float) -> float:
	return float(_round(_decimal(value)))
