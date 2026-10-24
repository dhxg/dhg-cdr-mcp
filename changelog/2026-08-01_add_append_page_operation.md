# Changelog — 2026-08-01

## Summary
Added support for page appending/creation operations (`append_page`, `page.append`, `page.add`, `add_page`) inside the batch operation engine `apply_operations_raw()`.

## Issue Addressed
When an AI client (such as Claude) called `apply_operations` with:
```json
{
  "expected_revision": 0,
  "label": "probe append page",
  "operations": [
    {
      "op": "append_page",
      "width_mm": 210,
      "height_mm": 297
    }
  ],
  "session_id": "sess_ff1448254013"
}
```
The request failed with error: `"Unsupported operation: append_page"`.

## Changes Made

### 1. `server/core/operations.py`
- Added operation handlers for `name in {"append_page", "page.append", "page.add", "add_page"}` in `apply_operations_raw()`.
- Implemented COM page creation (`doc.AddPages(1)`), page activation (`page.Activate()`), optional page sizing (`page.SetSize(width_mm, height_mm)`), and shape index refresh for subsequent operations in the batch.

### 2. `tests/test_operations.py`
- Updated mock `Page` and `Document` classes to support `AddPages`, `Activate`, and `SetSize`.
- Added unit test `test_append_page_operation` to verify `append_page` functionality and response schema.

## Verification
- Executed `python -m unittest tests/test_operations.py`: All 5 tests passed successfully.
