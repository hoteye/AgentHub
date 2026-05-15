# Changelog

All notable changes to AgentHub releases should be documented in this file.

The format is based on Keep a Changelog, with one release section per published release line.

## [Unreleased]

No unreleased changes yet.

## [0.1.13] - 2026-05-15

### Fixed

- Fixed the installed `agenthub` launcher so no-argument interactive startup works under `set -u` on macOS and Windows Bash environments.

## [0.1.12] - 2026-05-15

### Changed

- Updated the public installer `agenthub` launcher so interactive TUI startup prepares tmux split-preview support, while headless/help/provider-status commands still run the packaged binary directly.

## [0.1.11] - 2026-05-13

### Fixed

- Added `git` to the Linux clean-install smoke container dependencies so packaged CLI startup checks run in a fresh Ubuntu image.

## [0.1.10] - 2026-05-13

### Fixed

- Skipped the Linux installer smoke regression test on Windows runners so source CI no longer invokes bash installer coverage in a WSL-less environment.

## [0.1.9] - 2026-05-13

### Fixed

- Fixed the public install script cleanup trap so Docker clean-install smoke succeeds under `set -u` after a successful install.

## [0.1.8] - 2026-05-13

### Added

- Added a one-command GitHub CLI release driver for syncing the sanitized public tree, tagging releases, pushing to GitHub, and watching release Actions.
- Added a Docker-based Linux clean-install smoke script that validates the public install script, GitHub Release asset download path, basic no-key CLI startup, and uninstall cleanup.
- Added post-release clean-install smoke coverage to the executable release workflow.

### Changed

- Refreshed the public README and workspace illustration to match the current single-window startup layout, left-side tab rail, and on-demand tmux preview pane.

### Fixed

- Improved the TUI vertical tab rail startup and rendering path, including startup responsiveness, compact tab edge rendering, first-tab top border rendering, and tab-switch transcript color restoration.

## [0.1.7] - 2026-05-12

### Fixed

- Fixed macOS executable packaging by aligning the Codex sidecar runtime platform key with the prepared runtime catalog.

## [0.1.6] - 2026-05-12

### Fixed

- Fixed the executable release workflow so Codex sidecar runtime downloads use the GitHub Actions token and avoid unauthenticated API rate limits.
- Fixed Windows release CI portability by keeping the default shell on PowerShell, preserving simulated POSIX shell paths in tests, and falling back to `HOME` when a frozen runtime has no platform home profile.
- Fixed transcript markdown rendering so continuation lines are not indented under the assistant bullet.
- Fixed revived tmux preview panes so pane borders stay hidden after the preview pane is recreated.
- Improved split-pane Markdown preview by preferring terminal Markdown renderers before opening Markdown files in an editor.

## [0.1.5] - 2026-05-12

### Added

- Added public README coverage for visible multi-tab orchestration, Codex sidecar runtime behavior, and the split preview pane workflow.
- Added a README workspace illustration showing parent/child tabs, `TaskRun` summaries, Codex sidecar threads, and the right-side preview pane.
- Added a public binary install script that resolves the latest `cli-v*` GitHub Release, downloads the matching platform bundle, verifies the checksum when available, and installs an `agenthub` launcher.

### Changed

- README now links directly to GitHub Releases and documents one-command binary installation.
- Public export tooling now preserves the README workspace illustration and keeps the binary install script in the sanitized public tree.

### Fixed

- Left-side vertical tab rail now renders background busy, pending, unread, and dirty status markers.
- Tab restore now detects legacy Codex sidecar manifests whose kernel session id was saved as the thread id.

## [0.1.4] - 2026-05-12

### Added

- Release workflow now verifies the CLI test baseline before packaging release artifacts.
- Release workflow now creates a GitHub Release for `cli-v*` tags and uploads cross-platform archives plus `sha256` checksum files.
- Added a minimal GUI desktop release hardening mode that converts selected runtime Python trees to sourceless `.pyc` files for trial bundles.
- Added a release version/tag consistency check script and a release notes template for future releases.
- Added an `Apache-2.0` `LICENSE` file for public release packaging.
- Added a cross-platform release artifact smoke runner for packaged CLI bundles.
- Added internal governance policies for release support/rollback, security response, secrets handling, and docs/taskboard lifecycle management.
- Added a GUI desktop end-user install guide covering cross-platform bundle download, extraction, and launch.
- Added public source export/push support for syncing the sanitized `agenthubpublish` tree to GitHub.
- Added Codex sidecar runtime packaging support for release bundles, including prepared `codex-app-server`, `rg`, and `bwrap` resources.

### Changed

- Defined a repository-level breaking change rule: any incompatible behavior must be explicitly marked as `BREAKING` in changelog and release notes.
- Aligned GUI desktop release documentation to the repository-level support and rollback policy.
- GUI desktop bundles now emit platform-aware archive formats, platform-specific launchers, versioned artifact names, and a `release-manifest.json`.
- Current documentation now treats GUI bundles as closed-trial releases first, with open-source publication as a later product decision.
- Public release notes now identify the `Apache-2.0` AgentHub core license and state that commercial plugins such as `psbc_policy` are excluded from open-source release artifacts.
- Release executable builds now prepare and bundle Codex sidecar runtime in GitHub Actions before packaging.

### Fixed

- Portable release bundles now include CLI prompt assets and Reference parity prompt references required at runtime.
- Codex sidecar `/exit` and `/quit` commands are handled locally instead of being sent to the sidecar turn API.
- Transcript right-click copy/paste behavior was restored while keeping preview-pane click handling.

### Security

- Added internal incident severity/SLA response policy and standardized secret leak remediation requirements.

## [0.1.3] - 2026-04-28

### Fixed

- Fixed `/setup ... model <id>` so the optional model value is parsed and persisted instead of falling back to usage output.
- Provider config loading now merges user-private provider profiles before project-local selections, and provider auth now prefers user-private auth storage over project-local auth files.
- `/setup` and OAuth auth writes avoid project-local auth paths.
- Provider bootstrap no longer copies API key auth files into the project `.config` tree.

### Security

- Removed project-local provider auth state files from version control and ignored them for future commits.

## [0.1.1] - 2026-04-28

### Added

- Added a Codex-style `/status` runtime card with model, provider, directory, permissions, instruction docs, session, token usage, context window, and limits fields.

### Changed

- `/status` now shows the user-facing status card, while `/runtime_status` remains the key/value runtime policy diagnostic output.

## [0.1.0] - 2026-04-03

### Added

- Initial AgentHub CLI release packaging flow for Linux, macOS, and Windows portable bundles.
- Textual TUI, headless execution, provider/model switching, plugin discovery, and persistent thread storage.
- Gateway webhook ingress, gateway state persistence, and approval-oriented control-plane flows.
