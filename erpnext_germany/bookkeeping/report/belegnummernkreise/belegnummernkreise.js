// Copyright (c) 2026, ALYF GmbH and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Belegnummernkreise"] = {
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
			fieldname: "fiscal_year",
			label: __("Fiscal Year"),
			fieldtype: "Link",
			options: "Fiscal Year",
			default: erpnext.utils.get_fiscal_year(),
			reqd: 1,
		},
		{
			fieldname: "document_range",
			label: __("Document Range"),
			fieldtype: "Link",
			options: "Document Range",
			get_query: () => {
				const filters = frappe.query_report.get_filter_values();
				return {
					filters: {
						disabled: 0,
						...(filters.company ? { company: filters.company } : {}),
						...(filters.fiscal_year ? { fiscal_year: filters.fiscal_year } : {}),
					},
				};
			},
		},
	],

	initial_depth: 1,

	formatter(value, row, column, data, default_formatter) {
		const formatted = default_formatter(value, row, column, data);

		if (column.fieldname === "finding" && data && !data.is_range) {
			// A gap is the finding an auditor asks about, so it is the one that
			// has to be visible without reading the row.
			const colour = data.finding === "Gap" ? "red" : "orange";
			return `<span class="indicator ${colour}">${formatted}</span>`;
		}

		if (data && data.is_range) {
			return `<span style="font-weight: 600">${formatted}</span>`;
		}

		return formatted;
	},
};
