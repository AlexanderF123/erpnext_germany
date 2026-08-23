// Copyright (c) 2026, ALYF GmbH and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Kontoblatt"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "account",
			label: __("Account"),
			fieldtype: "Link",
			options: "Account",
			reqd: 1,
			get_query: () => {
				const company = frappe.query_report.get_filter_value("company");
				return { filters: { is_group: 0, ...(company ? { company } : {}) } };
			},
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.year_start(),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.year_end(),
			reqd: 1,
		},
		{
			fieldname: "cost_center",
			label: __("Cost Center"),
			fieldtype: "Link",
			options: "Cost Center",
			get_query: () => {
				const company = frappe.query_report.get_filter_value("company");
				return { filters: company ? { company: company } : {} };
			},
		},
	],

	formatter(value, row, column, data, default_formatter) {
		// The paperclip is what makes the last step of the drill-down one click:
		// from the booking to the paper it was made from.
		if (column.fieldname === "voucher_no" && data && data.attachments?.length) {
			return `${default_formatter(value, row, column, data)} ${document_link(data)}`;
		}

		const formatted = default_formatter(value, row, column, data);
		if (data && data.is_opening) {
			return `<span style="font-weight: 600">${formatted}</span>`;
		}

		return formatted;
	},

	onload(report) {
		report.page.add_inner_button(__("Close Document"), () =>
			erpnext_germany.account_sheet.close_document()
		);

		// Delegated once for the whole sheet: the rows are redrawn on every
		// refresh, and a listener per row would be re-attached each time.
		report.page.wrapper.on("click", "[data-egd-document]", (event) => {
			event.preventDefault();
			const target = event.currentTarget;
			erpnext_germany.account_sheet.show_document(
				target.dataset.egdDocument,
				target.dataset.egdTitle
			);
		});
	},
};

function document_link(data) {
	const first = data.attachments[0];
	const more = data.attachments.length > 1 ? ` ${data.attachments.length}` : "";

	return `<a href="#" data-egd-document="${frappe.utils.escape_html(first.url)}"
		data-egd-title="${frappe.utils.escape_html(first.name || "")}"
		title="${__("Show document")}">📎${more}</a>`;
}
