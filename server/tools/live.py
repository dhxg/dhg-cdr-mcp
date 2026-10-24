"""Compact, model-friendly MCP surface for safe live CorelDRAW editing."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from core.models import ToolResult
from core.operations import apply_operations_raw, inspect_document_raw
from core.sessions import session_manager
from tools import export as export_tools


def _error(exc: Exception, code: str = "COREL_OPERATION_FAILED") -> ToolResult:
    text = str(exc)
    retryable = any(token in text.lower() for token in ("busy", "timeout", "rejected", "rpc"))
    if "Revision conflict" in text or "changed outside this MCP session" in text:
        code = "REVISION_CONFLICT"
    elif "no longer open" in text:
        code = "DOCUMENT_CLOSED"
    elif "Unknown or expired" in text:
        code = "SESSION_NOT_FOUND"
    return ToolResult.fail(text, code=code, retryable=retryable)


def _validated_destination(
    destination_path: str,
    *,
    suffixes: set[str],
    overwrite: bool,
) -> Path:
    path = Path(destination_path).expanduser()
    if not path.is_absolute():
        raise ValueError("destination_path must be absolute")
    path = path.resolve(strict=False)
    if path.suffix.lower() not in suffixes:
        raise ValueError(f"destination_path must end with one of: {', '.join(sorted(suffixes))}")
    output_root = os.environ.get("COREL_OUTPUT_ROOT", "").strip()
    if output_root:
        root = Path(output_root).expanduser().resolve(strict=False)
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise PermissionError(f"Destination is outside COREL_OUTPUT_ROOT: {root}") from exc
    if path.exists() and not overwrite:
        raise FileExistsError(f"Destination already exists: {path}")
    return path


def corel_status() -> ToolResult:
    """Return CorelDRAW connection health and all currently open documents."""
    try:
        docs = session_manager.list_documents()
        return ToolResult.ok("CorelDRAW is connected", connected=True, documents=docs)
    except Exception as exc:
        return _error(exc, "COREL_NOT_CONNECTED")


def list_open_documents() -> ToolResult:
    """List open CorelDRAW documents before choosing one for a live-edit session."""
    try:
        docs = session_manager.list_documents()
        return ToolResult.ok(f"Found {len(docs)} open document(s)", documents=docs)
    except Exception as exc:
        return _error(exc)


def attach_active_document() -> ToolResult:
    """Attach to the document currently active in CorelDRAW; never creates or opens a document."""
    try:
        session = session_manager.attach_active("edit_active")
        return ToolResult.ok("Attached to the active CorelDRAW document", **session.public())
    except Exception as exc:
        return _error(exc, "ATTACH_FAILED")


def attach_open_document(name_or_path: str) -> ToolResult:
    """Attach to a specifically named document that is already open in CorelDRAW."""
    try:
        session = session_manager.attach_by_name(name_or_path, "edit_file")
        return ToolResult.ok("Attached to the requested CorelDRAW document", **session.public())
    except Exception as exc:
        return _error(exc, "ATTACH_FAILED")


def create_new_document(width_mm: float, height_mm: float) -> ToolResult:
    """Explicitly create a blank CorelDRAW document and return its create_new session."""
    try:
        session = session_manager.create_new(width_mm, height_mm)
        return ToolResult.ok("Created a new CorelDRAW document", **session.public())
    except Exception as exc:
        return _error(exc, "CREATE_DOCUMENT_FAILED")


def inspect_document(
    session_id: str,
    page_index: int = 0,
    include_shapes: bool = True,
    max_shapes: int = 500,
) -> ToolResult:
    """Inspect the exact session document using top-left millimetre coordinates and stable shape IDs."""
    try:
        payload = session_manager.execute(
            session_id,
            lambda doc: inspect_document_raw(doc, page_index, include_shapes, max_shapes),
            refresh_fingerprint=True,
        )
        return ToolResult.ok("Document inspection complete", **payload)
    except Exception as exc:
        return _error(exc, "INSPECTION_FAILED")


def apply_operations(
    session_id: str,
    expected_revision: int,
    label: str,
    operations: list[dict[str, Any]],
) -> ToolResult:
    """Apply an atomic, single-undo batch to the attached live document; all geometry is page-top-left mm."""
    try:
        payload = session_manager.execute(
            session_id,
            lambda doc: apply_operations_raw(doc, operations),
            mutation=True,
            expected_revision=expected_revision,
            label=label or "AI edit",
        )
        return ToolResult.ok(
            f"Applied {len(operations)} operation(s) to the live document",
            operations=payload["result"],
            revision=payload["revision"],
            session=payload["session"],
        )
    except Exception as exc:
        return _error(exc)


def undo_last_edit(session_id: str) -> ToolResult:
    """Undo the latest CorelDRAW command group in the attached document."""
    try:
        session_manager.execute(
            session_id,
            lambda doc: doc.Undo(),
            mutation=False,
            refresh_fingerprint=True,
        )
        # Undo is itself an external revision change from the agent's perspective.
        session = session_manager.get(session_id)
        session.revision += 1
        return ToolResult.ok("Undid the last CorelDRAW edit", revision=session.revision, session=session.public())
    except Exception as exc:
        return _error(exc, "UNDO_FAILED")


def redo_last_edit(session_id: str) -> ToolResult:
    """Redo the latest undone CorelDRAW command group in the attached document."""
    try:
        session_manager.execute(
            session_id,
            lambda doc: doc.Redo(),
            mutation=False,
            refresh_fingerprint=True,
        )
        session = session_manager.get(session_id)
        session.revision += 1
        return ToolResult.ok("Redid the last CorelDRAW edit", revision=session.revision, session=session.public())
    except Exception as exc:
        return _error(exc, "REDO_FAILED")


def save_current_document(session_id: str) -> ToolResult:
    """Save to the document's existing path; never performs Save As or invents a filename."""
    try:
        def _save(doc):
            folder = str(getattr(doc, "FilePath", "") or "")
            name = str(getattr(doc, "FileName", "") or "")
            if not folder or not name:
                raise RuntimeError("DOCUMENT_HAS_NO_PATH: use save_document_as for this new document")
            doc.Save()
            return {"path": str(Path(folder) / name)}

        payload = session_manager.execute(session_id, _save, mutation=False)
        return ToolResult.ok("Saved the current CorelDRAW document", **payload)
    except Exception as exc:
        code = "DOCUMENT_HAS_NO_PATH" if "DOCUMENT_HAS_NO_PATH" in str(exc) else "SAVE_FAILED"
        return _error(exc, code)


def save_document_as(session_id: str, destination_path: str, overwrite: bool = False) -> ToolResult:
    """Explicitly save the attached document to a new absolute .cdr path."""
    try:
        path = _validated_destination(
            destination_path,
            suffixes={".cdr"},
            overwrite=overwrite,
        )

        def _save_as(doc):
            path.parent.mkdir(parents=True, exist_ok=True)
            doc.SaveAs(str(path))
            return {"path": str(path)}

        payload = session_manager.execute(session_id, _save_as, mutation=False)
        session = session_manager.get(session_id)
        session.file_path = os.path.normcase(os.path.abspath(str(path)))
        session.document_name = path.name
        return ToolResult.ok("Saved the CorelDRAW document to a new path", **payload)
    except Exception as exc:
        return _error(exc, "SAVE_AS_FAILED")


def render_preview(
    session_id: str,
    destination_path: str,
    width_px: int = 800,
    overwrite: bool = False,
) -> ToolResult:
    """Render the attached document page to a PNG without saving or changing the CDR file."""
    try:
        path = _validated_destination(
            destination_path,
            suffixes={".png"},
            overwrite=overwrite,
        )

        def _preview(doc):
            result = export_tools.export_preview_png(str(path), width_px=width_px)
            if not result.success:
                raise RuntimeError(result.error or "Preview export failed")
            return result.data or {"path": str(path)}

        payload = session_manager.execute(
            session_id,
            _preview,
            mutation=False,
            timeout=300.0,
        )
        return ToolResult.ok("Rendered a preview of the live document", **payload)
    except Exception as exc:
        return _error(exc, "PREVIEW_FAILED")


def export_document(
    session_id: str,
    format: str,
    destination_path: str,
    dpi: int = 300,
    overwrite: bool = False,
) -> ToolResult:
    """Export the attached document as pdf, dxf, svg, png, or jpeg without changing its CDR path."""
    try:
        fmt = format.strip().lower()
        allowed = {"pdf", "dxf", "svg", "png", "jpeg", "jpg"}
        if fmt not in allowed:
            raise ValueError(f"Unsupported export format: {fmt}")
        expected_suffix = ".jpg" if fmt == "jpg" else f".{fmt}"
        accepted_suffixes = {expected_suffix}
        if fmt in {"jpeg", "jpg"}:
            accepted_suffixes = {".jpg", ".jpeg"}
        path = _validated_destination(
            destination_path,
            suffixes=accepted_suffixes,
            overwrite=overwrite,
        )

        def _export(doc):
            if fmt == "pdf":
                result = export_tools.export_pdf(str(path))
            elif fmt == "dxf":
                result = export_tools.export_dxf(str(path))
            elif fmt == "svg":
                result = export_tools.export_svg(str(path))
            elif fmt == "png":
                result = export_tools.export_png(str(path), dpi=dpi)
            else:
                result = export_tools.export_jpeg(str(path), dpi=dpi)
            if not result.success:
                raise RuntimeError(result.error or f"{fmt} export failed")
            return result.data or {"path": str(path), "format": fmt}

        payload = session_manager.execute(
            session_id,
            _export,
            mutation=False,
            timeout=300.0,
        )
        return ToolResult.ok(f"Exported the live document as {fmt}", **payload)
    except Exception as exc:
        return _error(exc, "EXPORT_FAILED")


def detach_document(session_id: str) -> ToolResult:
    """End an MCP document session without closing or saving the CorelDRAW document."""
    try:
        session_manager.get(session_id)
        session_manager.detach(session_id)
        return ToolResult.ok("Detached the live-edit session; CorelDRAW remains open")
    except Exception as exc:
        return _error(exc, "SESSION_NOT_FOUND")
