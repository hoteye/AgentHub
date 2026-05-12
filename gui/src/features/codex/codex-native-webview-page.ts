import { LitElement, css, html } from "lit";
import { customElement, property, state } from "lit/decorators.js";

type CodexBridgeMessageEvent = {
  source?: string;
  direction?: string;
  message?: unknown;
};

const CODEX_BRIDGE_EVENT_SOURCE = "agenthub-codex-bridge-shim";

@customElement("codex-native-webview-page")
export class CodexNativeWebviewPage extends LitElement {
  static styles = css`
    :host {
      display: block;
      width: 100%;
      height: 100vh;
      min-height: 100vh;
      background: #151515;
    }

    iframe {
      display: block;
      width: 100%;
      height: 100vh;
      border: 0;
      background: transparent;
    }
  `;

  @property({ type: String }) webviewSrc = "/__codex_webview/index.html";
  @state() private bridgeMessageCount = 0;

  connectedCallback(): void {
    super.connectedCallback();
    window.addEventListener("message", this.handleBridgeMessage);
  }

  disconnectedCallback(): void {
    window.removeEventListener("message", this.handleBridgeMessage);
    super.disconnectedCallback();
  }

  render() {
    return html`
      <iframe
        data-testid="codex-native-webview"
        data-bridge-message-count=${this.bridgeMessageCount}
        src=${this.webviewSrc}
        title="Codex native webview"
      ></iframe>
    `;
  }

  private readonly handleBridgeMessage = (event: MessageEvent<CodexBridgeMessageEvent>) => {
    if (event.data?.source !== CODEX_BRIDGE_EVENT_SOURCE) {
      return;
    }
    this.bridgeMessageCount += 1;
    this.dispatchEvent(
      new CustomEvent("codex-bridge-message", {
        detail: event.data,
        bubbles: true,
        composed: true,
      }),
    );
  };
}

declare global {
  interface HTMLElementTagNameMap {
    "codex-native-webview-page": CodexNativeWebviewPage;
  }
}
