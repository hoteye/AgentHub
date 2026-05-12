import { LitElement, css, html } from "lit";
import { customElement, property } from "lit/decorators.js";

@customElement("warp-tooltip")
export class WarpTooltip extends LitElement {
  static styles = css`
    :host {
      display: block;
      pointer-events: none;
    }

    .tooltip {
      display: inline-flex;
      align-items: center;
      gap: 10px;
      min-height: 30px;
      max-width: 320px;
      padding: 6px 10px;
      border: 1px solid rgba(142, 165, 181, 0.18);
      border-radius: 8px;
      background: rgba(8, 15, 21, 0.96);
      color: #edf5fb;
      box-shadow: 0 16px 36px rgba(0, 0, 0, 0.28);
      backdrop-filter: blur(12px);
    }

    .label {
      min-width: 0;
      overflow: hidden;
      color: inherit;
      font-size: 12px;
      line-height: 1.35;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .shortcut {
      flex: none;
      border-radius: 6px;
      padding: 2px 7px;
      background: rgba(255, 255, 255, 0.06);
      color: #b8cad5;
      font-size: 11px;
      line-height: 1.4;
      white-space: nowrap;
    }
  `;

  @property() label = "";
  @property() shortcut = "";

  render() {
    const label = this.label.trim();
    if (!label) {
      return html``;
    }
    return html`
      <div class="tooltip" role="tooltip">
        <span class="label">${label}</span>
        ${this.shortcut.trim() ? html`<span class="shortcut">${this.shortcut}</span>` : null}
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "warp-tooltip": WarpTooltip;
  }
}
