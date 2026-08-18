// Copyright (c) 2026, ALYF GmbH and contributors
// For license information, please see license.txt

frappe.ui.form.on("Ledger Lockdown", {
	refresh(frm) {
		if (frm.is_new()) {
			frm.set_intro(
				__(
					"Everything posted on or before this date becomes unchangeable. A lockdown cannot be undone."
				),
				"orange"
			);
			return;
		}

		frm.set_intro(
			__("{0} is locked up to {1}.", [
				frm.doc.company,
				frappe.datetime.str_to_user(frm.doc.locked_up_to),
			]),
			"blue"
		);
		frm.disable_save();
	},

	before_save(frm) {
		// The flag stops the second pass from asking again, which would
		// otherwise loop: the confirmation saves, which runs before_save again.
		if (!frm.is_new() || frm.__lockdown_confirmed) {
			return;
		}

		frappe.validated = false;
		frappe.confirm(
			__("Lock {0} up to {1}? This cannot be undone.", [
				frm.doc.company,
				frappe.datetime.str_to_user(frm.doc.locked_up_to),
			]),
			() => {
				frm.__lockdown_confirmed = true;
				frm.save();
			}
		);
	},
});
