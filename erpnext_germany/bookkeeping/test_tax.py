import pytest

from .tax import (
	INPUT_TAX,
	OUTPUT_TAX,
	REVERSE_CHARGE,
	TAX_FREE,
	resolve_tax_key,
	split_tax,
)


def test_takes_nineteen_percent_out_of_a_gross_amount():
	"""The classic domestic invoice: 119,00 EUR is 100,00 plus 19,00."""
	assert split_tax(119.0, 19.0, INPUT_TAX) == (100.0, 19.0, 119.0)


def test_takes_seven_percent_out_of_a_gross_amount():
	assert split_tax(107.0, 7.0, OUTPUT_TAX) == (100.0, 7.0, 107.0)


def test_input_and_output_tax_split_the_same_way():
	"""Which side of the ledger the tax lands on does not change the split."""
	assert split_tax(119.0, 19.0, INPUT_TAX) == split_tax(119.0, 19.0, OUTPUT_TAX)


def test_net_and_tax_always_add_up_to_the_gross():
	"""No line may end up a cent out of balance.

	The tax is rounded once and the net is the remainder, so the two can never
	drift apart -- which matters because both go into the same double entry.
	"""
	for amount in (0.01, 0.03, 1.0, 9.99, 33.33, 100.0, 119.0, 1234.56, 99999.99):
		for rate in (7.0, 19.0):
			net, tax, gross = split_tax(amount, rate, INPUT_TAX)
			assert round(net + tax, 2) == gross == round(amount, 2)


def test_rounds_half_up_like_a_german_invoice():
	"""0,105 becomes 0,11, not 0,10.

	Python rounds halves to even by default, which would quietly under-report
	the tax on every other borderline amount.
	"""
	# 0.66 gross at 19 % is 0.10537... -> 0.11
	assert split_tax(0.66, 19.0, INPUT_TAX) == (0.55, 0.11, 0.66)


def test_reverse_charge_adds_the_tax_on_top():
	"""The supplier bills net; the recipient owes the tax (§ 13b UStG).

	So the amount that moves between account and contra account stays the net
	amount, and the tax is booked separately.
	"""
	assert split_tax(1000.0, 19.0, REVERSE_CHARGE) == (1000.0, 190.0, 1000.0)


def test_tax_free_carries_no_tax():
	assert split_tax(500.0, 0.0, TAX_FREE) == (500.0, 0.0, 500.0)


def test_tax_free_rejects_a_rate():
	"""A key that is both tax free and taxed is a contradiction, not a default."""
	with pytest.raises(ValueError, match="tax free key cannot carry a tax rate"):
		split_tax(500.0, 19.0, TAX_FREE)


def test_a_zero_rate_leaves_the_amount_untouched():
	assert split_tax(500.0, 0.0, INPUT_TAX) == (500.0, 0.0, 500.0)


def test_rejects_an_unknown_effect():
	with pytest.raises(ValueError, match="Unknown tax effect"):
		split_tax(119.0, 19.0, "Vorsteuer")


def test_rejects_a_negative_amount():
	with pytest.raises(ValueError, match="Amount must not be negative"):
		split_tax(-119.0, 19.0, INPUT_TAX)


def test_rejects_a_negative_rate():
	with pytest.raises(ValueError, match="Tax rate must not be negative"):
		split_tax(119.0, -19.0, INPUT_TAX)


def test_the_line_key_overrides_the_account_key():
	assert resolve_tax_key("VSt 19", "RC 19") == "RC 19"


def test_the_account_key_applies_when_the_line_has_none():
	"""The Automatikkonto principle: the account alone is enough."""
	assert resolve_tax_key("VSt 19", None) == "VSt 19"


def test_no_key_at_all_stays_empty():
	assert resolve_tax_key(None, None) is None
