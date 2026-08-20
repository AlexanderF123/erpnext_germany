# Copyright (c) 2026, ALYF GmbH and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Company"]

TEST_COMPANY = "_Test Company"
OTHER_COMPANY = "_Test Company 2"


def ledger_accounts(count: int, company: str = TEST_COMPANY) -> list[str]:
	accounts = frappe.get_all(
		"Account",
		filters={"company": company, "is_group": 0, "disabled": 0},
		pluck="name",
		order_by="name asc",
		limit=count,
	)
	if len(accounts) < count:
		raise ValueError(f"Need {count} ledger accounts for {company}")

	return accounts


def group_account(company: str = TEST_COMPANY) -> str:
	return frappe.db.get_value("Account", {"company": company, "is_group": 1}, "name")


class TestTaxKey(FrappeTestCase):
	def setUp(self):
		self.first, self.second = ledger_accounts(2)

	def make(self, **kwargs):
		defaults = {
			"doctype": "Tax Key",
			"tax_key_name": "Test Key",
			"key_number": "99",
			"effect": "Input Tax",
			"rate": 19.0,
		}
		defaults.update(kwargs)
		return frappe.get_doc(defaults)

	def test_a_tax_free_key_cannot_carry_a_rate(self):
		"""Tax free and taxed at once is a contradiction, not a default."""
		key = self.make(effect="Tax Free", rate=19.0)

		self.assertRaises(frappe.ValidationError, key.insert)

	def test_a_rate_above_one_hundred_percent_is_refused(self):
		self.assertRaises(frappe.ValidationError, self.make(rate=120.0).insert)

	def test_one_company_cannot_have_two_tax_accounts(self):
		key = self.make(
			accounts=[
				{"company": TEST_COMPANY, "tax_account": self.first},
				{"company": TEST_COMPANY, "tax_account": self.second},
			]
		)

		self.assertRaises(frappe.ValidationError, key.insert)

	def test_the_tax_account_must_belong_to_its_company(self):
		other = ledger_accounts(1, OTHER_COMPANY)[0]
		key = self.make(accounts=[{"company": TEST_COMPANY, "tax_account": other}])

		self.assertRaises(frappe.ValidationError, key.insert)

	def test_a_group_account_cannot_take_tax(self):
		key = self.make(accounts=[{"company": TEST_COMPANY, "tax_account": group_account()}])

		self.assertRaises(frappe.ValidationError, key.insert)

	def test_reverse_charge_needs_a_deductible_account(self):
		"""Without it the offsetting pair is missing and the entry never balances."""
		key = self.make(
			effect="Reverse Charge",
			accounts=[{"company": TEST_COMPANY, "tax_account": self.first}],
		)

		self.assertRaises(frappe.ValidationError, key.insert)

	def test_a_deductible_account_only_applies_to_reverse_charge(self):
		key = self.make(
			effect="Input Tax",
			accounts=[
				{
					"company": TEST_COMPANY,
					"tax_account": self.first,
					"deductible_tax_account": self.second,
				}
			],
		)

		self.assertRaises(frappe.ValidationError, key.insert)

	def test_the_accounts_are_looked_up_per_company(self):
		"""Rate and effect are the same everywhere, only the account differs."""
		other = ledger_accounts(1, OTHER_COMPANY)[0]
		key = self.make(
			accounts=[
				{"company": TEST_COMPANY, "tax_account": self.first},
				{"company": OTHER_COMPANY, "tax_account": other},
			]
		)
		key.insert()

		self.assertEqual(key.get_accounts_for(TEST_COMPANY).tax_account, self.first)
		self.assertEqual(key.get_accounts_for(OTHER_COMPANY).tax_account, other)
		self.assertIsNone(key.get_accounts_for("_Test Company 3"))


class TestAutomaticAccountFlag(FrappeTestCase):
	"""The Automatikkonto flag is derived, never typed."""

	def test_the_flag_follows_the_tax_key(self):
		account = ledger_accounts(1)[0]
		key = frappe.get_doc(
			{
				"doctype": "Tax Key",
				"tax_key_name": "Flag Key",
				"key_number": "98",
				"effect": "Input Tax",
				"rate": 19.0,
			}
		).insert()

		doc = frappe.get_doc("Account", account)
		doc.tax_key = key.name
		doc.save()
		self.assertEqual(doc.is_automatic_account, 1)

		doc.tax_key = None
		doc.save()
		self.assertEqual(doc.is_automatic_account, 0)
