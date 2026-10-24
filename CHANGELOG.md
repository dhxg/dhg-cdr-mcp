# Changelog

## 0.2.2 — Release hygiene and export timeout

### Fixed

- Ensured HTTP/HTTPS startup logs render URLs without literal braces.
- Applied a 300-second timeout to every direct export, preview, and batch-export COM call.
- Removed machine-specific `.mcp.json` and stale v0.1.0 context documents.
- Removed assistant/harness scaffolding from the distributable project tree.
- Added an explicit release builder with deny-list validation.
- Expanded Ruff F/B checks to the complete `server` and `tests` trees.
- Completed English tool-facing strings in `text.py` and `export.py`.

## 0.2.1 — Runtime hardening

### Fixed

- Fixed all seven single-file export closures that raised `UnboundLocalError`.
- Preview/export no longer changes selection, layer visibility, or printable state.
- Zero open documents is reported as a healthy connected state.
- Added lazy CorelDRAW attachment after server startup.
- Added external document fingerprints and active-page shape indexing.
- Disabled blind retries for mutations and added longer export timeouts.
- Added overwrite protection and optional `COREL_OUTPUT_ROOT` enforcement.
- Added FastMCP decorator-based tool registration, CI, and export/session regression tests.
- Split optional agent, data-merge, and HTTPS dependencies.

## 0.2.0 — Live Edit Core

### Added

- Compact live-edit MCP tool profile.
- Explicit document sessions and revision checks.
- Recursive document inspection with stable CorelDRAW shape IDs.
- Atomic `apply_operations` transaction engine.
- Separate attach, create, save, Save As, preview, export, undo, redo, and detach tools.
- Structured error metadata and platform-independent unit tests.
- Phased implementation and release-gate documentation.

### Fixed

- Double top-left/CorelDRAW Y conversion during reference reconstruction.
- Nested STA tool calls that could block for the COM timeout.
- Automatic launch of another CorelDRAW instance during live-edit attachment.
- Implicit Save As to `output/saved_document.cdr` in the new live API.
- Large default tool catalog used by the bundled agent.

### Compatibility

- Set `COREL_TOOL_PROFILE=legacy` to expose the 0.1.x tools during migration.
- The production default is `COREL_TOOL_PROFILE=compact`.
- The default attach policy is `COREL_ATTACH_POLICY=existing_only`.
