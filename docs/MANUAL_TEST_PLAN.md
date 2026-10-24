# Manual Windows/CorelDRAW Test Plan

Run this plan on a **copy of a non-production CDR file**. Record the CorelDRAW version, Windows version, Python version, MCP client, and test result.

## 1. Startup and recovery

1. Start the MCP server while CorelDRAW is closed.
2. Call `corel_status`; it should report not connected without crashing.
3. Start CorelDRAW with no document open.
4. Call `corel_status` again; it should report connected with zero documents.
5. Open a CDR file and call `list_open_documents`; the file should appear without restarting MCP.

## 2. Exact document attachment

1. Open two differently named CDR files.
2. Attach each one by its returned document identifier.
3. Confirm the selected file becomes active and no second CorelDRAW instance is launched.
4. Confirm `detach_document` leaves CorelDRAW and the CDR file open.

## 3. Coordinates and atomic editing

1. Attach a disposable document and run `inspect_document`.
2. Move a known shape to a top-left coordinate such as `x=20`, `y=15`.
3. Confirm the object is right-side-up and exactly 20 mm from the left and 15 mm from the top.
4. Apply a transaction containing text and geometry changes.
5. Press CorelDRAW Undo once; the complete transaction should be undone in one step.
6. Trigger one intentionally invalid operation in a multi-operation transaction; no partial edits should remain.

## 4. External-edit conflict detection

1. Run `inspect_document` and keep its revision.
2. Manually move or resize the target object in CorelDRAW.
3. Submit `apply_operations` with the old revision.
4. Expect `REVISION_CONFLICT`; the MCP operation must not apply.
5. Inspect again, then retry with the new revision.

## 5. Preview state preservation

1. Hide one layer and mark another layer non-printable.
2. Select one object.
3. Run `render_preview`.
4. Confirm layer visibility, printable flags, and selection are unchanged.
5. Confirm the preview file exists and is non-empty.

## 6. Filesystem safety

1. Set `COREL_OUTPUT_ROOT` to a temporary test folder.
2. Attempt preview/export outside that folder; it must be rejected.
3. Create an existing destination file and export with `overwrite=false`; it must be rejected.
4. Repeat with `overwrite=true`; the export should succeed.
5. Confirm Save updates the attached CDR while Save As only writes the explicitly supplied `.cdr` path.

## 7. Long export

1. Use a large multipage signage file that normally takes longer than 60 seconds to export.
2. Export PDF and PNG.
3. Confirm the call remains active for up to five minutes and returns the final non-empty file instead of a 60-second timeout.
4. Confirm no duplicate export or duplicate document mutation occurs.

## 8. Client matrix

Repeat the compact workflow in each supported local MCP client you intend to publish for:

- Claude Desktop
- A compatible desktop ChatGPT build, only if it supports custom local MCP
- Your chosen local CLI/IDE MCP client

Browser-only clients are outside the supported scope.

## Release gate

Do not mark a CorelDRAW version as certified until all sections pass on that exact version. Keep failures with the server log, CorelDRAW version, document type, and reproduction steps.
