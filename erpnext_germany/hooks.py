app_name = "erpnext_germany"
app_title = "ERPNext Germany"
app_publisher = "ALYF GmbH"
app_description = "App to hold regional code for Germany, built on top of ERPNext."
required_apps = ["frappe/erpnext"]
app_icon = "octicon octicon-file-directory"
app_color = "grey"
app_email = "hallo@alyf.de"
app_license = "GPLv3"

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/erpnext_germany/css/erpnext_germany.css"
# app_include_js = "/assets/erpnext_germany/js/erpnext_germany.js"
app_include_js = [
	"erpnext_germany.bundle.js",
]

# include js, css files in header of web template
# web_include_css = "/assets/erpnext_germany/css/erpnext_germany.css"
# web_include_js = "/assets/erpnext_germany/js/erpnext_germany.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "erpnext_germany/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {
	"Journal Entry": "public/js/journal_entry.js",
	"Company": "public/js/company.js",
}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "erpnext_germany.utils.jinja_methods",
# 	"filters": "erpnext_germany.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "erpnext_germany.install.before_install"
after_install = "erpnext_germany.install.after_install"

# Uninstallation
# ------------

before_uninstall = "erpnext_germany.uninstall.before_uninstall"
# after_uninstall = "erpnext_germany.uninstall.after_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "erpnext_germany.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

TAX_DERIVATION = "erpnext_germany.bookkeeping.tax_derivation"

doc_events = {
	# The Automatikkonto flag is derived from the tax key, never typed, so the
	# chart can be filtered for automatic accounts without the two drifting.
	"Account": {
		"validate": f"{TAX_DERIVATION}.set_automatic_account_flag",
	},
	"Quotation": {
		"on_trash": "erpnext_germany.custom.sales.on_trash",
	},
	"Sales Order": {
		"on_trash": "erpnext_germany.custom.sales.on_trash",
	},
	"Sales Invoice": {
		"on_trash": "erpnext_germany.custom.sales.on_trash",
	},
	"Journal Entry": {
		"validate": "erpnext_germany.bookkeeping.reversal.set_reversal_reason_mandatory",
	},
}

# doc_events = {}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"all": ["erpnext_germany.tasks.all"],
	# 	"daily": [
	# 		"erpnext_germany.tasks.daily"
	# 	],
	# 	"hourly": [
	# 		"erpnext_germany.tasks.hourly"
	# 	],
	# 	"weekly": [
	# 		"erpnext_germany.tasks.weekly"
	# 	],
	# 	"monthly": [
	# 		"erpnext_germany.tasks.monthly"
	# 	],
}

# Testing
# -------

# before_tests = "erpnext_germany.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "erpnext_germany.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "erpnext_germany.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]


# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"erpnext_germany.auth.validate"
# ]

export_python_type_annotations = True

# The standard German tax keys. Rate and effect follow from the law, the
# numbers from the DATEV chart of accounts (SKR03/SKR04). Shipped without tax
# accounts on purpose: those depend on the chart of the individual company and
# are filled in once, per company, by the accountant.
TAX_KEYS = [
	{
		"doctype": "Tax Key",
		"tax_key_name": "Vorsteuer 19 %",
		"key_number": "9",
		"effect": "Input Tax",
		"rate": 19.0,
		"description": "Regelsteuersatz, § 12 Abs. 1 UStG.",
	},
	{
		"doctype": "Tax Key",
		"tax_key_name": "Vorsteuer 7 %",
		"key_number": "8",
		"effect": "Input Tax",
		"rate": 7.0,
		"description": "Ermäßigter Steuersatz, § 12 Abs. 2 UStG.",
	},
	{
		"doctype": "Tax Key",
		"tax_key_name": "Umsatzsteuer 19 %",
		"key_number": "3",
		"effect": "Output Tax",
		"rate": 19.0,
		"description": "Regelsteuersatz, § 12 Abs. 1 UStG.",
	},
	{
		"doctype": "Tax Key",
		"tax_key_name": "Umsatzsteuer 7 %",
		"key_number": "2",
		"effect": "Output Tax",
		"rate": 7.0,
		"description": "Ermäßigter Steuersatz, § 12 Abs. 2 UStG.",
	},
	{
		"doctype": "Tax Key",
		"tax_key_name": "Steuerfrei",
		"key_number": "0",
		"effect": "Tax Free",
		"rate": 0.0,
		"description": "Steuerfreier Umsatz, z. B. § 4 UStG.",
	},
]


# The standard German BWA, in the arrangement a tax advisor and a bank expect
# to see: revenue at the top, the cost blocks in their usual order, and the
# result lines as further steps down the same column.
#
# The account ranges are for SKR03 and have to be confirmed against the chart
# actually in use before anyone reports on them. The report says which
# accounts no line covers, so a wrong or missing range shows up as a figure
# rather than disappearing.
BWA_SCHEMAS = [
	{
		"doctype": "BWA Schema",
		"schema_name": "BWA Standard SKR03",
		"chart_of_accounts": "SKR03",
		"is_default": 1,
		"description": (
			"Standardform der BWA für SKR03. Die Kontenzuordnung ist vor dem produktiven"
			" Einsatz mit dem Steuerberater abzugleichen."
		),
		"rows": [
			{
				"doctype": "BWA Row",
				"row_number": 1,
				"label": "Umsatzerloese",
				"row_type": "Accounts",
				"sign": "+",
				"accounts": "8000-8799",
			},
			{
				"doctype": "BWA Row",
				"row_number": 2,
				"label": "Bestandsveraenderungen",
				"row_type": "Accounts",
				"sign": "+",
				"accounts": "8960-8979",
			},
			{
				"doctype": "BWA Row",
				"row_number": 3,
				"label": "Aktivierte Eigenleistungen",
				"row_type": "Accounts",
				"sign": "+",
				"accounts": "8980-8989",
			},
			{
				"doctype": "BWA Row",
				"row_number": 4,
				"label": "Gesamtleistung",
				"row_type": "Subtotal",
				"sign": "+",
				"from_row": 1,
				"to_row": 3,
			},
			{
				"doctype": "BWA Row",
				"row_number": 5,
				"label": "Material- und Wareneinkauf",
				"row_type": "Accounts",
				"sign": "-",
				"accounts": "3000-3969",
			},
			{
				"doctype": "BWA Row",
				"row_number": 6,
				"label": "Rohertrag",
				"row_type": "Subtotal",
				"sign": "+",
				"from_row": 1,
				"to_row": 5,
			},
			{
				"doctype": "BWA Row",
				"row_number": 7,
				"label": "Sonstige betriebliche Erloese",
				"row_type": "Accounts",
				"sign": "+",
				"accounts": "8800-8959\n2700-2799",
			},
			{
				"doctype": "BWA Row",
				"row_number": 8,
				"label": "Betrieblicher Rohertrag",
				"row_type": "Subtotal",
				"sign": "+",
				"from_row": 1,
				"to_row": 7,
			},
			{
				"doctype": "BWA Row",
				"row_number": 9,
				"label": "Personalkosten",
				"row_type": "Accounts",
				"sign": "-",
				"accounts": "4100-4199",
			},
			{
				"doctype": "BWA Row",
				"row_number": 10,
				"label": "Raumkosten",
				"row_type": "Accounts",
				"sign": "-",
				"accounts": "4200-4299",
			},
			{
				"doctype": "BWA Row",
				"row_number": 11,
				"label": "Betriebliche Steuern",
				"row_type": "Accounts",
				"sign": "-",
				"accounts": "4320-4359",
			},
			{
				"doctype": "BWA Row",
				"row_number": 12,
				"label": "Versicherungen und Beitraege",
				"row_type": "Accounts",
				"sign": "-",
				"accounts": "4360-4399",
			},
			{
				"doctype": "BWA Row",
				"row_number": 13,
				"label": "Besondere Kosten",
				"row_type": "Accounts",
				"sign": "-",
				"accounts": "4400-4499",
			},
			{
				"doctype": "BWA Row",
				"row_number": 14,
				"label": "Fahrzeugkosten",
				"row_type": "Accounts",
				"sign": "-",
				"accounts": "4500-4599",
			},
			{
				"doctype": "BWA Row",
				"row_number": 15,
				"label": "Werbe- und Reisekosten",
				"row_type": "Accounts",
				"sign": "-",
				"accounts": "4600-4699",
			},
			{
				"doctype": "BWA Row",
				"row_number": 16,
				"label": "Kosten der Warenabgabe",
				"row_type": "Accounts",
				"sign": "-",
				"accounts": "4700-4799",
			},
			{
				"doctype": "BWA Row",
				"row_number": 17,
				"label": "Reparatur und Instandhaltung",
				"row_type": "Accounts",
				"sign": "-",
				"accounts": "4800-4819",
			},
			{
				"doctype": "BWA Row",
				"row_number": 18,
				"label": "Abschreibungen",
				"row_type": "Accounts",
				"sign": "-",
				"accounts": "4820-4899",
			},
			{
				"doctype": "BWA Row",
				"row_number": 19,
				"label": "Sonstige Kosten",
				"row_type": "Accounts",
				"sign": "-",
				"accounts": "4900-4999",
			},
			{
				"doctype": "BWA Row",
				"row_number": 20,
				"label": "Gesamtkosten",
				"row_type": "Subtotal",
				"sign": "-",
				"from_row": 9,
				"to_row": 19,
			},
			{
				"doctype": "BWA Row",
				"row_number": 21,
				"label": "Betriebsergebnis",
				"row_type": "Subtotal",
				"sign": "+",
				"from_row": 1,
				"to_row": 19,
			},
			{
				"doctype": "BWA Row",
				"row_number": 22,
				"label": "Zinsaufwand",
				"row_type": "Accounts",
				"sign": "-",
				"accounts": "2100-2149",
			},
			{
				"doctype": "BWA Row",
				"row_number": 23,
				"label": "Sonstiger neutraler Aufwand",
				"row_type": "Accounts",
				"sign": "-",
				"accounts": "2000-2099",
			},
			{
				"doctype": "BWA Row",
				"row_number": 24,
				"label": "Zinsertraege",
				"row_type": "Accounts",
				"sign": "+",
				"accounts": "2650-2699",
			},
			{
				"doctype": "BWA Row",
				"row_number": 25,
				"label": "Sonstiger neutraler Ertrag",
				"row_type": "Accounts",
				"sign": "+",
				"accounts": "2500-2599",
			},
			{
				"doctype": "BWA Row",
				"row_number": 26,
				"label": "Ergebnis vor Steuern",
				"row_type": "Subtotal",
				"sign": "+",
				"from_row": 1,
				"to_row": 25,
			},
			{
				"doctype": "BWA Row",
				"row_number": 27,
				"label": "Steuern vom Einkommen und Ertrag",
				"row_type": "Accounts",
				"sign": "-",
				"accounts": "2200-2289",
			},
			{
				"doctype": "BWA Row",
				"row_number": 28,
				"label": "Vorlaeufiges Ergebnis",
				"row_type": "Subtotal",
				"sign": "+",
				"from_row": 1,
				"to_row": 27,
			},
		],
	},
]

germany_custom_records = [
	*TAX_KEYS,
	*BWA_SCHEMAS,
	{
		"doctype": "DocType Link",
		"parent": "Customer",
		"parentfield": "links",
		"parenttype": "Customize Form",
		"group": "Pre Sales",
		"link_doctype": "VAT ID Check",
		"link_fieldname": "party",
		"custom": 1,
	},
	{
		"doctype": "DocType Link",
		"parent": "Supplier",
		"parentfield": "links",
		"parenttype": "Customize Form",
		"group": "Vendor Evaluation",
		"link_doctype": "VAT ID Check",
		"link_fieldname": "party",
		"custom": 1,
	},
]
