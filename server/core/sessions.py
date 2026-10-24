"""Live CorelDRAW document sessions and atomic transaction execution.

A session binds AI operations to one verified document instead of repeatedly
using whichever document happens to be active.  All COM access is serialized by
``CorelDrawConnection`` and every mutation is one CorelDRAW undo group.
"""

from __future__ import annotations

import os
import hashlib
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Literal, Optional

from core.connection import get_connection

SessionMode = Literal["edit_active", "edit_file", "create_new", "duplicate_then_edit"]
_CDR_MILLIMETER = 3


@dataclass
class DocumentSession:
    session_id: str
    mode: SessionMode
    document_name: str
    file_path: str
    document_ordinal: int
    revision: int = 0
    fingerprint: str = ""
    created_at: str = ""

    def public(self) -> dict[str, Any]:
        result = asdict(self)
        result["coordinate_space"] = "page_top_left"
        result["unit"] = "mm"
        return result


def _safe_attr(obj: Any, name: str, default: Any = "") -> Any:
    try:
        return getattr(obj, name)
    except Exception:
        return default


def _full_path(doc: Any) -> str:
    folder = str(_safe_attr(doc, "FilePath", "") or "")
    name = str(_safe_attr(doc, "FileName", "") or _safe_attr(doc, "Name", "") or "Untitled")
    return os.path.normcase(os.path.abspath(os.path.join(folder, name))) if folder else ""


def _document_fingerprint(doc: Any) -> str:
    """Cheap content fingerprint used to detect edits made outside MCP."""
    old_unit = _safe_attr(doc, "Unit", None)
    try:
        doc.Unit = _CDR_MILLIMETER
    except Exception:
        old_unit = None
    parts: list[str] = [str(_safe_attr(doc.Pages, "Count", 0))]

    def add_shapes(shapes: Any) -> None:
        try:
            iterator = iter(shapes)
        except Exception:
            return
        for shape in iterator:
            parts.append(
                "|".join(
                    [
                        str(_safe_attr(shape, "StaticID", "")),
                        str(_safe_attr(shape, "Name", "")),
                        str(round(float(_safe_attr(shape, "PositionX", 0) or 0), 4)),
                        str(round(float(_safe_attr(shape, "PositionY", 0) or 0), 4)),
                        str(round(float(_safe_attr(shape, "SizeWidth", 0) or 0), 4)),
                        str(round(float(_safe_attr(shape, "SizeHeight", 0) or 0), 4)),
                    ]
                )
            )
            try:
                parts.append(str(shape.Text.Story.Text))
            except Exception:
                pass
            try:
                nested = shape.Shapes
                if int(nested.Count) > 0:
                    add_shapes(nested)
            except Exception:
                pass

    try:
        for page in doc.Pages:
            parts.extend(
                [
                    f"page:{_safe_attr(page, 'Index', '')}",
                    str(round(float(_safe_attr(page, "SizeWidth", 0) or 0), 4)),
                    str(round(float(_safe_attr(page, "SizeHeight", 0) or 0), 4)),
                ]
            )
            add_shapes(page.Shapes)
    except Exception:
        pass
    digest = hashlib.sha256("\n".join(parts).encode("utf-8", "replace")).hexdigest()
    if old_unit is not None:
        try:
            doc.Unit = old_unit
        except Exception:
            pass
    return digest


class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, DocumentSession] = {}
        self._lock = threading.RLock()

    def _ensure_connected(self) -> None:
        conn = get_connection()
        if conn.status.connected and conn.is_alive():
            return
        # Lazy recovery supports the common sequence: MCP server first,
        # CorelDRAW second. existing_only remains safe and never launches it.
        if not conn.connect():
            raise RuntimeError(conn.status.last_error or "CorelDRAW is not connected")

    def list_documents(self) -> list[dict[str, Any]]:
        self._ensure_connected()
        conn = get_connection()

        def _list() -> list[dict[str, Any]]:
            items: list[dict[str, Any]] = []
            count = int(conn.app.Documents.Count)
            if count == 0:
                return items
            try:
                active_doc = conn.app.ActiveDocument
                active_path = _full_path(active_doc)
                active_name = str(_safe_attr(active_doc, "FileName", "") or _safe_attr(active_doc, "Name", ""))
            except Exception:
                active_path = ""
                active_name = ""
            for ordinal in range(1, count + 1):
                doc = conn.app.Documents(ordinal)
                page = doc.ActivePage
                old_unit = _safe_attr(doc, "Unit", None)
                doc.Unit = _CDR_MILLIMETER
                items.append(
                    {
                        "ordinal": ordinal,
                        "name": str(_safe_attr(doc, "FileName", "") or _safe_attr(doc, "Name", "Untitled")),
                        "path": _full_path(doc),
                        "active": bool(
                            _safe_attr(doc, "Active", False)
                            or (active_path and _full_path(doc) == active_path)
                            or (not active_path and active_name and str(_safe_attr(doc, "Name", "")) == active_name)
                        ),
                        "modified": bool(_safe_attr(doc, "Modified", False)),
                        "pages": int(doc.Pages.Count),
                        "current_page": int(page.Index),
                        "width_mm": round(float(page.SizeWidth), 3),
                        "height_mm": round(float(page.SizeHeight), 3),
                    }
                )
                if old_unit is not None:
                    doc.Unit = old_unit
            return items

        result = conn.safe_call(_list)
        if not result["success"]:
            raise RuntimeError(result.get("error") or "Unable to list CorelDRAW documents")
        return result["result"]

    def _register(self, metadata: dict[str, Any], mode: SessionMode) -> DocumentSession:
        session = DocumentSession(
            session_id=f"sess_{uuid.uuid4().hex[:12]}",
            mode=mode,
            document_name=str(metadata["name"]),
            file_path=str(metadata["path"]),
            document_ordinal=int(metadata["ordinal"]),
            fingerprint=str(metadata.get("fingerprint", "")),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            self._sessions[session.session_id] = session
        return session

    def attach_active(self, mode: SessionMode = "edit_active") -> DocumentSession:
        self._ensure_connected()
        conn = get_connection()

        def _attach() -> dict[str, Any]:
            doc = conn.app.ActiveDocument
            if not doc:
                raise RuntimeError("No document is open in CorelDRAW")
            count = int(conn.app.Documents.Count)
            active_path = _full_path(doc)
            active_name = str(_safe_attr(doc, "FileName", "") or _safe_attr(doc, "Name", "Untitled"))
            for ordinal in range(1, count + 1):
                candidate = conn.app.Documents(ordinal)
                candidate_path = _full_path(candidate)
                candidate_name = str(_safe_attr(candidate, "FileName", "") or _safe_attr(candidate, "Name", "Untitled"))
                if bool(_safe_attr(candidate, "Active", False)) or (active_path and candidate_path == active_path) or (not active_path and candidate_name == active_name):
                    return {"name": candidate_name, "path": candidate_path, "ordinal": ordinal, "fingerprint": _document_fingerprint(candidate)}
            return {"name": active_name, "path": active_path, "ordinal": 1, "fingerprint": _document_fingerprint(doc)}

        result = conn.safe_call(_attach)
        if not result["success"]:
            raise RuntimeError(result.get("error") or "Unable to attach active document")
        return self._register(result["result"], mode)

    def attach_by_name(self, name_or_path: str, mode: SessionMode = "edit_file") -> DocumentSession:
        self._ensure_connected()
        target_name = os.path.normcase(os.path.basename(name_or_path))
        target_path = os.path.normcase(os.path.abspath(name_or_path)) if os.path.isabs(name_or_path) else ""
        conn = get_connection()

        def _attach() -> dict[str, Any]:
            count = int(conn.app.Documents.Count)
            for ordinal in range(1, count + 1):
                doc = conn.app.Documents(ordinal)
                if target_path and _full_path(doc) == target_path:
                    doc.Activate()
                    return {"name": str(_safe_attr(doc, "FileName", "") or _safe_attr(doc, "Name", "Untitled")), "path": _full_path(doc), "ordinal": ordinal, "fingerprint": _document_fingerprint(doc)}
                current_name = os.path.normcase(str(_safe_attr(doc, "FileName", "") or _safe_attr(doc, "Name", "")))
                if current_name == target_name:
                    doc.Activate()
                    return {"name": str(_safe_attr(doc, "FileName", "") or _safe_attr(doc, "Name", "Untitled")), "path": _full_path(doc), "ordinal": ordinal, "fingerprint": _document_fingerprint(doc)}
            raise RuntimeError(f"The requested document is not open: {name_or_path}")

        result = conn.safe_call(_attach)
        if not result["success"]:
            raise RuntimeError(result.get("error") or "Unable to attach document")
        return self._register(result["result"], mode)

    def create_new(self, width_mm: float, height_mm: float) -> DocumentSession:
        self._ensure_connected()
        if width_mm <= 0 or height_mm <= 0:
            raise ValueError("Document width and height must be greater than zero")
        conn = get_connection()

        def _create() -> dict[str, Any]:
            doc = conn.app.CreateDocument()
            doc.Unit = _CDR_MILLIMETER
            doc.ActivePage.SetSize(width_mm, height_mm)
            return {
                "name": str(_safe_attr(doc, "FileName", "") or _safe_attr(doc, "Name", "Untitled")),
                "path": _full_path(doc),
                "ordinal": int(conn.app.Documents.Count),
                "fingerprint": _document_fingerprint(doc),
            }

        result = conn.safe_call(_create)
        if not result["success"]:
            raise RuntimeError(result.get("error") or "Unable to create document")
        return self._register(result["result"], "create_new")

    def get(self, session_id: str) -> DocumentSession:
        with self._lock:
            session = self._sessions.get(session_id)
        if not session:
            raise KeyError(f"Unknown or expired session: {session_id}")
        return session

    def detach(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def _resolve_document(self, session: DocumentSession) -> Any:
        """Resolve a session on the COM thread without trusting ActiveDocument."""
        conn = get_connection()
        count = int(conn.app.Documents.Count)
        if session.file_path:
            for ordinal in range(1, count + 1):
                doc = conn.app.Documents(ordinal)
                if _full_path(doc) == session.file_path:
                    return doc
        # Unsaved documents are matched by original ordinal first, then name.
        if 1 <= session.document_ordinal <= count:
            candidate = conn.app.Documents(session.document_ordinal)
            current_name = str(_safe_attr(candidate, "FileName", "") or _safe_attr(candidate, "Name", "Untitled"))
            if current_name == session.document_name:
                return candidate
        for ordinal in range(1, count + 1):
            doc = conn.app.Documents(ordinal)
            current_name = str(_safe_attr(doc, "FileName", "") or _safe_attr(doc, "Name", "Untitled"))
            if current_name == session.document_name:
                return doc
        raise RuntimeError("The CorelDRAW document attached to this session is no longer open")

    def execute(
        self,
        session_id: str,
        action: Callable[[Any], Any],
        *,
        mutation: bool = False,
        expected_revision: Optional[int] = None,
        label: str = "AI edit",
        refresh_fingerprint: bool = False,
        timeout: float = 60.0,
    ) -> dict[str, Any]:
        session = self.get(session_id)
        if mutation and expected_revision is not None and expected_revision != session.revision:
            raise RuntimeError(
                f"Revision conflict: expected {expected_revision}, current {session.revision}. "
                "Inspect the document again before applying changes."
            )
        conn = get_connection()

        def _execute() -> Any:
            doc = self._resolve_document(session)
            current_fingerprint = _document_fingerprint(doc)
            if mutation and session.fingerprint and current_fingerprint != session.fingerprint:
                raise RuntimeError(
                    "Document changed outside this MCP session. Inspect it again before applying changes."
                )
            doc.Activate()
            old_unit = _safe_attr(doc, "Unit", None)
            doc.Unit = _CDR_MILLIMETER
            group_started = False
            old_optimization = _safe_attr(conn.app, "Optimization", False)
            try:
                if mutation:
                    doc.BeginCommandGroup(label[:120])
                    group_started = True
                    conn.app.Optimization = True
                value = action(doc)
                if group_started:
                    doc.EndCommandGroup()
                    group_started = False
                if mutation:
                    session.revision += 1
                    session.fingerprint = _document_fingerprint(doc)
                elif refresh_fingerprint:
                    session.fingerprint = _document_fingerprint(doc)
                return value
            except Exception:
                if group_started:
                    try:
                        doc.EndCommandGroup()
                    except Exception:
                        pass
                    try:
                        doc.Undo()
                    except Exception:
                        pass
                raise
            finally:
                if mutation:
                    try:
                        conn.app.Optimization = old_optimization
                        conn.app.Refresh()
                    except Exception:
                        pass
                if old_unit is not None:
                    try:
                        doc.Unit = old_unit
                    except Exception:
                        pass

        result = conn.safe_call(
            _execute,
            timeout=timeout,
            idempotent=not mutation,
        )
        if not result["success"]:
            raise RuntimeError(result.get("error") or "CorelDRAW operation failed")
        return {"result": result["result"], "revision": session.revision, "session": session.public()}


session_manager = SessionManager()
