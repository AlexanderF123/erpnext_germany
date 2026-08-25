# Copyright (c) 2026, ALYF GmbH and contributors
# For license information, please see license.txt

"""The checklist a month is read against before it is closed.

One line per check saying how many things it found, and under it the things
themselves, each one clickable through to the account or the voucher. A check
that found nothing still gets its line: the value of a checklist is knowing
that a question was asked, and a list that only shows problems cannot tell the
difference between a clean month and a check that never ran.
"""

import frappe
from frappe import _
from frappe.utils import cint

from erpnext_germany.bookkeeping.month_end import get_titles, run_checks
from erpnext_germany.utils.periods import get_month_range

CLEAN = "Clean"
ATTENTION = "Attention"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.company:
		frappe.throw(_("Choose a company."))

	from_date, to_date = get_period(filters)
	return get_columns(), get_data(filters, from_date, to_date)


def get_period(filters: frappe._dict):
	fiscal_year_start = frappe.get_cached_value("Fiscal Year", filters.fiscal_year, "year_start_date")
	if not fiscal_year_start:
		frappe.throw(_("Fiscal Year {0} not found").format(filters.fiscal_year))

	return get_month_range(fiscal_year_start, cint(filters.month))


def get_columns() -> list[dict]:
	return [
		{"fieldname": "label", "label": _("Check"), "fieldtype": "Data", "width": 340},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
		{"fieldname": "count", "label": _("Findings"), "fieldtype": "Int", "width": 90},
		{"fieldname": "amount", "label": _("Amount"), "fieldtype": "Currency", "width": 150},
		{"fieldname": "detail", "label": _("Detail"), "fieldtype": "Data", "width": 420},
		{
			"fieldname": "account",
			"label": _("Account"),
			"fieldtype": "Link",
			"options": "Account",
			"width": 220,
		},
		{
			"fieldname": "voucher_no",
			"label": _("Voucher"),
			"fieldtype": "Dynamic Link",
			"options": "voucher_type",
			"width": 170,
		},
		{
			"fieldname": "voucher_type",
			"label": _("Voucher Type"),
			"fieldtype": "Data",
			"width": 140,
			"hidden": 1,
		},
	]


def get_data(filters: frappe._dict, from_date, to_date) -> list[dict]:
	results = run_checks(filters.company, from_date, to_date)
	titles = get_titles()
	only_findings = cint(filters.only_findings)

	rows = []
	for name, findings in results.items():
		if only_findings and not findings:
			continue

		rows.append(
			{
				"label": titles.get(name, name),
				"status": ATTENTION if findings else CLEAN,
				"count": len(findings),
				"amount": sum(finding.get("amount") or 0 for finding in findings),
				"indent": 0,
				"is_check": 1,
			}
		)
		rows.extend(
			{
				**finding,
				"indent": 1,
				"is_check": 0,
				"period_from_date": from_date,
				"period_to_date": to_date,
			}
			for finding in findings
		)

	return rows
