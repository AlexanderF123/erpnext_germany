// Copyright (c) 2026, ALYF GmbH and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Betriebswirtschaftliche Auswertung"] = {
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
			fieldname: "bwa_schema",
			label: __("BWA Schema"),
			fieldtype: "Link",
			options: "BWA Schema",
			reqd: 1,
			get_query: () => ({ filters: { disabled: 0 } }),
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
			fieldname: "month",
			label: __("Month"),
			fieldtype: "Select",
			default: get_previous_month(),
			options: [
				{ value: 1, label: __("January") },
				{ value: 2, label: __("February") },
				{ value: 3, label: __("March") },
				{ value: 4, label: __("April") },
				{ value: 5, label: __("May") },
				{ value: 6, label: __("June") },
				{ value: 7, label: __("July") },
				{ value: 8, label: __("August") },
				{ value: 9, label: __("September") },
				{ value: 10, label: __("October") },
				{ value: 11, label: __("November") },
				{ value: 12, label: __("December") },
			],
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
		{
			fieldname: "show_accounts",
			label: __("Show Accounts"),
			fieldtype: "Check",
			default: 1,
		},
	],

	// The accounts sit under the line they belong to, so the sheet reads as a
	// BWA at a glance and opens up where a figure is queried. The nesting comes
	// from the indent the report puts on every row; the depth of nought is what
	// makes it open closed.
	initial_depth: 0,

	onload(report) {
		set_default_schema(report);
	},

	formatter(value, row, column, data, default_formatter) {
		if (column.fieldname === "label" && data && data.account) {
			return get_ledger_link(data);
		}

		// A ratio line holds a percentage in the same columns the other lines
		// hold money in, so it has to say so rather than read as an amount.
		if (data && data.is_ratio && column.fieldtype === "Currency") {
			value = value == null ? "" : `${format_number(value, null, 1)} %`;
			return `<span style="font-weight: 600">${value}</span>`;
		}

		const formatted = default_formatter(value, row, column, data);
		if (data && data.is_result) {
			return `<span style="font-weight: 600">${formatted}</span>`;
		}

		return formatted;
	},
};

function set_default_schema(report) {
	/* Open on the arrangement marked as the default, so the report is usable
	without a decision the first time it is opened. */
	if (frappe.query_report.get_filter_value("bwa_schema")) {
		return;
	}

	frappe.db
		.get_value("BWA Schema", { is_default: 1, disabled: 0 }, "name")
		.then(({ message }) => {
			if (message && message.name) {
				report.set_filter_value("bwa_schema", message.name);
			}
		});
}

function get_previous_month() {
	/* Return the 1-indexed number of the previous month */
	const date = new Date();
	date.setDate(0); // set to last day of previous month
	return date.getMonth() + 1; // getMonth() is 0-indexed
}

function get_ledger_link(data) {
	/* Link an account to its ledger for the evaluated period.

	The period boundaries are supplied by the report itself, so the dates always
	match the figures in the row. */
	const filters = frappe.query_report.get_filter_values();
	const params = {
		company: filters.company,
		account: data.account,
		from_date: data.period_from_date,
		to_date: data.period_to_date,
		group_by: "Group by Voucher (Consolidated)",
	};
	if (filters.cost_center) {
		params.cost_center = filters.cost_center;
	}

	const query = Object.entries(params)
		.filter(([, val]) => val)
		.map(([key, val]) => `${key}=${encodeURIComponent(val)}`)
		.join("&");

	return `<a href="/app/query-report/General%20Ledger?${query}">${frappe.utils.escape_html(
		data.label
	)}</a>`;
}
