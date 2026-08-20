# Copyright (c) 2026, ALYF GmbH and contributors
# For license information, please see license.txt

"""Finding an account the way a bookkeeper looks for one.

Not alphabetically, and not by the full name that ERPNext stores. By number,
by a word out of the label, or simply by reaching for the account that was
used twenty times this week -- which is why the chart comes back ordered by
recent use rather than by name.

The per company label lives here too. A chart of accounts is a fixed thing
that an auditor expects to recognise, so a company that calls 4830 something
of its own gets a second label instead of a renamed account.
"""

import frappe
from frappe.query_builder.functions import Count, Max
from frappe.utils import add_days, nowdate

USAGE_WINDOW_DAYS = 90


def get_accounts(company: str) -> list[dict]:
	"""The postable chart of accounts, most recently used first.

	Returned in full rather than searched per keystroke: a chart has a few
	thousand accounts, which is nothing to hold in a browser and the only way
	an account can be resolved while the finger is still on the key. Should a
	chart ever outgrow that, this is the place to turn into a query.
	"""
	accounts = frappe.get_all(
		"Account",
		filters={"company": company, "is_group": 0, "disabled": 0},
		fields=["name", "account_number", "account_name", "account_label", "tax_key"],
	)

	usage = get_usage(company)

	rows = [
		{
			"name": account.name,
			"number": account.account_number or "",
			# The company label wins where there is one: it is what the people
			# booking actually call the account.
			"label": account.account_label or account.account_name,
			"tax_key": account.tax_key,
			"uses": usage.get(account.name, {}).get("uses", 0),
			"last_used": usage.get(account.name, {}).get("last_used"),
		}
		for account in accounts
	]

	# Frequently used first, the rest by number: the account being looked for
	# is usually one of a handful, and the long tail only needs to be findable.
	rows.sort(key=lambda row: (-row["uses"], row["number"] or "zzz", row["label"]))
	return rows


def get_usage(company: str, days: int = USAGE_WINDOW_DAYS) -> dict:
	"""How often and how recently each account was posted to."""
	gl_entry = frappe.qb.DocType("GL Entry")
	rows = (
		frappe.qb.from_(gl_entry)
		.select(
			gl_entry.account,
			Count(gl_entry.name).as_("uses"),
			Max(gl_entry.posting_date).as_("last_used"),
		)
		.where(gl_entry.company == company)
		.where(gl_entry.posting_date >= add_days(nowdate(), -days))
		.where(gl_entry.is_cancelled == 0)
		.groupby(gl_entry.account)
	).run(as_dict=True)

	return {row.account: {"uses": row.uses, "last_used": str(row.last_used)} for row in rows}


def account_label(account: str) -> str:
	"""What this account is called here, falling back to its own name."""
	details = frappe.get_cached_value("Account", account, ["account_label", "account_name"], as_dict=True)
	if not details:
		return account

	return details.account_label or details.account_name
