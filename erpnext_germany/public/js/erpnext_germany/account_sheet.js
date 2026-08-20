// Copyright (c) 2026, ALYF GmbH and contributors
// For license information, please see license.txt

// The way from a figure to the paper behind it.
//
// Every evaluation in this app links its accounts here, through one function
// rather than through a URL each report builds for itself. Two reports that
// build the same link separately drift apart, and a drill-down that lands on
// the wrong period is worse than none: it answers a question nobody asked.

frappe.provide("erpnext_germany.account_sheet");

const PANEL_ID = "erpnext-germany-document-panel";

Object.assign(erpnext_germany.account_sheet, {
	/** The Kontoblatt of one account, for exactly the period a figure covers. */
	url(params) {
		const query = Object.entries({
			company: params.company,
			account: params.account,
			from_date: params.from_date,
			to_date: params.to_date,
			cost_center: params.cost_center,
		})
			.filter(([, value]) => value)
			.map(([key, value]) => `${key}=${encodeURIComponent(value)}`)
			.join("&");

		return `/app/query-report/Kontoblatt?${query}`;
	},

	/** An account, as a link a report can put in a cell. */
	link(params, label) {
		const text = frappe.utils.escape_html(label || params.account);
		return `<a href="${this.url(params)}">${text}</a>`;
	},

	/** Show a filed document beside the sheet, without leaving it.
	 *
	 * A panel rather than a new tab: looking up what a booking was about is
	 * something a bookkeeper does dozens of times in a row, and every one of
	 * those that costs a window switch is one they stop doing.
	 */
	show_document(url, title) {
		this.close_document();

		const panel = document.createElement("div");
		panel.id = PANEL_ID;
		panel.innerHTML = `
			<div class="egd-head">
				<span class="egd-title"></span>
				<a class="egd-open" target="_blank" rel="noopener">${__("Open", null, "Document panel")}</a>
				<button class="egd-close" aria-label="${__("Close", null, "Document panel")}">&times;</button>
			</div>
			<div class="egd-body"></div>
		`;

		panel.querySelector(".egd-title").textContent = title || url;
		panel.querySelector(".egd-open").href = url;
		panel.querySelector(".egd-close").addEventListener("click", () => this.close_document());
		panel.querySelector(".egd-body").appendChild(this.viewer(url));

		document.body.appendChild(panel);
		document.addEventListener("keydown", this.on_escape);
	},

	close_document() {
		document.getElementById(PANEL_ID)?.remove();
		document.removeEventListener("keydown", erpnext_germany.account_sheet.on_escape);
	},

	on_escape(event) {
		if (event.key === "Escape") {
			erpnext_germany.account_sheet.close_document();
		}
	},

	/** An image is shown as one; everything else is left to the browser. */
	viewer(url) {
		const is_image = /\.(png|jpe?g|gif|webp|svg)$/i.test(url);
		const element = document.createElement(is_image ? "img" : "iframe");
		element.src = url;
		if (!is_image) {
			element.setAttribute("title", __("Document"));
		}

		return element;
	},
});

frappe.dom.set_style(
	`
	#${PANEL_ID} {
		position: fixed;
		top: 0;
		right: 0;
		bottom: 0;
		width: min(46vw, 720px);
		background: var(--fg-color, #fff);
		border-left: 1px solid var(--border-color, #d1d8dd);
		box-shadow: -2px 0 12px rgba(0, 0, 0, 0.08);
		display: flex;
		flex-direction: column;
		z-index: 1050;
	}
	#${PANEL_ID} .egd-head {
		display: flex;
		align-items: center;
		gap: 12px;
		padding: 10px 14px;
		border-bottom: 1px solid var(--border-color, #d1d8dd);
	}
	#${PANEL_ID} .egd-title {
		flex: 1;
		font-weight: 600;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	#${PANEL_ID} .egd-close {
		background: none;
		border: none;
		font-size: 22px;
		line-height: 1;
		cursor: pointer;
		color: var(--text-muted, #8d99a6);
	}
	#${PANEL_ID} .egd-body {
		flex: 1;
		overflow: auto;
		background: var(--control-bg, #f4f5f6);
	}
	#${PANEL_ID} .egd-body > * {
		width: 100%;
		height: 100%;
		border: 0;
		display: block;
	}
	#${PANEL_ID} .egd-body > img {
		height: auto;
		object-fit: contain;
	}
`,
	"erpnext-germany-document-panel",
);
