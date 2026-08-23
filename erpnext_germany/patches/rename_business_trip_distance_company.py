# Copyright (c) 2026, ALYF GmbH and contributors
# For license information, please see license.txt

"""Give the scope field of a Business Trip Distance a name Frappe will not fill in.

A Link field called `company` is filled from the session default whenever a new
document is created. On a site with a default company that made "leave empty and
the distance counts for everyone" impossible to express: the field was never
empty, so a route entered as a general one answered for one company and went
silent for every other. Renaming it is the whole fix -- there is no per-field way
to opt out of the default.

Existing rows keep their value, so a route that really was meant for one company
stays that way.
"""

import frappe
from frappe.model.utils.rename_field import rename_field


def execute():
	if not frappe.db.table_exists("Business Trip Distance"):
		return

	if not frappe.db.has_column("Business Trip Distance", "company"):
		return

	frappe.reload_doc("erpnext_germany", "doctype", "business_trip_distance")
	rename_field("Business Trip Distance", "company", "for_company")
