import { createReadStream, existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { defineConfig, type Plugin } from "vite";

export default defineConfig({
  plugins: [codexNativeWebviewPlugin()],
  server: {
    port: 4173,
  },
});

const CODEX_WEBVIEW_ROUTE = "/__codex_webview/";
const DEFAULT_CODEX_WEBVIEW_DIR = "/mnt/c/Users/Administrator/codex-extracted/webview";
const AGENTHUB_CODEX_BRIDGE_SHIM = '<script src="/agenthub-codex-bridge-shim.js"></script>';
const AGENTHUB_CODEX_API_ROUTE = "/__agenthub_codex/";

export function resolveCodexNativeWebviewDir(env: Record<string, string | undefined> = process.env): string {
  return path.resolve(env.AGENTHUB_CODEX_WEBVIEW_DIR || DEFAULT_CODEX_WEBVIEW_DIR);
}

export function resolveAgentHubWorkspaceRoot(
  env: Record<string, string | undefined> = process.env,
  cwd = process.cwd(),
): string {
  if (env.AGENTHUB_WORKSPACE_ROOT) {
    return path.resolve(env.AGENTHUB_WORKSPACE_ROOT);
  }
  return path.basename(cwd) === "gui" ? path.resolve(cwd, "..") : path.resolve(cwd);
}

export function agentHubCodexWebviewConfigScript(
  env: Record<string, string | undefined> = process.env,
  cwd = process.cwd(),
): string {
  const config = {
    workspaceRoot: resolveAgentHubWorkspaceRoot(env, cwd),
    homeDir: os.homedir(),
    codexHome: path.join(os.homedir(), ".codex"),
  };
  return `<script>window.__AGENTHUB_CODEX_WEBVIEW_CONFIG__=${JSON.stringify(config)};</script>`;
}

export function injectAgentHubCodexBridgeShim(html: string, configScript = agentHubCodexWebviewConfigScript()): string {
  if (html.includes("__AGENTHUB_CODEX_WEBVIEW_CONFIG__") && html.includes(AGENTHUB_CODEX_BRIDGE_SHIM)) {
    return html;
  }
  const injected = `${configScript}\n    ${AGENTHUB_CODEX_BRIDGE_SHIM}`;
  const firstModuleScript = html.match(/<script\s+type="module"[^>]*><\/script>/);
  if (firstModuleScript?.index != null) {
    return `${html.slice(0, firstModuleScript.index)}${injected}\n    ${html.slice(firstModuleScript.index)}`;
  }
  return html.replace("</head>", `  ${injected}\n</head>`);
}

function codexNativeWebviewPlugin(): Plugin {
  return {
    name: "agenthub-codex-native-webview",
    configureServer(server) {
      server.middlewares.use((request, response, next) => {
        const requestPath = new URL(request.url || "/", "http://agenthub.local").pathname;
        if (requestPath === `${AGENTHUB_CODEX_API_ROUTE}workspace-directory-entries`) {
          handleWorkspaceDirectoryEntries(request, response);
          return;
        }

        if (requestPath !== "/__codex_webview" && !requestPath.startsWith(CODEX_WEBVIEW_ROUTE)) {
          next();
          return;
        }

        const webviewDir = resolveCodexNativeWebviewDir();
        if (!existsSync(webviewDir)) {
          response.statusCode = 404;
          response.setHeader("content-type", "text/plain; charset=utf-8");
          response.end(
            [
              "Codex native webview extract not found.",
              `Expected: ${webviewDir}`,
              "Set AGENTHUB_CODEX_WEBVIEW_DIR to the extracted Codex webview directory.",
            ].join("\n"),
          );
          return;
        }

        let relativePath = requestPath === "/__codex_webview"
          ? "index.html"
          : decodeURIComponent(requestPath.slice(CODEX_WEBVIEW_ROUTE.length)) || "index.html";
        if (relativePath.endsWith("/")) {
          relativePath = `${relativePath}index.html`;
        }

        const filePath = path.resolve(webviewDir, relativePath);
        if (!filePath.startsWith(`${webviewDir}${path.sep}`) && filePath !== webviewDir) {
          response.statusCode = 403;
          response.end("path escapes Codex webview root");
          return;
        }
        if (!existsSync(filePath) || !statSync(filePath).isFile()) {
          response.statusCode = 404;
          response.end("Codex webview asset not found");
          return;
        }

        response.setHeader("content-type", contentTypeFor(filePath));
        if (path.basename(filePath) === "index.html") {
          response.end(injectAgentHubCodexBridgeShim(readFileSync(filePath, "utf8")));
          return;
        }
        createReadStream(filePath).pipe(response);
      });
    },
  };
}

function handleWorkspaceDirectoryEntries(
  request: import("node:http").IncomingMessage,
  response: import("node:http").ServerResponse,
) {
  if (request.method !== "POST") {
    response.statusCode = 405;
    response.setHeader("content-type", "application/json; charset=utf-8");
    response.end(JSON.stringify({ error: "method_not_allowed" }));
    return;
  }

  let rawBody = "";
  request.setEncoding("utf8");
  request.on("data", (chunk) => {
    rawBody += chunk;
  });
  request.on("end", () => {
    try {
      const payload = rawBody.trim() ? JSON.parse(rawBody) : {};
      const allowedWorkspaceRoot = resolveAgentHubWorkspaceRoot();
      const requestedWorkspaceRoot = path.resolve(String(payload.workspaceRoot || allowedWorkspaceRoot));
      if (requestedWorkspaceRoot !== allowedWorkspaceRoot) {
        response.statusCode = 403;
        response.setHeader("content-type", "application/json; charset=utf-8");
        response.end(JSON.stringify({ error: "workspace_root_not_allowed" }));
        return;
      }
      const workspaceRoot = requestedWorkspaceRoot;
      const directoryPath = String(payload.directoryPath || "").replace(/\\/g, "/");
      const includeHidden = payload.includeHidden === true;
      const targetDirectory = path.resolve(workspaceRoot, directoryPath);
      if (targetDirectory !== workspaceRoot && !targetDirectory.startsWith(`${workspaceRoot}${path.sep}`)) {
        response.statusCode = 403;
        response.setHeader("content-type", "application/json; charset=utf-8");
        response.end(JSON.stringify({ error: "path_escapes_workspace_root" }));
        return;
      }
      if (!existsSync(targetDirectory) || !statSync(targetDirectory).isDirectory()) {
        response.statusCode = 404;
        response.setHeader("content-type", "application/json; charset=utf-8");
        response.end(JSON.stringify({ error: "directory_not_found" }));
        return;
      }

      const entries = readdirSync(targetDirectory, { withFileTypes: true })
        .filter((entry) => includeHidden || !entry.name.startsWith("."))
        .filter((entry) => entry.isDirectory() || entry.isFile())
        .map((entry) => {
          const relativePath = path
            .relative(workspaceRoot, path.join(targetDirectory, entry.name))
            .split(path.sep)
            .join("/");
          return {
            name: entry.name,
            type: entry.isDirectory() ? "directory" : "file",
            path: relativePath,
          };
        })
        .sort((left, right) => {
          if (left.type !== right.type) {
            return left.type === "directory" ? -1 : 1;
          }
          return left.path.localeCompare(right.path);
        });

      response.statusCode = 200;
      response.setHeader("content-type", "application/json; charset=utf-8");
      response.end(JSON.stringify({ entries }));
    } catch (error) {
      response.statusCode = 500;
      response.setHeader("content-type", "application/json; charset=utf-8");
      response.end(JSON.stringify({ error: error instanceof Error ? error.message : String(error) }));
    }
  });
}

function contentTypeFor(filePath: string): string {
  switch (path.extname(filePath).toLowerCase()) {
    case ".css":
      return "text/css; charset=utf-8";
    case ".html":
      return "text/html; charset=utf-8";
    case ".js":
      return "text/javascript; charset=utf-8";
    case ".json":
      return "application/json; charset=utf-8";
    case ".png":
      return "image/png";
    case ".svg":
      return "image/svg+xml";
    case ".wasm":
      return "application/wasm";
    case ".webp":
      return "image/webp";
    case ".woff":
      return "font/woff";
    case ".woff2":
      return "font/woff2";
    default:
      return "application/octet-stream";
  }
}
