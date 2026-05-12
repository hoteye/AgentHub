import { LitElement, css, html } from "lit";
import { customElement, property } from "lit/decorators.js";

export type WarpTabItem = {
  id: string;
  label: string;
  detail?: string;
};

@customElement("warp-tabs")
export class WarpTabs extends LitElement {
  static styles = css`
    :host {
      display: block;
    }

    .tabs {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    button {
      display: grid;
      gap: 2px;
      min-width: 0;
      border: 1px solid rgba(143, 163, 176, 0.16);
      border-radius: 8px;
      padding: 8px 10px;
      color: #c8d7e0;
      background: rgba(12, 20, 27, 0.88);
      font: inherit;
      text-align: left;
      cursor: pointer;
      transition:
        background 120ms ease,
        border-color 120ms ease,
        color 120ms ease,
        transform 120ms ease;
    }

    button:hover,
    button:focus-visible {
      outline: none;
      transform: translateY(-1px);
      border-color: rgba(164, 191, 203, 0.3);
      background: rgba(16, 26, 34, 0.98);
    }

    button[aria-selected="true"] {
      border-color: rgba(122, 191, 218, 0.34);
      background: linear-gradient(180deg, rgba(24, 47, 61, 0.94), rgba(14, 25, 33, 0.98));
      color: #f3fbff;
      box-shadow: inset 0 0 0 1px rgba(122, 191, 218, 0.08);
    }

    .label {
      min-width: 0;
      font-size: 13px;
      font-weight: 600;
      line-height: 1.3;
    }

    .detail {
      min-width: 0;
      color: inherit;
      font-size: 11px;
      line-height: 1.35;
      opacity: 0.72;
    }
  `;

  @property({ attribute: false }) items: WarpTabItem[] = [];
  @property() value = "";
  @property() ariaLabel = "Tabs";

  private select(id: string) {
    if (this.value === id) {
      return;
    }
    this.value = id;
    this.dispatchEvent(
      new CustomEvent("change", {
        detail: { value: id },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private handleKeydown = (event: KeyboardEvent, index: number) => {
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) {
      return;
    }
    event.preventDefault();
    if (!this.items.length) {
      return;
    }
    let nextIndex = index;
    if (event.key === "Home") {
      nextIndex = 0;
    } else if (event.key === "End") {
      nextIndex = this.items.length - 1;
    } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      nextIndex = (index - 1 + this.items.length) % this.items.length;
    } else {
      nextIndex = (index + 1) % this.items.length;
    }
    const nextItem = this.items[nextIndex];
    if (!nextItem) {
      return;
    }
    this.select(nextItem.id);
    const buttons = Array.from(this.renderRoot.querySelectorAll<HTMLButtonElement>("button"));
    buttons[nextIndex]?.focus();
  };

  render() {
    return html`
      <div class="tabs" role="tablist" aria-label=${this.ariaLabel}>
        ${this.items.map(
          (item, index) => html`
            <button
              type="button"
              role="tab"
              aria-selected=${item.id === this.value ? "true" : "false"}
              tabindex=${item.id === this.value ? "0" : "-1"}
              @click=${() => this.select(item.id)}
              @keydown=${(event: KeyboardEvent) => this.handleKeydown(event, index)}
            >
              <span class="label">${item.label}</span>
              ${item.detail ? html`<span class="detail">${item.detail}</span>` : null}
            </button>
          `,
        )}
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "warp-tabs": WarpTabs;
  }
}
