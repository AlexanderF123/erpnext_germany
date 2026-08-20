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
const FIELDS = [
	{ fieldname: "amount", label: __("Amount"), kind: "amount", width: 120 },
	{
		fieldname: "direction",
		label: __("D/C", null, "Debit or credit column"),
		kind: "direction",
		width: 60,
	},
	{ fieldname: "tax_key", label: __("Tax Key"), kind: "tax_key", width: 110 },
	{ fieldname: "against_account", label: __("Contra Account"), kind: "account", width: 190 },
	{ fieldname: "document_number", label: __("Document Number"), kind: "text", width: 120 },
	{
		fieldname: "document_number_2",
		label: __("Second Document Number"),
		kind: "text",
		width: 120,
	},
	{ fieldname: "posting_date", label: __("Posting Date"), kind: "date", width: 110 },
	{ fieldname: "account", label: __("Account"), kind: "account", width: 190 },
	{ fieldname: "cost_center", label: __("Cost Center"), kind: "cost_center", width: 150 },
	{ fieldname: "remark", label: __("Remark"), kind: "remark", width: 200 },
];

const CARRIED_OVER = ["posting_date", "account", "against_account", "cost_center"];
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

		inject_styles();
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
		this.$rows = $('<div class="fe-rows"></div>').appendTo(this.$table);
		this.set_enabled(false);
	}

	render_head() {
		const cells = FIELDS.map(
			(field) =>
				`<div class="fe-cell fe-head-cell" style="width:${
					field.width
				}px">${frappe.utils.escape_html(field.label)}</div>`
		).join("");

		$(
			`<div class="fe-row fe-head">${cells}<div class="fe-cell fe-derived">${__(
				"Net / Tax"
			)}</div></div>`
		).appendTo(this.$table);
	}

	render_line() {
		this.$line = $('<div class="fe-row fe-line"></div>').appendTo(this.$table);

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

	set_enabled(enabled) {
		this.$line.toggleClass("fe-disabled", !enabled);
		Object.values(this.inputs).forEach(($input) => $input.prop("disabled", !enabled));
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

		this.index_accounts();
		this.render_rows();
		this.apply_totals(this.context.totals);
		this.set_enabled(true);
		this.reset_line(this.restore_draft());
	}

	index_accounts() {
		// Pre-lowercased once so that filtering on every keystroke stays a
		// plain string compare over an array.
		this.account_index = this.context.accounts.map((account) => ({
			...account,
			display: account.number ? `${account.number} ${account.label}` : account.label,
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
		return {
			account: this.account_index,
			cost_center: this.cost_center_index,
			tax_key: this.tax_key_index,
		}[kind];
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

	focus_next(fieldname) {
		const position = FIELDS.findIndex((field) => field.fieldname === fieldname);
		const next = FIELDS[position + 1];
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
			case "account":
				return resolve(this.account_index, raw);
			case "cost_center":
				return resolve(this.cost_center_index, raw);
			case "tax_key":
				return resolve(this.tax_key_index, raw);
			default:
				return raw;
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
		const cells = FIELDS.map((field) => {
			const value = display_value(field, row[field.fieldname], this);
			return `<div class="fe-cell${field.kind === "amount" ? " fe-right" : ""}"
				style="width:${field.width}px" title="${frappe.utils.escape_html(
				value
			)}">${frappe.utils.escape_html(value)}</div>`;
		}).join("");

		return `<div class="fe-row ${state}">${cells}<div class="fe-cell fe-derived">${derived_text(
			row
		)}</div></div>`;
	}

	apply_totals(totals) {
		const format = (value) => format_currency(value, frappe.defaults.get_default("currency"));
		this.$totals.html(
			[
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
			].join("")
		);
	}

	// --- suggestions -----------------------------------------------------

	open_suggestions($input, items) {
		this.close_suggestions();
		if (!items.length) {
			return;
		}

		const $list = $('<div class="fe-suggestions"></div>');
		items.forEach((item, position) => {
			$(
				`<div class="fe-suggestion${
					position === 0 ? " fe-active" : ""
				}">${frappe.utils.escape_html(item.display)}</div>`
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

function derived_text(row) {
	if (!row.tax_amount) {
		return "";
	}

	return frappe.utils.escape_html(
		`${format_number(row.net_amount, null, 2)} / ${format_number(row.tax_amount, null, 2)}`
	);
}

function inject_styles() {
	// Carried in the page instead of a stylesheet so that the screen works in
	// any install without an asset build step.
	if (document.getElementById("fast-entry-styles")) {
		return;
	}

	$(`<style id="fast-entry-styles">
		.fast-entry { font-variant-numeric: tabular-nums; }
		.fe-totals { display: flex; gap: 24px; padding: 8px 0 12px; flex-wrap: wrap; }
		.fe-total label { display: block; font-size: 11px; color: var(--text-muted); margin: 0; }
		.fe-total { font-size: 15px; font-weight: 600; }
		.fe-hint { font-size: 11px; color: var(--text-muted); padding-bottom: 8px; }
		.fe-hint kbd { font-size: 10px; }
		.fe-table { overflow-x: auto; border: 1px solid var(--border-color); border-radius: var(--border-radius); }
		.fe-row { display: flex; align-items: stretch; border-bottom: 1px solid var(--border-color); }
		.fe-row:last-child { border-bottom: none; }
		.fe-cell { padding: 4px 8px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; flex: none; }
		.fe-right { text-align: right; }
		.fe-head { background: var(--subtle-fg); font-weight: 600; position: sticky; top: 0; }
		.fe-head-cell { color: var(--text-muted); font-size: 11px; text-transform: uppercase; }
		.fe-line { background: var(--bg-color); }
		.fe-line .fe-cell { padding: 0; position: relative; }
		.fe-input { width: 100%; border: none; border-right: 1px solid var(--border-color); padding: 6px 8px; font-size: 13px; background: transparent; }
		.fe-input:focus { outline: 2px solid var(--primary); outline-offset: -2px; }
		.fe-input.fe-right { text-align: right; }
		.fe-disabled { opacity: 0.5; }
		.fe-derived { flex: 1 1 auto; min-width: 120px; color: var(--text-muted); text-align: right; }
		.fe-pending { opacity: 0.55; }
		.fe-failed { background: var(--red-50); color: var(--red-600); cursor: pointer; }
		.fe-suggestions { position: absolute; z-index: 10; top: 100%; left: 0; min-width: 100%; background: var(--fg-color); border: 1px solid var(--border-color); border-radius: var(--border-radius); box-shadow: var(--shadow-md); max-height: 240px; overflow-y: auto; }
		.fe-suggestion { padding: 4px 8px; font-size: 12px; white-space: nowrap; cursor: pointer; }
		.fe-suggestion.fe-active { background: var(--primary); color: white; }
	</style>`).appendTo(document.head);
}
