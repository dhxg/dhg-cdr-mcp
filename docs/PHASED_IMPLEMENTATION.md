# CorelDRAW MCP — Phased Implementation Plan

## Current release: 0.2.2 Live Edit Core

This release changes the project from a collection of independent active-document COM calls into a session-based live-edit engine.

## Supported client scope

The MCP is intended only for local desktop applications and local CLI agents that support custom/user-configured MCP servers. Examples include Claude Desktop and compatible CLI environments such as Antigravity. A ChatGPT desktop application is compatible only when its installed version exposes custom local MCP configuration. Browser-only AI websites are not supported because they cannot start or directly connect to the local Windows stdio MCP process.

## Phase 0 — Stabilization (implemented)

- Safe `existing_only` attach policy by default.
- Re-entrant STA execution prevents nested-tool deadlocks.
- Canonical `page_top_left` millimetre coordinate contract.
- Fixed double Y-coordinate conversion in image reconstruction.
- Structured error fields: `code`, `retryable`, `warnings`, `details`.
- Compact tool profile is the default; legacy tools require `COREL_TOOL_PROFILE=legacy`.
- Runtime files, secrets, logs, caches, and generated designs are excluded from releases.

## Phase 1 — Live editing (implemented)

- Explicit document sessions bind operations to a verified open document.
- `attach_active_document` never opens or creates a document.
- `create_new_document` is separate and explicit.
- Revisions detect stale model decisions.
- `apply_operations` batches related edits into one CorelDRAW command group.
- Failed batches attempt rollback with CorelDRAW Undo.
- UI redraw is suppressed only during the transaction and refreshed afterward.
- `save_current_document` never invents a filename or performs Save As.
- `save_document_as` requires an explicit absolute `.cdr` path.
- Recursive indexing covers groups and available PowerClip contents.

## Phase 2 — Cross-client MCP (implemented foundation)

The default server exposes a compact tool catalog suitable for Claude Desktop, Claude Code, Gemini CLI, Cursor, and VS Code. The bundled agent uses the same catalog and workflow prompt.

Remaining client certification work requires Windows runs against each host and each supported CorelDRAW version.

## Phase 3 — Reference reconstruction (foundation only)

The renderer now uses the same top-left coordinate contract, but accurate raster-to-editable reconstruction still requires:

1. source classification (CDR/PDF/SVG/raster),
2. OCR and layout detection,
3. font and asset matching,
4. a normalized design manifest,
5. vector reconstruction,
6. render-and-compare iterations,
7. confidence reporting and human confirmation.

Do not market raster reconstruction as a guaranteed pixel-perfect clone. Flattened images do not contain original fonts, hidden layers, vector nodes, or source assets.

## Phase 4 — Distribution (planned)

- Signed Windows installer and tray companion.
- Health/diagnostics UI.
- One-click MCP bundle for Claude Desktop.
- Config generators for Gemini CLI, Cursor, and VS Code.
- Automatic crash bundle with secrets removed.

## Phase 5 — Remote/ChatGPT bridge (planned)

ChatGPT web requires a remote streaming HTTP/SSE MCP endpoint. The safe architecture is a cloud relay paired with the local Windows companion. Never expose the local COM service directly to the internet.

Required controls: OAuth/device pairing, per-device authorization, encrypted transport, approval for destructive actions, audit logs, and rate limits.

## Release gates

A phase is considered complete only when:

- unit tests pass,
- Python compilation and linting pass,
- a real Windows/CorelDRAW smoke test passes,
- live edits affect the originally attached document,
- one undo restores the pre-transaction state,
- no edit operation silently creates or saves another document,
- orientation golden tests pass for portrait and landscape pages.
