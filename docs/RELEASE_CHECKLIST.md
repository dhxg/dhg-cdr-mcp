# Release checklist

## Automated

- [ ] Build with `python scripts/build_release.py` (never ZIP the working directory directly)
- [ ] `python -m compileall -q server tests`
- [ ] `python -m unittest discover -s tests -v` (export, path safety, retry, session, coordinate, and operation regressions)
- [ ] Ruff F/B checks pass in CI and the Windows development environment
- [ ] Release archive contains no `.env`, API keys, logs, CDR customer files, or `__pycache__`

## Windows/CorelDRAW matrix

Run against every claimed CorelDRAW version:

- [ ] Server attaches with `COREL_ATTACH_POLICY=existing_only`
- [ ] It does not launch a second CorelDRAW instance
- [ ] Active-document session attaches to the expected file
- [ ] Switching tabs during a transaction does not redirect the edit
- [ ] Portrait top-left coordinate golden test passes
- [ ] Landscape top-left coordinate golden test passes
- [ ] A mixed operation batch appears live in the open document
- [ ] One Undo reverses the entire batch
- [ ] A deliberately failing operation rolls the batch back
- [ ] Stale `expected_revision` is rejected
- [ ] `save_current_document` does not Save As
- [ ] Unsaved documents return `DOCUMENT_HAS_NO_PATH`
- [ ] Preview/export leaves the CDR path unchanged
- [ ] Grouped text and available PowerClip content are indexed

## MCP clients

- [ ] Claude Desktop
- [ ] Claude Code
- [ ] Gemini CLI
- [ ] Cursor
- [ ] VS Code/Copilot

For each client, verify tool discovery, attachment, inspection, atomic editing, preview, save confirmation, and error reporting.

## Security

- [ ] Destructive operations require explicit user intent
- [ ] Remote transport is loopback-only unless authenticated
- [ ] No direct public exposure of the local COM bridge
- [ ] Dependency vulnerability scan reviewed
- [ ] Changelog and migration notes updated
