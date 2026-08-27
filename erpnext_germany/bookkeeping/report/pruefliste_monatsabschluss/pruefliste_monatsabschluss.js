// Copyright (c) 2026, ALYF GmbH and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Pruefliste Monatsabschluss"] = {
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
			fieldname: "only_findings",
			label: __("Only Checks With Findings"),
			fieldtype: "Check",
			default: 0,
		},
	],

	initial_depth: 1,

	formatter(value, row, column, data, default_formatter) {
		// The account of a finding leads to its Kontoblatt for the same period,
		// so the next question after "what is this" can be asked in one click.
		if (column.fieldname === "account" && data && data.account && !data.is_check) {
			return erpnext_germany.account_sheet.link({
				company: frappe.query_report.get_filter_value("company"),
				account: data.account,
				from_date: data.period_from_date,
				to_date: data.period_to_date,
			});
		}

		const formatted = default_formatter(value, row, column, data);

		if (column.fieldname === "status" && data && data.is_check) {
			const clean = value === "Clean";
			const label = clean ? __("Clean") : __("Attention");
			return `<span class="indicator ${clean ? "green" : "orange"}">${label}</span>`;
		}

		if (data && data.is_check) {
			return `<span style="font-weight: 600">${formatted}</span>`;
		}

		return formatted;
	},

	onload(report) {
		report.page.add_inner_button(__("File With The Company"), () => file_result(report));
	},
};

function file_result(report) {
	/* Keep the result with the company. The question an auditor asks later is
	not whether there was a checklist, but what the people who closed the month
	saw when they closed it. */
	const filters = frappe.query_report.get_filter_values();
	const [from_date, to_date] = report_period(report);

	frappe.call({
		method: "erpnext_germany.bookkeeping.month_end.archive",
		args: { company: filters.company, from_date, to_date },
		freeze: true,
		callback: (response) => {
			if (response.message) {
				frappe.show_alert({ message: __("Filed with the company."), indicator: "green" });
			}
		},
	});
}

function report_period(report) {
	/* The report already worked the period out from the fiscal year and the
	month; taking it back off a row keeps the two from disagreeing. */
	const row = (report.data || []).find((entry) => entry.period_from_date);

	return row ? [row.period_from_date, row.period_to_date] : [null, null];
}

function get_previous_month() {
	/* Return the 1-indexed number of the previous month */
	const date = new Date();
	date.setDate(0); // set to last day of previous month
	return date.getMonth() + 1; // getMonth() is 0-indexed
}
