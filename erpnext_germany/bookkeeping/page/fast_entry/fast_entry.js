// Copyright (c) 2026, ALYF GmbH and contributors
// For license information, please see license.txt

/**
 * Fast entry: one booking per line, typed without leaving the keyboard.
 *
 * The screen exists because the standard form is built for one careful
 * document, while bookkeeping is a hundred quick ones. Three rules follow from
 * that and explain most of the code below.
 *
 * Nothing waits for the server. The chart of accounts, the tax keys and the
 * text shortcuts arrive once when the screen opens, so resolving an account by
 * number or by name happens between two keystrokes.
 *
 * Enter never blocks. The line is shown immediately and the save runs behind
 * it, so the next document can be typed while the previous one is still on its
 * way. A line that the server refuses turns red and keeps its values.
 *
 * Nothing typed is ever lost. Saved lines live in the batch, and the line
 * currently being typed is kept in the browser, so closing the tab by accident
 * costs nothing.
 */

frappe.provide("erpnext_germany");

// The tab order of the DATEV entry mask. Fingers that know it should not have
// to relearn anything, which is the whole point of this screen.
// Several columns carry the word the entry mask uses rather than the word the
// rest of the system uses -- "Umsatz" for an amount, "BU-Schluessel" for a tax
// key. The context keeps those apart from the same English word elsewhere, so
// renaming a column here cannot rename a field somewhere else.
const COLUMN = "Entry mask column";

const FIELDS = [
	{ fieldname: "amount", label: __("Amount", null, COLUMN), kind: "amount", width: 120 },
	{
		fieldname: "direction",
		label: __("D/C", null, "Debit or credit column"),
		kind: "direction",
		width: 60,
	},
	{ fieldname: "tax_key", label: __("Tax Key", null, COLUMN), kind: "tax_key", width: 110 },
	{ fieldname: "against_account", label: __("Contra Account"), kind: "account", width: 190 },
	{ fieldname: "document_number", label: __("Document Number"), kind: "text", width: 120 },
	{
		fieldname: "document_number_2",
		label: __("Second Document Number"),
		kind: "text",
		width: 120,
	},
	{
		fieldname: "posting_date",
		label: __("Posting Date", null, COLUMN),
		kind: "date",
		width: 110,
	},
	{ fieldname: "account", label: __("Account"), kind: "account", width: 190 },
	{ fieldname: "party", label: __("Party", null, COLUMN), kind: "party", width: 170 },
	{
		fieldname: "reference_name",
		label: __("Open Item", null, COLUMN),
		kind: "open_item",
		width: 150,
	},
	{
		fieldname: "cost_center",
		label: __("Cost Center", null, COLUMN),
		kind: "cost_center",
		width: 150,
	},
	{ fieldname: "remark", label: __("Remark", null, COLUMN), kind: "remark", width: 200 },
];

// The person carries over like the account does -- a stack of statements is
// usually one tenant's. The open item never does: each payment settles a
// different invoice, and a carried one would settle the wrong.
const CARRIED_OVER = ["posting_date", "account", "against_account", "cost_center", "party"];
const ACCOUNT_FIELDS = ["account", "against_account"];
const PARTY_FIELDS = ["party", "reference_name"];
const DRAFT_KEY = "erpnext_germany:fast_entry:line";
const MAX_SUGGESTIONS = 8;

frappe.pages["fast-entry"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Fast Entry"),
		single_column: true,
	});

	new erpnext_germany.FastEntry(page);
};

erpnext_germany.FastEntry = class FastEntry {
	constructor(page) {
		this.page = page;
		this.context = null;
		this.inputs = {};
		this.suggestions = null;
		// Balances are asked for once per account and then kept: nothing is
		// posted while this screen is open, so the figure cannot go stale.
		this.balances = {};

		this.make_batch_field();
		this.make_body();
		this.bind_shortcuts();
		this.restore_from_route();
	}

	// --- chrome ----------------------------------------------------------

	make_batch_field() {
		this.batch_field = this.page.add_field({
			fieldname: "batch",
			label: __("Posting Batch"),
			fieldtype: "Link",
			options: "Posting Batch",
			get_query: () => ({ filters: { status: "Open" } }),
			change: () => {
				const value = this.batch_field.get_value();
				if (value && value !== this.context?.batch?.name) {
					this.load(value);
				}
			},
		});

		this.page.set_secondary_action(__("Open Batch"), () => {
			if (this.context) {
				frappe.set_route("Form", "Posting Batch", this.context.batch.name);
			}
		});
	}

	make_body() {
		this.$body = $('<div class="fast-entry"></div>').appendTo(this.page.main);
		this.$totals = $('<div class="fe-totals"></div>').appendTo(this.$body);
		this.$hint = $('<div class="fe-hint"></div>').appendTo(this.$body);
		this.$table = $('<div class="fe-table"></div>').appendTo(this.$body);

		this.$hint.html(
			[
				`<kbd>Enter</kbd> ${__("saves the line")}`,
				`<kbd>F2</kbd> ${__("copies the previous line")}`,
				`<kbd>Esc</kbd> ${__("clears the line")}`,
			].join(" &middot; ")
		);

		this.render_head();
		this.render_line();
		this.render_balances_row();
		this.$rows = $('<div class="fe-rows"></div>').appendTo(this.$table);
		this.set_enabled(false);
	}

	render_head() {
		const number = `<div class="fe-cell fe-head-cell fe-number">${__(
			"No.",
			null,
			"Entry number column"
		)}</div>`;
		const cells = FIELDS.map(
			(field) =>
				`<div class="fe-cell fe-head-cell" style="width:${
					field.width
				}px">${frappe.utils.escape_html(field.label)}</div>`
		).join("");

		$(
			`<div class="fe-row fe-head">${number}${cells}<div class="fe-cell fe-derived">${__(
				"Net / Tax"
			)}</div></div>`
		).appendTo(this.$table);
	}

	render_line() {
		this.$line = $('<div class="fe-row fe-line"></div>').appendTo(this.$table);
		// Held open but left empty: the line being typed has no number yet, and
		// guessing the next one would be a promise the server has not made.
		$('<div class="fe-cell fe-number"></div>').appendTo(this.$line);

		for (const field of FIELDS) {
			const $cell = $(`<div class="fe-cell" style="width:${field.width}px"></div>`).appendTo(
				this.$line
			);
			const $input = $(
				`<input type="text" class="fe-input" data-fieldname="${field.fieldname}"
					autocomplete="off" spellcheck="false" aria-label="${frappe.utils.escape_html(field.label)}">`
			).appendTo($cell);

			if (field.kind === "amount") {
				$input.addClass("fe-right");
			}

			this.inputs[field.fieldname] = $input;
			this.bind_input(field, $input);
		}

		this.$preview = $('<div class="fe-cell fe-derived fe-preview"></div>').appendTo(
			this.$line
		);
	}

	render_balances_row() {
		this.$balances = $('<div class="fe-balances"></div>').appendTo(this.$table);
	}

	set_enabled(enabled) {
		this.$line.toggleClass("fe-disabled", !enabled);
		Object.values(this.inputs).forEach(($input) => $input.prop("disabled", !enabled));
		if (enabled) {
			this.sync_party();
		}
	}

	// --- loading ---------------------------------------------------------

	restore_from_route() {
		const from_route = frappe.get_route()[1];
		if (from_route) {
			this.batch_field.set_value(from_route);
		}
	}

	async load(batch) {
		try {
			this.context = await frappe.xcall(
				"erpnext_germany.bookkeeping.fast_entry.get_context",
				{ batch }
			);
		} catch (error) {
			this.context = null;
			this.set_enabled(false);
			return;
		}

		this.index_lookups();
		this.render_rows();
		this.apply_totals(this.context.totals);
		this.set_enabled(true);
		this.reset_line(this.restore_draft());
	}

	index_lookups() {
		// Pre-lowercased once so that filtering on every keystroke stays a
		// plain string compare over an array.
		// The order comes from the server: accounts used a lot recently first,
		// because the account being looked for is usually one of a handful.
		this.account_index = this.context.accounts.map((account) => ({
			...account,
			display: account.number ? `${account.number} ${account.label}` : account.label,
			hint: account.last_used ? frappe.datetime.str_to_user(account.last_used) : "",
			haystack: `${account.number} ${account.label}`.toLowerCase(),
		}));

		this.cost_center_index = this.context.cost_centers.map((name) => ({
			name,
			display: name,
			haystack: name.toLowerCase(),
		}));

		this.tax_key_index = this.context.tax_keys.map((key) => ({
			name: key.name,
			display: `${key.key_number} ${key.name}`,
			haystack: `${key.key_number} ${key.name}`.toLowerCase(),
		}));

		this.party_index = (this.context.parties || []).map((party) => ({
			...party,
			display: party.label,
			haystack: `${party.name} ${party.label}`.toLowerCase(),
		}));

		this.open_item_index = (this.context.open_items || []).map((item) => ({
			...item,
			display: `${item.name}  ${format_number(item.outstanding_amount, null, 2)}`,
			// The due date is what tells two invoices of the same tenant apart.
			hint: item.due_date ? frappe.datetime.str_to_user(item.due_date) : "",
			haystack: item.name.toLowerCase(),
		}));
	}

	// --- the line --------------------------------------------------------

	bind_input(field, $input) {
		$input.on("keydown", (event) => this.on_keydown(field, $input, event));
		$input.on("input", () => {
			this.on_input(field, $input);
			this.save_draft();
		});
		$input.on("blur", () => this.close_suggestions());
	}

	on_input(field, $input) {
		if (field.kind === "account") {
			this.refresh_balances();
			this.sync_party();
		}

		if (field.kind === "party") {
			// Somebody else's invoice is never the one being settled.
			this.inputs.reference_name.val("");
		}

		if (field.kind === "direction") {
			// A single keystroke decides the side; typing "S" and waiting for
			// a dropdown would be slower than the paper journal it replaces.
			const value = normalise_direction($input.val());
			if (value) {
				$input.val(value === "Debit" ? debit_letter() : credit_letter());
				this.focus_next(field.fieldname);
			}
			return;
		}

		const index = this.index_for(field.kind);
		if (index) {
			this.open_suggestions($input, match(index, $input.val()));
		}
	}

	index_for(kind) {
		// The last two depend on what the rest of the line says, so they are
		// worked out per call rather than built once.
		return {
			account: this.account_index,
			cost_center: this.cost_center_index,
			tax_key: this.tax_key_index,
			party: this.parties_for_line(),
			open_item: this.open_items_for_line(),
		}[kind];
	}

	// --- the person on the line ------------------------------------------

	line_party_type() {
		// Which of the two accounts is a personal one decides whether this line
		// names a person at all, and which kind. Two personal accounts would be
		// two bookings; the server refuses that, so nothing is offered here.
		const types = ACCOUNT_FIELDS.map((fieldname) => {
			const name = resolve(this.account_index, this.inputs[fieldname].val() || "");
			const account = this.account_index.find((entry) => entry.name === name);
			return account ? account.party_type : null;
		}).filter(Boolean);

		return types.length === 1 ? types[0] : null;
	}

	parties_for_line() {
		const party_type = this.line_party_type();
		if (!party_type) {
			return [];
		}
		return this.party_index.filter((party) => party.party_type === party_type);
	}

	open_items_for_line() {
		const party = resolve(this.parties_for_line(), this.inputs.party.val() || "");
		if (!party) {
			return [];
		}
		return this.open_item_index.filter((item) => item.party === party);
	}

	sync_party() {
		// A line touching no personal account has nobody to book against, so
		// the two columns are shut rather than left to be filled in vain --
		// the entry mask has always skipped what it cannot ask for.
		const wanted = Boolean(this.line_party_type());
		for (const fieldname of PARTY_FIELDS) {
			const $input = this.inputs[fieldname];
			if (!wanted) {
				$input.val("");
			}
			$input.prop("disabled", !wanted);
			$input.closest(".fe-cell").toggleClass("fe-shut", !wanted);
		}
	}

	on_keydown(field, $input, event) {
		if (this.suggestions && ["ArrowDown", "ArrowUp"].includes(event.key)) {
			event.preventDefault();
			this.move_suggestion(event.key === "ArrowDown" ? 1 : -1);
			return;
		}

		if (event.key === "Enter" || event.key === "Tab") {
			// An open suggestion list swallows the first Enter: it means
			// "take this one", not "book the line".
			if (this.suggestions) {
				const taken = this.take_suggestion($input);
				if (taken && event.key === "Enter") {
					event.preventDefault();
					this.focus_next(field.fieldname);
					return;
				}
			}

			if (field.kind === "remark" && event.key === "Tab") {
				this.expand_shortcut($input);
			}

			if (event.key === "Enter") {
				event.preventDefault();
				this.submit();
			}
			return;
		}

		if (event.key === "Escape") {
			event.preventDefault();
			if (this.suggestions) {
				this.close_suggestions();
			} else {
				this.clear_line();
			}
		}
	}

	// --- balances --------------------------------------------------------

	async refresh_balances() {
		if (!this.context) {
			return;
		}

		const wanted = ACCOUNT_FIELDS.map((fieldname) =>
			this.read_field(FIELDS.find((field) => field.fieldname === fieldname))
		).filter(Boolean);

		// Marked as asked for before the call goes out, so two keystrokes in a
		// row cannot send the same question twice.
		const missing = wanted.filter((account) => this.balances[account] === undefined);
		missing.forEach((account) => {
			this.balances[account] = null;
		});

		this.render_balances(wanted);

		if (!missing.length) {
			return;
		}

		try {
			const found = await frappe.xcall(
				"erpnext_germany.bookkeeping.fast_entry.get_balances",
				{ batch: this.context.batch.name, accounts: missing }
			);
			Object.assign(this.balances, found);
		} catch (error) {
			// A balance is a convenience. Losing it must not cost the line
			// being typed, so the question is simply asked again next time.
			missing.forEach((account) => delete this.balances[account]);
		}

		this.render_balances(wanted);
	}

	render_balances(accounts) {
		if (!this.$balances) {
			return;
		}

		const shown = accounts.filter((account) => this.balances[account] != null);
		this.$balances.html(
			shown
				.map((account) => {
					const label = this.account_label(account);
					return `<span class="fe-balance"><label>${frappe.utils.escape_html(
						label
					)}</label>${balance_text(this.balances[account])}</span>`;
				})
				.join("")
		);
	}

	account_label(account) {
		const found = this.account_index.find((entry) => entry.name === account);
		return found ? found.display : account;
	}

	focus_next(fieldname) {
		const position = FIELDS.findIndex((field) => field.fieldname === fieldname);
		// A column that does not apply to this line is stepped over rather
		// than stopped at.
		const next = FIELDS.slice(position + 1).find(
			(field) => !this.inputs[field.fieldname].prop("disabled")
		);
		if (next) {
			this.inputs[next.fieldname].focus().select();
		}
	}

	read_line() {
		const values = {};
		for (const field of FIELDS) {
			values[field.fieldname] = this.read_field(field);
		}
		return values;
	}

	read_field(field) {
		const raw = (this.inputs[field.fieldname].val() || "").trim();
		if (!raw) {
			return "";
		}

		switch (field.kind) {
			case "amount":
				return parse_amount(raw);
			case "direction":
				return normalise_direction(raw) || "";
			case "date":
				return parse_date(raw, this.context.batch.from_date);
			default: {
				// Everything else is either picked from a list or plain text.
				const index = this.index_for(field.kind);
				return index ? resolve(index, raw) : raw;
			}
		}
	}

	write_line(values) {
		for (const field of FIELDS) {
			const value = values?.[field.fieldname];
			this.inputs[field.fieldname].val(display_value(field, value, this));
		}
	}

	reset_line(values) {
		this.write_line(values || {});
		this.$preview.text("");
		this.clear_draft();
		this.sync_party();
		// The accounts carry over, so their balances belong on screen before
		// the first keystroke of the next document rather than after it.
		this.refresh_balances();
		if (!this.$line.hasClass("fe-disabled")) {
			this.inputs[FIELDS[0].fieldname].focus().select();
		}
	}

	clear_line() {
		this.reset_line(this.carry_over(this.last_values || {}));
	}

	carry_over(values) {
		// What stays on screen after a booking is what stays the same across a
		// stack of documents: the date and the accounts, never the amount.
		return Object.fromEntries(CARRIED_OVER.map((field) => [field, values[field]]));
	}

	// --- saving ----------------------------------------------------------

	async submit() {
		if (!this.context) {
			return;
		}

		const values = this.read_line();
		const complaint = this.check(values);
		if (complaint) {
			frappe.show_alert({ message: complaint, indicator: "orange" });
			return;
		}

		this.last_values = values;
		const $row = this.add_pending_row(values);
		this.reset_line(this.carry_over(values));

		try {
			const result = await frappe.xcall("erpnext_germany.bookkeeping.fast_entry.add_entry", {
				batch: this.context.batch.name,
				row: values,
			});
			this.confirm_row($row, result.row);
			this.apply_totals(result.totals);
		} catch (error) {
			this.reject_row($row, values);
		}
	}

	check(values) {
		if (!values.amount) {
			return __("Enter an amount.");
		}
		if (!values.direction) {
			return __("Enter D for debit or C for credit.");
		}
		if (!values.account || !values.against_account) {
			return __("Enter an account and a contra account.");
		}
		if (values.account === values.against_account) {
			return __("Account and contra account must be different.");
		}
		if (!values.posting_date) {
			return __("Enter a posting date.");
		}
		if (this.line_party_type() && !values.party) {
			return __("A personal account needs a party.");
		}
		return null;
	}

	// --- the list of entered lines ---------------------------------------

	render_rows() {
		this.$rows.empty();
		// Newest first: the line just typed stays under the input line, which
		// is also the one most likely to need a correction or to be copied.
		for (const row of [...this.context.rows].reverse()) {
			this.$rows.append(this.row_html(row, "fe-done"));
		}
	}

	add_pending_row(values) {
		const $row = $(this.row_html(values, "fe-pending"));
		this.$rows.prepend($row);
		return $row;
	}

	confirm_row($row, row) {
		$row.replaceWith(this.row_html(row, "fe-done"));
	}

	reject_row($row, values) {
		// The values stay on screen and stay recoverable: a refused line is a
		// line that still has to be booked, not one that may quietly vanish.
		$row.replaceWith(this.row_html(values, "fe-failed"));
		this.$rows
			.find(".fe-failed")
			.first()
			.on("click", () => {
				this.write_line(values);
				this.inputs[FIELDS[0].fieldname].focus().select();
			});
	}

	row_html(row, state) {
		const number = `<div class="fe-cell fe-number">${
			row.idx ? frappe.utils.escape_html(String(row.idx)) : ""
		}</div>`;
		const cells = FIELDS.map((field) => {
			const value = display_value(field, row[field.fieldname], this);
			return `<div class="fe-cell${field.kind === "amount" ? " fe-right" : ""}"
				style="width:${field.width}px" title="${frappe.utils.escape_html(
				value
			)}">${frappe.utils.escape_html(value)}</div>`;
		}).join("");

		return `<div class="fe-row ${state}">${number}${cells}<div class="fe-cell fe-derived">${derived_text(
			row
		)}</div></div>`;
	}

	apply_totals(totals) {
		const format = (value) => format_currency(value, frappe.defaults.get_default("currency"));
		const parts = [
			`<span class="fe-total"><label>${__("Number of Entries")}</label>${
				totals.entry_count
			}</span>`,
			`<span class="fe-total"><label>${__("Total Amount")}</label>${format(
				totals.total_amount
			)}</span>`,
			`<span class="fe-total"><label>${__("Total Net Amount")}</label>${format(
				totals.total_net_amount
			)}</span>`,
			`<span class="fe-total"><label>${__("Total Tax Amount")}</label>${format(
				totals.total_tax_amount
			)}</span>`,
		];

		// The target and what is still missing from it, but only where somebody
		// wrote a target down. Shown last because it is what the eye goes back to
		// between two documents, and coloured because "is it nought yet" is the
		// only question being asked of it.
		if (totals.target_amount) {
			const reconciled = Math.abs(totals.difference) < 0.005;
			parts.push(
				`<span class="fe-total"><label>${__("Target Amount")}</label>${format(
					totals.target_amount
				)}</span>`,
				`<span class="fe-total fe-difference ${
					reconciled ? "fe-reconciled" : "fe-off"
				}"><label>${__("Difference")}</label>${format(totals.difference)}</span>`
			);
		}

		this.$totals.html(parts.join(""));
	}

	// --- suggestions -----------------------------------------------------

	open_suggestions($input, items) {
		this.close_suggestions();
		if (!items.length) {
			return;
		}

		const $list = $('<div class="fe-suggestions"></div>');
		items.forEach((item, position) => {
			// The date of last use is the quickest way to tell two similarly
			// named accounts apart without leaving the keyboard.
			const hint = item.hint
				? `<span class="fe-suggestion-hint">${frappe.utils.escape_html(item.hint)}</span>`
				: "";
			$(
				`<div class="fe-suggestion${
					position === 0 ? " fe-active" : ""
				}">${frappe.utils.escape_html(item.display)}${hint}</div>`
			)
				.data("item", item)
				// mousedown, not click: blur would close the list first.
				.on("mousedown", (event) => {
					event.preventDefault();
					$input.val(item.display);
					this.close_suggestions();
				})
				.appendTo($list);
		});

		$input.closest(".fe-cell").append($list);
		this.suggestions = { $list, $input };
	}

	move_suggestion(step) {
		const $items = this.suggestions.$list.find(".fe-suggestion");
		const current = $items.index($items.filter(".fe-active"));
		const next = Math.min(Math.max(current + step, 0), $items.length - 1);
		$items.removeClass("fe-active").eq(next).addClass("fe-active");
	}

	take_suggestion($input) {
		const item = this.suggestions.$list.find(".fe-active").data("item");
		this.close_suggestions();
		if (!item) {
			return false;
		}

		$input.val(item.display);
		return true;
	}

	close_suggestions() {
		if (this.suggestions) {
			this.suggestions.$list.remove();
			this.suggestions = null;
		}
	}

	expand_shortcut($input) {
		const text = ($input.val() || "").trim().toUpperCase();
		const expansion = this.context.text_shortcuts[text];
		if (expansion) {
			$input.val(expansion);
		}
	}

	// --- keyboard and draft ----------------------------------------------

	bind_shortcuts() {
		this.$body.on("keydown", (event) => {
			if (event.key === "F2") {
				event.preventDefault();
				if (this.last_values) {
					this.write_line(this.last_values);
					this.inputs[FIELDS[0].fieldname].focus().select();
				}
			}
		});
	}

	save_draft() {
		if (!this.context) {
			return;
		}

		// Written on every keystroke rather than on a timer: the point is to
		// survive the close that nobody planned.
		try {
			localStorage.setItem(
				`${DRAFT_KEY}:${this.context.batch.name}`,
				JSON.stringify(this.raw_line())
			);
		} catch (error) {
			// A full or blocked storage is not worth interrupting typing for.
		}
	}

	restore_draft() {
		try {
			const stored = localStorage.getItem(`${DRAFT_KEY}:${this.context.batch.name}`);
			return stored ? JSON.parse(stored) : null;
		} catch (error) {
			return null;
		}
	}

	clear_draft() {
		if (this.context) {
			try {
				localStorage.removeItem(`${DRAFT_KEY}:${this.context.batch.name}`);
			} catch (error) {
				// see save_draft
			}
		}
	}

	raw_line() {
		// The draft keeps what was typed, not what it resolves to, so a half
		// finished account number comes back exactly as it was left.
		return Object.fromEntries(
			FIELDS.map((field) => [field.fieldname, this.inputs[field.fieldname].val()])
		);
	}
};

// --- pure helpers --------------------------------------------------------

function debit_letter() {
	return __("D", null, "Debit shorthand");
}

function credit_letter() {
	return __("C", null, "Credit shorthand");
}

function normalise_direction(raw) {
	const value = (raw || "").trim().toUpperCase();
	// S/H for Soll and Haben, D/C for debit and credit, plus whatever the
	// translation made of them: a typist should not have to think about which
	// language the screen is in.
	if (["S", "D", debit_letter().toUpperCase()].includes(value)) {
		return "Debit";
	}
	if (["H", "C", credit_letter().toUpperCase()].includes(value)) {
		return "Credit";
	}
	return null;
}

function parse_amount(raw) {
	// German keyboards produce a comma; both separators mean the same thing
	// here and refusing one would only cost a correction.
	const cleaned = raw
		.replace(/\s/g, "")
		.replace(/\.(?=\d{3}\b)/g, "")
		.replace(",", ".");
	const value = parseFloat(cleaned);
	return isNaN(value) ? "" : value;
}

function parse_date(raw, fallback) {
	const digits = raw.replace(/\D/g, "");
	const year_of = (value) => (value.length === 2 ? `20${value}` : value);
	const iso = (year, month, day) => `${year}-${month.padStart(2, "0")}-${day.padStart(2, "0")}`;

	// A DATEV typist enters 1503 for the 15th of March; the year comes from
	// the batch, because a batch never spans two of them.
	if (digits.length === 4) {
		return iso(String(fallback).slice(0, 4), digits.slice(2, 4), digits.slice(0, 2));
	}
	if (digits.length === 6) {
		return iso(year_of(digits.slice(4, 6)), digits.slice(2, 4), digits.slice(0, 2));
	}
	if (digits.length === 8) {
		return iso(digits.slice(4, 8), digits.slice(2, 4), digits.slice(0, 2));
	}

	return "";
}

function match(index, query) {
	const needle = (query || "").trim().toLowerCase();
	if (!needle) {
		return [];
	}

	const starts = [];
	const contains = [];
	for (const item of index) {
		if (item.haystack.startsWith(needle)) {
			starts.push(item);
		} else if (item.haystack.includes(needle)) {
			contains.push(item);
		}
		if (starts.length >= MAX_SUGGESTIONS) {
			break;
		}
	}

	return [...starts, ...contains].slice(0, MAX_SUGGESTIONS);
}

function resolve(index, raw) {
	const needle = raw.trim().toLowerCase();
	const exact = index.find(
		(item) => item.name.toLowerCase() === needle || item.display.toLowerCase() === needle
	);
	if (exact) {
		return exact.name;
	}

	const matches = match(index, raw);
	// Only an unambiguous match is accepted. Guessing between two accounts is
	// how a wrong booking gets made without anyone noticing.
	return matches.length === 1 ? matches[0].name : "";
}

function display_value(field, value, screen) {
	if (value === undefined || value === null || value === "") {
		return "";
	}

	switch (field.kind) {
		case "direction":
			return value === "Debit"
				? debit_letter()
				: value === "Credit"
				? credit_letter()
				: String(value);
		case "amount":
			return typeof value === "number" ? format_number(value, null, 2) : String(value);
		case "date":
			return frappe.datetime.str_to_user(String(value)) || String(value);
		case "account":
			return display_of(screen?.account_index, value);
		case "cost_center":
			return display_of(screen?.cost_center_index, value);
		case "party":
			return display_of(screen?.party_index, value);
		case "open_item":
			return display_of(screen?.open_item_index, value);
		case "tax_key":
			return display_of(screen?.tax_key_index, value);
		default:
			return String(value);
	}
}

function display_of(index, value) {
	const item = index?.find((entry) => entry.name === value);
	return item ? item.display : String(value);
}

function balance_text(balance) {
	// Read the German way: a balance sits on one side, it is not a signed
	// number. 1.200 im Soll and -1.200 are the same thing, and only one of
	// them is what a bookkeeper says out loud.
	const side = balance < 0 ? credit_letter() : debit_letter();
	return `${format_number(Math.abs(balance), null, 2)}&nbsp;${frappe.utils.escape_html(side)}`;
}

function derived_text(row) {
	if (!row.tax_amount) {
		return "";
	}

	return frappe.utils.escape_html(
		`${format_number(row.net_amount, null, 2)} / ${format_number(row.tax_amount, null, 2)}`
	);
}
