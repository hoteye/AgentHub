import { LitElement, css, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import "./warp-tooltip.ts";

export type WarpButtonVariant = "primary" | "secondary" | "ghost" | "naked";
export type WarpButtonSize = "default" | "small" | "icon";

@customElement("warp-button")
export class WarpButton extends LitElement {
  static styles = css`
    :host {
      display: inline-block;
      position: relative;
      vertical-align: middle;
    }

    button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      box-sizing: border-box;
      min-width: 0;
      border: 1px solid transparent;
      border-radius: 8px;
      padding: 0 12px;
      color: #dbe8f0;
      background: rgba(17, 26, 34, 0.96);
      font: inherit;
      font-size: 13px;
      font-weight: 600;
      line-height: 1;
      cursor: pointer;
      transition:
        background 120ms ease,
        border-color 120ms ease,
        color 120ms ease,
        transform 120ms ease,
        box-shadow 120ms ease;
    }

    button:hover:not(:disabled),
    button:focus-visible:not(:disabled) {
      outline: none;
      transform: translateY(-1px);
    }

    button:focus-visible:not(:disabled) {
      box-shadow: 0 0 0 2px rgba(101, 180, 219, 0.18);
    }

    button.primary {
      border-color: rgba(120, 196, 224, 0.28);
      background: linear-gradient(135deg, rgba(22, 98, 131, 0.96), rgba(20, 66, 88, 0.96));
      color: #f4fbff;
    }

    button.primary:hover:not(:disabled),
    button.primary:focus-visible:not(:disabled) {
      background: linear-gradient(135deg, rgba(29, 116, 153, 0.98), rgba(24, 77, 103, 0.98));
    }

    button.secondary {
      border-color: rgba(143, 163, 176, 0.18);
      background: rgba(13, 22, 29, 0.96);
      color: #dbe8f0;
    }

    button.secondary:hover:not(:disabled),
    button.secondary:focus-visible:not(:disabled) {
      border-color: rgba(160, 189, 202, 0.34);
      background: rgba(18, 31, 41, 0.98);
    }

    button.ghost {
      border-color: rgba(143, 163, 176, 0.1);
      background: rgba(8, 14, 20, 0.82);
      color: #d0dbe3;
    }

    button.ghost:hover:not(:disabled),
    button.ghost:focus-visible:not(:disabled) {
      border-color: rgba(170, 191, 203, 0.24);
      background: rgba(12, 19, 27, 0.96);
    }

    button.naked {
      border-color: transparent;
      background: transparent;
      color: #d4e1ea;
      padding: 0 2px;
    }

    button.naked:hover:not(:disabled),
    button.naked:focus-visible:not(:disabled) {
      background: rgba(255, 255, 255, 0.06);
    }

    button.active {
      border-color: rgba(125, 187, 213, 0.42);
      box-shadow: inset 0 0 0 1px rgba(125, 187, 213, 0.08);
    }

    button:disabled {
      cursor: not-allowed;
      opacity: 0.48;
      transform: none;
    }

    button.small {
      min-height: 28px;
      padding: 0 10px;
      font-size: 12px;
    }

    button.default {
      min-height: 34px;
    }

    button.icon {
      min-width: 34px;
      min-height: 34px;
      padding: 0;
    }

    .icon {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 16px;
      color: inherit;
      font-size: 16px;
      line-height: 1;
    }

    .label {
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .shortcut {
      flex: none;
      padding: 2px 6px;
      border-radius: 6px;
      background: rgba(255, 255, 255, 0.06);
      color: #b8cad5;
      font-size: 11px;
      line-height: 1.35;
      white-space: nowrap;
    }

    .tooltip {
      position: absolute;
      left: 0;
      top: calc(100% + 6px);
      z-index: 20;
    }
  `;

  @property() label = "";
  @property() icon = "";
  @property() tooltip = "";
  @property() shortcut = "";
  @property() variant: WarpButtonVariant = "secondary";
  @property() size: WarpButtonSize = "default";
  @property({ type: Boolean, reflect: true }) active = false;
  @property({ type: Boolean, reflect: true }) disabled = false;
  @property({ type: Boolean, reflect: true }) busy = false;
  @property() type: "button" | "submit" | "reset" = "button";

  @state() private hovered = false;
  @state() private focused = false;

  private handleMouseEnter = () => {
    this.hovered = true;
  };

  private handleMouseLeave = () => {
    this.hovered = false;
  };

  private handleFocusIn = () => {
    this.focused = true;
  };

  private handleFocusOut = () => {
    this.focused = false;
  };

  render() {
    const label = this.label.trim();
    const tooltip = this.tooltip.trim() || label;
    const ariaLabel = label || tooltip || "action";
    const showTooltip = Boolean(tooltip) && (this.hovered || this.focused);
    const icon = this.busy ? "⋯" : this.icon.trim();
    return html`
      <button
        class=${`${this.variant} ${this.size} ${this.active ? "active" : ""}`}
        type=${this.type}
        ?disabled=${this.disabled}
        aria-pressed=${this.active ? "true" : "false"}
        aria-label=${ariaLabel}
        title=${tooltip}
        @mouseenter=${this.handleMouseEnter}
        @mouseleave=${this.handleMouseLeave}
        @focusin=${this.handleFocusIn}
        @focusout=${this.handleFocusOut}
      >
        ${icon ? html`<span class="icon" aria-hidden="true">${icon}</span>` : null}
        ${label ? html`<span class="label">${label}</span>` : nothing}
        ${this.shortcut.trim() ? html`<span class="shortcut" aria-hidden="true">${this.shortcut}</span>` : nothing}
      </button>
      ${showTooltip
        ? html`
            <div class="tooltip">
              <warp-tooltip .label=${tooltip} .shortcut=${this.shortcut}></warp-tooltip>
            </div>
          `
        : null}
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "warp-button": WarpButton;
  }
}
