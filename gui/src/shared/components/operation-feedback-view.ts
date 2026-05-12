import { LitElement, css, html } from "lit";
import { customElement, property } from "lit/decorators.js";

import { neutralFeedback, type OperationFeedback } from "../state/operation-feedback.ts";

export type OperationFeedbackViewVariant = "inline" | "stack";

@customElement("operation-feedback-view")
export class OperationFeedbackView extends LitElement {
  static styles = css`
    :host {
      display: block;
    }

    .wrapper {
      gap: 10px;
    }

    .wrapper.inline {
      display: inline-flex;
      align-items: center;
      flex-wrap: wrap;
    }

    .wrapper.stack {
      display: grid;
      gap: 8px;
    }

    .wrapper.surface {
      padding: 10px 12px;
      border-radius: 12px;
      border: 1px solid transparent;
    }

    .wrapper.surface.neutral {
      background: rgba(35, 56, 70, 0.64);
      border-color: rgba(120, 154, 167, 0.16);
      color: #d6e6ed;
    }

    .wrapper.surface.success {
      background: rgba(26, 86, 72, 0.3);
      border-color: rgba(84, 181, 156, 0.26);
      color: #c9f1e3;
    }

    .wrapper.surface.warning {
      background: rgba(103, 77, 24, 0.28);
      border-color: rgba(214, 170, 63, 0.24);
      color: #f4ddb0;
    }

    .wrapper.surface.error {
      background: rgba(104, 38, 44, 0.28);
      border-color: rgba(224, 109, 120, 0.22);
      color: #ffd3d8;
    }

    .row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      flex-wrap: wrap;
    }

    .row.inline {
      justify-content: flex-start;
    }

    .title {
      color: #eef6fa;
      font-size: 13px;
      font-weight: 600;
      line-height: 1.4;
    }

    .message {
      color: #a6bcc7;
      font-size: 13px;
      line-height: 1.5;
    }

    .wrapper.surface .message {
      color: inherit;
    }

    .pill {
      border-radius: 999px;
      padding: 3px 8px;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      white-space: nowrap;
    }

    .pill.neutral {
      background: rgba(124, 152, 167, 0.14);
      color: #b6cad5;
    }

    .pill.success {
      background: rgba(76, 175, 139, 0.16);
      color: #8ae0ba;
    }

    .pill.warning {
      background: rgba(234, 183, 94, 0.14);
      color: #ffd486;
    }

    .pill.error {
      background: rgba(218, 97, 97, 0.14);
      color: #ff9d9d;
    }
  `;

  @property({ attribute: false }) feedback: OperationFeedback = neutralFeedback("");
  @property() title = "";
  @property({ reflect: true }) variant: OperationFeedbackViewVariant = "inline";
  @property({ type: Boolean, reflect: true }) surface = false;

  render() {
    const level = this.feedback.level;
    const title = this.title.trim();
    return html`
      <section class=${`wrapper ${this.variant} ${level} ${this.surface ? "surface" : ""}`}>
        ${title
          ? html`
              <div class="row">
                <span class="title">${title}</span>
                <span class=${`pill ${level}`}>${level}</span>
              </div>
              <div class="message">${this.feedback.message}</div>
            `
          : html`
              <div class=${`row ${this.variant === "inline" ? "inline" : ""}`}>
                <span class=${`pill ${level}`}>${level}</span>
                <span class="message">${this.feedback.message}</span>
              </div>
            `}
      </section>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "operation-feedback-view": OperationFeedbackView;
  }
}
