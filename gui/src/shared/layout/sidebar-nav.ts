import { LitElement, css, html } from "lit";
import { customElement, property } from "lit/decorators.js";

import {
  GUI_ROUTE_GROUPS,
  routesForGroup,
  type GuiRouteId,
} from "../../routes.ts";

@customElement("sidebar-nav")
export class SidebarNav extends LitElement {
  static styles = css`
    :host {
      display: block;
      padding: 20px 16px;
      background: linear-gradient(180deg, rgba(6, 18, 26, 0.98), rgba(8, 14, 19, 0.96));
      border-right: 1px solid rgba(150, 186, 196, 0.12);
    }

    nav {
      display: grid;
      gap: 14px;
      position: sticky;
      top: 20px;
    }

    .brand {
      display: grid;
      gap: 6px;
      padding: 14px 14px 18px;
    }

    .brand strong {
      font-size: 22px;
      color: #f0f6fa;
    }

    .brand span {
      font-size: 13px;
      color: #8ca4b0;
      line-height: 1.5;
    }

    .group {
      display: grid;
      gap: 8px;
    }

    .group-header {
      display: grid;
      gap: 2px;
      padding: 2px 12px;
    }

    .group-title {
      font-size: 12px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: #89a2b0;
    }

    .group-description {
      font-size: 12px;
      color: #6f8794;
    }

    .group-empty {
      font-size: 12px;
      color: #7b8f9a;
      border-radius: 12px;
      border: 1px dashed rgba(150, 186, 196, 0.18);
      padding: 10px 12px;
      background: rgba(12, 26, 34, 0.4);
    }

    button {
      display: flex;
      align-items: center;
      justify-content: space-between;
      width: 100%;
      border: 0;
      border-radius: 16px;
      padding: 12px 14px;
      text-align: left;
      color: #9db2bd;
      background: rgba(12, 26, 34, 0.52);
      cursor: pointer;
      transition: background 120ms ease, color 120ms ease, transform 120ms ease;
    }

    button:hover {
      background: rgba(18, 39, 50, 0.82);
      color: #eef6fa;
      transform: translateX(1px);
    }

    button[aria-current="page"] {
      background: linear-gradient(135deg, rgba(29, 75, 79, 0.86), rgba(23, 59, 73, 0.88));
      color: #ffffff;
      box-shadow: inset 0 0 0 1px rgba(174, 231, 219, 0.22);
    }

    .badge {
      min-width: 22px;
      padding: 2px 8px;
      border-radius: 999px;
      text-align: center;
      font-size: 12px;
      background: rgba(246, 188, 96, 0.14);
      color: #ffd486;
    }
  `;

  @property({ type: String }) currentRoute: GuiRouteId = "workbench";
  @property({ type: Number }) pendingApprovals = 0;

  render() {
    return html`
      <nav>
        <section class="brand">
          <strong>EasyClaw</strong>
          <span>AgentHub 的桌面控制台骨架，当前阶段先冻结导航、状态和页面入口。</span>
        </section>
        ${GUI_ROUTE_GROUPS.map((group) => {
          const routes = routesForGroup(group.id);
          return html`
            <section class="group" data-group=${group.id}>
              <header class="group-header">
                <span class="group-title">${group.label}</span>
                <span class="group-description">${group.description}</span>
              </header>
              ${routes.length
                ? routes.map((route) => {
                    const isCurrent = route.id === this.currentRoute;
                    const badge =
                      route.id === "approvals" && this.pendingApprovals > 0
                        ? this.pendingApprovals
                        : null;
                    return html`
                      <button
                        type="button"
                        aria-current=${isCurrent ? "page" : "false"}
                        data-route=${route.id}
                        @click=${() => this.emitRouteChange(route.id)}
                      >
                        <span>${route.label}</span>
                        ${badge ? html`<span class="badge">${badge}</span>` : ""}
                      </button>
                    `;
                  })
                : html`<div class="group-empty">该分组入口将在后续波次补齐。</div>`}
            </section>
          `;
        })}
      </nav>
    `;
  }

  private emitRouteChange(route: GuiRouteId) {
    this.dispatchEvent(
      new CustomEvent<GuiRouteId>("route-change", {
        detail: route,
        bubbles: true,
        composed: true,
      }),
    );
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "sidebar-nav": SidebarNav;
  }
}
