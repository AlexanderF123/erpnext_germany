from frappe import get_installed_apps

from .constants import REGISTER_COURTS


def _(message: str) -> str:
	return message


def get_register_fields(insert_after: str):
	return [
		{
			"fieldtype": "Section Break",
			"fieldname": "register_sb_1",
			"label": _("Register Information"),
			"insert_after": insert_after,
			"collapsible": 1,
		},
		{
			"fieldtype": "Select",
			"fieldname": "register_type",
			"label": _("Register Type"),
			"insert_after": "register_sb_1",
			"options": "\nHRA\nHRB\nGnR\nPR\nVR",
			"translatable": 0,
		},
		{
			"fieldtype": "Column Break",
			"fieldname": "register_cb_1",
			"insert_after": "register_type",
		},
		{
			"fieldtype": "Data",
			"fieldname": "register_number",
			"label": _("Register Number"),
			"insert_after": "register_cb_1",
			"translatable": 0,
		},
		{
			"fieldtype": "Column Break",
			"fieldname": "register_cb_2",
			"insert_after": "register_number",
		},
		{
			"fieldtype": "Select",
			"fieldname": "register_court",
			"label": _("Register Court"),
			"insert_after": "register_cb_2",
			"options": "\n".join(["", *REGISTER_COURTS]),  # empty string to be able to select nothing
			"translatable": 0,
		},
	]


def get_custom_fields():
	custom_fields = {
		"Company": get_register_fields(insert_after="registration_details"),
		"Customer": get_register_fields(insert_after="customer_details"),
		"Supplier": get_register_fields(insert_after="language"),
		"Employee": [
			{
				"fieldtype": "Link",
				"fieldname": "nationality",
				"label": _("Nationality"),
				"options": "Country",
				"insert_after": "date_of_joining",
			},
			{
				"fieldtype": "Check",
				"fieldname": "is_severely_disabled",
				"label": _("Is Severely Disabled"),
				"insert_after": "nationality",
			},
			{
				"fieldtype": "Float",
				"fieldname": "working_hours_per_week",
				"label": _("Working Hours Per Week"),
				"insert_after": "attendance_device_id",
			},
			# -- BEGIN TAXES SECTION --
			{
				"fieldtype": "Section Break",
				"fieldname": "employee_taxes_sb",
				"label": _("Taxes"),
				"insert_after": "default_shift",
				"collapsible": 1,
			},
			{
				"fieldtype": "Data",
				"fieldname": "tax_id",
				"label": _("Tax ID"),
				"insert_after": "employee_taxes_sb",
				"translatable": 0,
			},
			{
				"fieldtype": "Data",
				"fieldname": "tax_office",
				"label": _("Tax Office"),
				"insert_after": "tax_id",
				"translatable": 0,
			},
			{
				"fieldtype": "Data",
				"fieldname": "tax_office_number",
				"label": _("Tax Office Number"),
				"insert_after": "tax_office",
				"translatable": 0,
			},
			{
				"fieldtype": "Column Break",
				"fieldname": "employee_taxes_cb",
				"insert_after": "tax_office_number",
			},
			{
				"fieldtype": "Select",
				"fieldname": "tax_bracket",
				"label": _("Tax Bracket"),
				"options": "\nI\nII\nIII\nIV\nV\nVI",
				"insert_after": "employee_taxes_cb",
				"translatable": 0,
			},
			{
				"fieldtype": "Int",
				"fieldname": "children_eligible_for_tax_credits",
				"label": _("Children Eligible for Tax Credits"),
				"insert_after": "tax_bracket",
			},
			{
				"fieldtype": "Link",
				"fieldname": "religious_denomination",
				"label": _("Religious Denomination"),
				"options": "Religious Denomination",
				"insert_after": "children_eligible_for_tax_credits",
			},
			# -- END TAXES SECTION --
			{
				"fieldtype": "Check",
				"fieldname": "has_children",
				"label": _("Has Children"),
				"insert_after": "health_insurance_no",
			},
			{
				"fieldtype": "Check",
				"fieldname": "has_other_employments",
				"label": _("Has Other Employments"),
				"insert_after": "external_work_history",
			},
			{
				"fieldtype": "Select",
				"fieldname": "highest_school_qualification",
				"label": _("Highest School Qualification"),
				"options": "\n".join(
					[
						"",
						"Ohne Schulabschluss",
						"Haupt-/Volksschulabschluss",
						"Mitttlere Reife",
						"(Fach-)Abitur",
					]
				),
				"insert_after": "education",
				"translatable": 0,
			},
		],
		"Purchase Invoice": [
			{
				"fieldtype": "Link",
				"fieldname": "business_trip",
				"label": _("Business Trip"),
				"options": "Business Trip",
				"insert_after": "apply_tds",
			},
			{
				"fieldtype": "Link",
				"fieldname": "business_trip_employee",
				"label": _("Business Trip Employee"),
				"options": "Employee",
				"insert_after": "business_trip",
				"read_only": 0,  # kept 0 on purpose to override former value
				"read_only_depends_on": "business_trip",
				"mandatory_depends_on": "pay_to_employee",
				"fetch_from": "business_trip.employee",
				"fetch_if_empty": 1,
				"depends_on": "eval: doc.business_trip || doc.pay_to_employee",
				"ignore_user_permissions": 1,
			},
			{
				"fieldtype": "Check",
				"fieldname": "pay_to_employee",
				"label": _("Pay to Employee"),
				"insert_after": "business_trip_employee",
				"depends_on": "",  # kept empty on purpose to override former value
				"description": _(
					"If checked, the invoice was advanced by the employee and must be reimbursed."
				),
			},
		],
		("Quotation", "Sales Order", "Sales Invoice"): [
			{
				"label": _("Tax Exemption Reason"),
				"fieldtype": "Small Text",
				"fieldname": "tax_exemption_reason",
				"fetch_from": "taxes_and_charges.tax_exemption_reason",
				"depends_on": "tax_exemption_reason",
				"insert_after": "taxes_and_charges",
				"translatable": 0,
			}
		],
		"Sales Taxes and Charges Template": [
			{
				"label": _("Tax Exemption Reason"),
				"fieldtype": "Small Text",
				"fieldname": "tax_exemption_reason",
				"insert_after": "tax_category",
				"translatable": 0,
			}
		],
		# A posted entry is never deleted and never edited, only reversed -- and
		# the reversal has to say why and stay tied to what it undoes.
		#
		# Prefixed on purpose: ERPNext has a "reversal_of" of its own, which
		# belongs to the Exchange Rate Revaluation and means something else.
		# Sharing that field would make our rules fire on its entries.
		"Journal Entry": [
			{
				"fieldtype": "Section Break",
				"fieldname": "german_reversal_sb",
				"label": _("General Reversal"),
				"insert_after": "user_remark",
				"collapsible": 1,
				"collapsible_depends_on": "eval: doc.general_reversal_of || doc.general_reversal_by",
			},
			{
				"fieldtype": "Link",
				"fieldname": "general_reversal_of",
				"label": _("General Reversal Of"),
				"options": "Journal Entry",
				"read_only": 1,
				"insert_after": "german_reversal_sb",
				"no_copy": 1,
			},
			{
				"fieldtype": "Small Text",
				"fieldname": "reversal_reason",
				"label": _("Reversal Reason"),
				"depends_on": "general_reversal_of",
				"mandatory_depends_on": "general_reversal_of",
				"read_only_depends_on": "eval: doc.docstatus > 0",
				"insert_after": "general_reversal_of",
				"no_copy": 1,
			},
			{
				"fieldtype": "Link",
				"fieldname": "general_reversal_by",
				"label": _("Reversed By"),
				"options": "Journal Entry",
				"read_only": 1,
				# Set once the reversal exists, which is after this entry was
				# posted -- hence editable after submit.
				"allow_on_submit": 1,
				"insert_after": "reversal_reason",
				"no_copy": 1,
			},
		],
		"Account": [
			{
				"fieldtype": "Data",
				"fieldname": "account_label",
				"label": _("Account Label"),
				"description": _(
					"What this company calls the account. Used for entry and reports; the chart of"
					" accounts itself stays as it is."
				),
				"insert_after": "account_name",
				"translatable": 0,
			},
			# The Automatikkonto principle: the tax hangs on the account, so
			# booking to it is enough to get rate, tax account and tax amount.
			{
				"fieldtype": "Section Break",
				"fieldname": "german_tax_sb",
				"label": _("Tax Derivation"),
				"insert_after": "tax_rate",
				"collapsible": 1,
			},
			{
				"fieldtype": "Link",
				"fieldname": "tax_key",
				"label": _("Tax Key"),
				"options": "Tax Key",
				"description": _("Bookings to this account derive their tax from this key."),
				"insert_after": "german_tax_sb",
			},
			{
				"fieldtype": "Check",
				"fieldname": "is_automatic_account",
				"label": _("Automatic Account"),
				"description": _("Set automatically for every account that has a tax key."),
				"read_only": 1,
				"in_standard_filter": 1,
				"insert_after": "tax_key",
			},
		],
	}

	if "hrms" in get_installed_apps():
		custom_fields["Expense Claim"] = [
			{
				"fieldtype": "Link",
				"fieldname": "business_trip",
				"label": _("Business Trip"),
				"options": "Business Trip",
				"insert_after": "company",
			},
		]

	return custom_fields
