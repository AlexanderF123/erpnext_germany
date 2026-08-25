// Copyright (c) 2026, ALYF GmbH and contributors
// For license information, please see license.txt

// A posted entry is corrected by a general reversal, never by editing or
// deleting it. The button is the only route to one, so that no reversal can
// exist without a reason attached to it.

frappe.ui.form.on("Journal Entry", {
	refresh(frm) {
		show_reversal_state(frm);
		add_reversal_button(frm);
	},
});

function add_reversal_button(frm) {
	if (frm.doc.docstatus !== 1 || frm.doc.general_reversal_by || frm.doc.general_reversal_of) {
		return;
	}

	frm.add_custom_button(__("General Reversal"), () => ask_for_reason(frm));
}

function show_reversal_state(frm) {
	if (frm.doc.general_reversal_of) {
		frm.dashboard.add_comment(
			__("This entry reverses {0}.", [
				frappe.utils.get_form_link("Journal Entry", frm.doc.general_reversal_of, true),
			]),
			"blue",
			true
		);
	}

	if (frm.doc.general_reversal_by) {
		frm.dashboard.add_comment(
			__("This entry was reversed by {0}.", [
				frappe.utils.get_form_link("Journal Entry", frm.doc.general_reversal_by, true),
			]),
			"orange",
			true
		);
	}
}

function ask_for_reason(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("General Reversal"),
		fields: [
			{
				fieldtype: "Small Text",
				fieldname: "reason",
				label: __("Reversal Reason"),
				reqd: 1,
				description: __("Why this entry is being corrected. Stays with the reversal."),
			},
			{
				fieldtype: "Date",
				fieldname: "posting_date",
				label: __("Posting Date"),
				// Today rather than the original date: the period the mistake
				// sits in is usually closed, and a correction belongs in the
				// period it is made in.
				default: frappe.datetime.get_today(),
				reqd: 1,
			},
		],
		primary_action_label: __("Reverse", null, "General reversal dialog"),
		primary_action(values) {
			dialog.hide();
			reverse(frm, values);
		},
	});

	dialog.show();
}

function reverse(frm, values) {
	frappe.call({
		method: "erpnext_germany.bookkeeping.reversal.reverse_entry",
		args: {
			journal_entry: frm.doc.name,
			reason: values.reason,
			posting_date: values.posting_date,
		},
		freeze: true,
		freeze_message: __("Reversing ..."),
		callback: () => frm.reload_doc(),
	});
}
