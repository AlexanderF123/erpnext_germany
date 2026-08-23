PROTECTED_FILE_DOCTYPES = (
	"Quotation",
	"Sales Order",
	"Delivery Note",
	"Sales Invoice",
	"Request for Quotation",
	"Supplier Quotation",
	"Purchase Order",
	"Purchase Receipt",
	"Purchase Invoice",
	"Journal Entry",
	"Payment Entry",
	"Asset",
	"Asset Depreciation Schedule",
	"Asset Repair",
	"Asset Value Adjustment",
	"Asset Capitalization",
	"POS Invoice",
	"Dunning",
	"Business Letter",
	"Period Closing Voucher",
	"Contract",
	"Blanket Order",
)


def get_property_setters():
	return {
		"Employee": [
			("salary_currency", "default", "EUR"),
			("salary_mode", "default", "Bank"),
			("permanent_accommodation_type", "hidden", 1),
			("current_accommodation_type", "hidden", 1),
		],
		PROTECTED_FILE_DOCTYPES: [
			(None, "protect_attached_files", 1),
		],
		# So that typing a number or a word out of the label finds the account
		# in every link field, not just in the fast entry screen. Extending the
		# search fields leaves ERPNext's own filtering untouched, which
		# replacing the link query would not.
		"Account": [
			(None, "search_fields", "account_number,account_label"),
		],
	}
