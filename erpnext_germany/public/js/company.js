// Copyright (c) 2026, ALYF GmbH and contributors
// For license information, please see license.txt

// The tax audit data package is built here because it is filed here: what was
// handed to an auditor stays attached to the company it was handed for.

frappe.ui.form.on("Company", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}

		frm.add_custom_button(
			__("GoBD Export"),
			() => ask_for_fiscal_year(frm),
			__("Bookkeeping")
		);
	},
});

function ask_for_fiscal_year(frm) {
	frappe.prompt(
		{
			fieldtype: "Link",
			fieldname: "fiscal_year",
			label: __("Fiscal Year"),
			options: "Fiscal Year",
			reqd: 1,
			default: erpnext.utils.get_fiscal_year(),
		},
		(values) => build(frm, values.fiscal_year),
		__("GoBD Export"),
		__("Create")
	);
}

function build(frm, fiscal_year) {
	frappe.call({
		method: "erpnext_germany.bookkeeping.gobd_export.export",
		args: { company: frm.doc.name, fiscal_year: fiscal_year },
		freeze: true,
		// A year of books takes a while to write out, and a frozen screen with
		// no explanation reads as a hung one.
		freeze_message: __("Building the audit data package ..."),
		callback: (response) => {
			if (!response.message) {
				return;
			}

			frappe.msgprint({
				title: __("Package Ready"),
				indicator: "green",
				message: __("The package is attached to this company: {0}", [
					`<a href="${response.message}" target="_blank" rel="noopener">${__(
						"Download"
					)}</a>`,
				]),
			});
			frm.reload_doc();
		},
	});
}
