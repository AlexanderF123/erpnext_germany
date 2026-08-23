// Copyright (c) 2026, ALYF GmbH and contributors
// For license information, please see license.txt

frappe.ui.form.on("Posting Batch", {
	refresh(frm) {
		frm.set_query("fiscal_year", () => ({ filters: { disabled: 0 } }));

		for (const fieldname of ["account", "against_account"]) {
			frm.set_query(fieldname, "entries", () => ({
				filters: { company: frm.doc.company, is_group: 0, disabled: 0 },
			}));
		}

		frm.set_query("cost_center", "entries", () => ({
			filters: { company: frm.doc.company, is_group: 0 },
		}));

		if (frm.doc.status === "Posted") {
			frm.set_intro(
				__("This batch has been posted. Corrections are booked as a general reversal."),
				"blue"
			);
			return;
		}

		if (!frm.is_new() && frm.doc.entries?.length) {
			frm.add_custom_button(__("Post Batch"), () => confirm_posting(frm)).addClass(
				"btn-primary"
			);
		}
	},

	company(frm) {
		// Accounts of the previous company would no longer be valid.
		frm.doc.entries?.forEach((entry) => {
			entry.account = null;
			entry.against_account = null;
			entry.cost_center = null;
		});
		frm.refresh_field("entries");
	},
});

frappe.ui.form.on("Posting Batch Entry", {
	entries_add(frm, cdt, cdn) {
		// Carry the previous line forward, the way a batch is typed in practice:
		// same day, same contra account, next document.
		const rows = frm.doc.entries || [];
		const previous = rows[rows.length - 2];
		if (!previous) {
			const row = locals[cdt][cdn];
			row.posting_date = frm.doc.from_date;
			frm.refresh_field("entries");
			return;
		}

		const row = locals[cdt][cdn];
		row.posting_date = previous.posting_date;
		row.against_account = previous.against_account;
		row.direction = previous.direction;
		frm.refresh_field("entries");
	},
});

function confirm_posting(frm) {
	frappe.confirm(
		__("Post {0} entries to the ledger? This cannot be undone.", [frm.doc.entries.length]),
		() => {
			frm.call({
				doc: frm.doc,
				method: "post",
				freeze: true,
				freeze_message: __("Posting entries…"),
				callback: () => frm.reload_doc(),
			});
		}
	);
}
