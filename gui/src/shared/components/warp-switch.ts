import { LitElement, css, html } from "lit";
import { customElement, property } from "lit/decorators.js";

@customElement("warp-switch")
export class WarpSwitch extends LitElement {
  static styles = css`
    :host {
      display: block;
    }

    button {
      display: grid;
      grid-template-columns: auto minmax(0, 1fr);
      align-items: center;
      gap: 12px;
      width: 100%;
      border: 1px solid rgba(143, 163, 176, 0.16);
      border-radius: 8px;
      padding: 10px 12px;
      color: #d8e5ed;
      background: rgba(12, 20, 27, 0.94);
      font: inherit;
      text-align: left;
      cursor: pointer;
      transition:
        background 120ms ease,
        border-color 120ms ease,
        transform 120ms ease;
    }

    button:hover:not(:disabled),
    button:focus-visible:not(:disabled) {
      outline: none;
      transform: translateY(-1px);
      border-color: rgba(160, 189, 202, 0.3);
      background: rgba(16, 26, 34, 0.98);
    }

    button:disabled {
      cursor: not-allowed;
      opacity: 0.48;
      transform: none;
    }

    .track {
      position: relative;
      width: 42px;
      height: 24px;
      border-radius: 999px;
      background: rgba(97, 120, 134, 0.3);
      box-shadow: inset 0 0 0 1px rgba(150, 186, 196, 0.12);
      transition: background 120ms ease, box-shadow 120ms ease;
    }

    .thumb {
      position: absolute;
      top: 3px;
      left: 3px;
      width: 18px;
      height: 18px;
      border-radius: 999px;
      background: #f4fbff;
      box-shadow: 0 4px 10px rgba(0, 0, 0, 0.22);
      transition: transform 120ms ease;
    }

    :host([checked]) .track {
      background: linear-gradient(135deg, rgba(28, 115, 154, 0.92), rgba(26, 88, 118, 0.96));
      box-shadow: inset 0 0 0 1px rgba(123, 193, 219, 0.22);
    }

    :host([checked]) .thumb {
      transform: translateX(18px);
    }

    .content {
      display: grid;
      gap: 2px;
      min-width: 0;
    }

    .label {
      min-width: 0;
      color: #edf4f8;
      font-size: 13px;
      font-weight: 600;
      line-height: 1.35;
    }

    .description {
      min-width: 0;
      color: #9cb0bc;
      font-size: 12px;
      line-height: 1.4;
    }
  `;

  @property({ type: Boolean, reflect: true }) checked = false;
  @property({ type: Boolean, reflect: true }) disabled = false;
  @property() label = "";
  @property() description = "";

  private toggle() {
    if (this.disabled) {
      return;
    }
    this.checked = !this.checked;
    this.dispatchEvent(
      new CustomEvent("change", {
        detail: { checked: this.checked },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private handleKeydown(event: KeyboardEvent) {
    if (event.key !== " " && event.key !== "Enter") {
      return;
    }
    event.preventDefault();
    this.toggle();
  }

  render() {
    return html`
      <button
        type="button"
        role="switch"
        aria-checked=${this.checked ? "true" : "false"}
        ?disabled=${this.disabled}
        @click=${this.toggle}
        @keydown=${this.handleKeydown}
      >
        <span class="track" aria-hidden="true"><span class="thumb"></span></span>
        <span class="content">
          <span class="label">${this.label}</span>
          ${this.description ? html`<span class="description">${this.description}</span>` : null}
        </span>
      </button>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "warp-switch": WarpSwitch;
  }
}
