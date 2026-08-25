// Copyright (c) 2026, ALYF GmbH and contributors
// For license information, please see license.txt

// A receivable account means a customer, a payable account a supplier. The
// server derives the same thing when it validates; this only spares whoever
// is typing from saying it a second time, because Frappe checks a dynamic
// link before any hook of ours could fill in its type.
const PARTY_TYPES = { Receivable: "Customer", Payable: "Supplier" };
const OPEN_ITEM_TYPES = { Customer: "Sales Invoice", Supplier: "Purchase Invoice" };

frappe.ui.form.on("Posting Batch Entry", {
	account: (frm, cdt, cdn) => set_party_type(cdt, cdn),
	against_account: (frm, cdt, cdn) => set_party_type(cdt, cdn),
});

async function set_party_type(cdt, cdn) {
	const row = locals[cdt][cdn];
	const kinds = await Promise.all(
		["account", "against_account"].map((fieldname) => account_type(row[fieldname]))
	);
	const personal = kinds.find((kind) => PARTY_TYPES[kind]);
	const party_type = personal ? PARTY_TYPES[personal] : null;

	if (row.party_type === party_type) {
		return;
	}

	// Both types have to stand next to their value before the document is
	// saved: Frappe checks a dynamic link before any server hook of ours runs.
	frappe.model.set_value(cdt, cdn, "party_type", party_type);
	frappe.model.set_value(
		cdt,
		cdn,
		"reference_type",
		party_type ? OPEN_ITEM_TYPES[party_type] : null
	);

	if (!party_type) {
		// Nobody left to book against, so nothing may keep pointing at one.
		frappe.model.set_value(cdt, cdn, "party", null);
		frappe.model.set_value(cdt, cdn, "reference_name", null);
	}
}

async function account_type(account) {
	if (!account) {
		return null;
	}

	const value = await frappe.db.get_value("Account", account, "account_type");
	return value?.message?.account_type || null;
}

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

		frm.set_query("reference_name", "entries", (doc, cdt, cdn) => {
			const row = locals[cdt][cdn];
			return {
				filters: {
					company: frm.doc.company,
					docstatus: 1,
					outstanding_amount: ["!=", 0],
					[row.party_type === "Supplier" ? "supplier" : "customer"]: row.party,
				},
			};
		});

		if (frm.doc.status === "Posted") {
			frm.set_intro(
				__("This batch has been posted. Corrections are booked as a general reversal."),
				"blue"
			);
			return;
		}

		if (!frm.is_new()) {
			// The form is for looking at a batch and correcting single lines;
			// typing a stack of documents belongs on the fast entry screen.
			frm.add_custom_button(__("Fast Entry"), () =>
				frappe.set_route("fast-entry", frm.doc.name)
			);
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
