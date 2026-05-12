import { LitElement, css, html } from "lit";
import { customElement, property } from "lit/decorators.js";

export type StatusLevel = "ready" | "warning" | "error";
export type StatusItemSummary = {
  level: StatusLevel;
  detail: string;
};

export type StatusSummary = {
  model: StatusItemSummary;
  browser: StatusItemSummary;
  plugins: StatusItemSummary;
  connectors: StatusItemSummary;
  gateway?: {
    connected: boolean;
    detail: string;
  };
  approvals?: {
    pending: number;
    detail: string;
  };
};

export function statusSummaryFixture(): StatusSummary {
  return {
    model: { level: "ready", detail: "模型已就绪" },
    browser: { level: "warning", detail: "浏览器未启动" },
    plugins: { level: "ready", detail: "插件已加载" },
    connectors: { level: "warning", detail: "连接器待同步" },
    gateway: { connected: false, detail: "Control UI bootstrap 未接入" },
    approvals: { pending: 0, detail: "暂无待审批项" },
  };
}

@customElement("global-status-bar")
export class GlobalStatusBar extends LitElement {
  static styles = css`
    :host {
      display: block;
    }

    .bar {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
    }

    .meta {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 10px;
      margin-bottom: 10px;
      color: #8ea3af;
      font-size: 12px;
      letter-spacing: 0.04em;
    }

    .meta-pill {
      padding: 4px 10px;
      border-radius: 999px;
      border: 1px solid rgba(150, 186, 196, 0.18);
      background: rgba(9, 22, 30, 0.88);
    }

    .meta-pill.ready {
      border-color: rgba(76, 175, 139, 0.36);
      color: #8ae0ba;
    }

    .meta-pill.warning {
      border-color: rgba(234, 183, 94, 0.36);
      color: #ffd486;
    }

    .item {
      border-radius: 16px;
      border: 1px solid rgba(150, 186, 196, 0.14);
      background: rgba(9, 22, 30, 0.88);
      padding: 12px 14px;
      display: grid;
      gap: 12px;
      font-size: 13px;
    }

    .row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }

    .label {
      color: #93a9b6;
    }

    .detail {
      color: #8097a3;
      font-size: 12px;
      line-height: 1.45;
    }

    .pill {
      padding: 3px 9px;
      border-radius: 999px;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }

    .ready {
      background: rgba(76, 175, 139, 0.16);
      color: #8ae0ba;
    }

    .warning {
      background: rgba(234, 183, 94, 0.14);
      color: #ffd486;
    }

    .error {
      background: rgba(218, 97, 97, 0.14);
      color: #ff9d9d;
    }

    @media (max-width: 960px) {
      .bar {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
    }
  `;

  @property({ attribute: false }) summary: StatusSummary = statusSummaryFixture();

  render() {
    return html`
      <div class="meta">
        <span class="meta-pill ${this.summary.gateway?.connected ? "ready" : "warning"}">
          Gateway · ${this.summary.gateway?.connected ? "connected" : "degraded"}
        </span>
        <span class="meta-pill ${this.summary.approvals?.pending ? "warning" : "ready"}">
          Pending approvals · ${this.summary.approvals?.pending ?? 0}
        </span>
        ${this.summary.gateway?.detail ? html`<span>${this.summary.gateway?.detail}</span>` : ""}
      </div>
      <div class="bar">
        ${this.renderItem("模型", this.summary.model)}
        ${this.renderItem("浏览器", this.summary.browser)}
        ${this.renderItem("插件", this.summary.plugins)}
        ${this.renderItem("连接器", this.summary.connectors)}
      </div>
    `;
  }

  private renderItem(label: string, summary: StatusItemSummary) {
    return html`
      <section class="item">
        <div class="row">
          <span class="label">${label}</span>
          <span class="pill ${summary.level}">${summary.level}</span>
        </div>
        <span class="detail">${summary.detail}</span>
      </section>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "global-status-bar": GlobalStatusBar;
  }
}
