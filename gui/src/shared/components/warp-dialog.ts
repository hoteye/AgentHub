import { LitElement, css, html } from "lit";
import { customElement, property } from "lit/decorators.js";

import "./warp-button.ts";

@customElement("warp-dialog")
export class WarpDialog extends LitElement {
  static styles = css`
    :host {
      position: fixed;
      inset: 0;
      z-index: 80;
      display: block;
    }

    :host(:not([open])),
    :host([open="false"]) {
      display: none;
    }

    .backdrop {
      position: absolute;
      inset: 0;
      background: rgba(3, 7, 10, 0.72);
      backdrop-filter: blur(8px);
    }

    .panel {
      position: relative;
      display: grid;
      grid-template-rows: auto 1fr auto;
      width: min(720px, calc(100vw - 32px));
      max-height: min(84vh, 720px);
      margin: min(9vh, 96px) auto 0;
      border: 1px solid rgba(143, 163, 176, 0.18);
      border-radius: 8px;
      background: #0b1218;
      color: #eff6fb;
      box-shadow: 0 24px 80px rgba(0, 0, 0, 0.36);
      overflow: hidden;
    }

    header {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 16px;
      padding: 16px 18px 12px;
      border-bottom: 1px solid rgba(143, 163, 176, 0.12);
    }

    .title-block {
      display: grid;
      gap: 4px;
      min-width: 0;
    }

    .title {
      min-width: 0;
      color: #f6fbff;
      font-size: 16px;
      font-weight: 700;
      line-height: 1.35;
    }

    .subtitle {
      min-width: 0;
      color: #97aebc;
      font-size: 12px;
      line-height: 1.45;
    }

    .close {
      flex: none;
      width: 32px;
      height: 32px;
      border: 1px solid rgba(143, 163, 176, 0.16);
      border-radius: 8px;
      color: #d2e0e7;
      background: rgba(10, 17, 23, 0.96);
      font: inherit;
      cursor: pointer;
    }

    .close:hover,
    .close:focus-visible {
      outline: none;
      border-color: rgba(166, 191, 203, 0.28);
      background: rgba(15, 23, 30, 0.98);
    }

    .body {
      min-height: 0;
      overflow: auto;
      padding: 16px 18px;
    }

    footer {
      display: flex;
      justify-content: flex-end;
      gap: 10px;
      padding: 14px 18px 18px;
      border-top: 1px solid rgba(143, 163, 176, 0.12);
      background: rgba(8, 12, 16, 0.7);
    }
  `;

  @property({ type: Boolean, reflect: true }) open = false;
  @property() title = "";
  @property() subtitle = "";
  @property({ type: Boolean }) dismissible = true;

  connectedCallback(): void {
    super.connectedCallback();
    window.addEventListener("keydown", this.handleWindowKeydown);
  }

  disconnectedCallback(): void {
    window.removeEventListener("keydown", this.handleWindowKeydown);
    super.disconnectedCallback();
  }

  private handleWindowKeydown = (event: KeyboardEvent) => {
    if (!this.open || !this.dismissible || event.key !== "Escape") {
      return;
    }
    this.requestDismiss();
  };

  private requestDismiss() {
    if (!this.dismissible) {
      return;
    }
    this.dispatchEvent(
      new CustomEvent("dismiss", {
        bubbles: true,
        composed: true,
      }),
    );
    this.open = false;
  }

  private handleBackdropClick = () => {
    this.requestDismiss();
  };

  render() {
    if (!this.open) {
      return html``;
    }
    return html`
      <div class="backdrop" @click=${this.handleBackdropClick}></div>
      <section class="panel" role="dialog" aria-modal="true" aria-label=${this.title}>
        <header>
          <div class="title-block">
            <div class="title">${this.title}</div>
            ${this.subtitle ? html`<div class="subtitle">${this.subtitle}</div>` : null}
          </div>
          ${this.dismissible
            ? html`<button class="close" type="button" aria-label="Close dialog" @click=${this.requestDismiss}>×</button>`
            : null}
        </header>
        <div class="body">
          <slot></slot>
        </div>
        <footer>
          <slot name="footer"></slot>
        </footer>
      </section>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "warp-dialog": WarpDialog;
  }
}
