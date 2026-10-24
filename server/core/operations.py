"""Validated, atomic operation engine for live CorelDRAW edits."""

from __future__ import annotations

from typing import Any

from core.coordinates import Bounds, bounds_to_corel, corel_bounds_to_top_left
from tools.text import _get_text_content, _set_text_bold, _set_text_content, _set_text_font, _set_text_size

_CDR_BOTTOM_LEFT = 1
_CDR_TEXT_SHAPE = 3


def _safe_attr(obj: Any, name: str, default: Any = None) -> Any:
    try:
        return getattr(obj, name)
    except Exception:
        return default


def _walk_shapes(shapes: Any, parent_path: list[str] | None = None):
    parent_path = parent_path or []
    for shape in shapes:
        sid = str(_safe_attr(shape, "StaticID", ""))
        yield shape, parent_path
        # Groups
        try:
            nested = shape.Shapes
            if nested and int(nested.Count) > 0:
                yield from _walk_shapes(nested, [*parent_path, sid])
        except Exception:
            pass
        # PowerClip content, if available in this CorelDRAW version.
        try:
            contents = shape.PowerClip.Shapes
            if contents and int(contents.Count) > 0:
                yield from _walk_shapes(contents, [*parent_path, sid, "powerclip"])
        except Exception:
            pass


class ShapeIndex:
    """One-page shape lookup that prefers StaticID and rejects ambiguous names."""

    def __init__(self, page: Any):
        self.by_id: dict[str, Any] = {}
        self.by_name: dict[str, list[Any]] = {}
        for shape, _ in _walk_shapes(page.Shapes):
            self.add(shape)

    def add(self, shape: Any) -> None:
        sid = str(_safe_attr(shape, "StaticID", ""))
        name = str(_safe_attr(shape, "Name", "") or "")
        if sid:
            self.by_id[sid] = shape
        if name:
            self.by_name.setdefault(name, []).append(shape)

    def resolve(self, target: str) -> Any:
        target = str(target)
        if target in self.by_id:
            return self.by_id[target]
        matches = self.by_name.get(target, [])
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ValueError(f"Ambiguous shape name on active page: {target}")
        raise ValueError(f"Shape not found on active page: {target}")


def _shape_type_name(shape: Any) -> str:
    value = int(_safe_attr(shape, "Type", -1))
    return {
        1: "rectangle",
        2: "ellipse",
        3: "text_frame",
        4: "curve",
        5: "polygon",
        6: "text",
        7: "group",
    }.get(value, f"type_{value}")


def _with_bottom_left_reference(doc: Any):
    """Small context helper implemented as a generator-free object for COM."""
    class ReferenceScope:
        def __enter__(self):
            self.old = _safe_attr(doc, "ReferencePoint", None)
            try:
                doc.ReferencePoint = _CDR_BOTTOM_LEFT
            except Exception:
                self.old = None
            return self

        def __exit__(self, exc_type, exc, tb):
            if self.old is not None:
                try:
                    doc.ReferencePoint = self.old
                except Exception:
                    pass
    return ReferenceScope()


def inspect_document_raw(doc: Any, page_index: int = 0, include_shapes: bool = True, max_shapes: int = 1000) -> dict[str, Any]:
    page = doc.ActivePage if page_index == 0 else doc.Pages(page_index)
    page_height = float(page.SizeHeight)
    page_width = float(page.SizeWidth)
    items: list[dict[str, Any]] = []

    if include_shapes:
        with _with_bottom_left_reference(doc):
            for shape, parent_path in _walk_shapes(page.Shapes):
                if len(items) >= max_shapes:
                    break
                sid = str(_safe_attr(shape, "StaticID", ""))
                width = float(_safe_attr(shape, "SizeWidth", 0.0) or 0.0)
                height = float(_safe_attr(shape, "SizeHeight", 0.0) or 0.0)
                left = float(_safe_attr(shape, "PositionX", 0.0) or 0.0)
                bottom = float(_safe_attr(shape, "PositionY", 0.0) or 0.0)
                b = corel_bounds_to_top_left(left, bottom, width, height, page_height)
                item: dict[str, Any] = {
                    "shape_id": sid,
                    "name": str(_safe_attr(shape, "Name", "") or ""),
                    "type": _shape_type_name(shape),
                    "page": int(page.Index),
                    "layer": str(_safe_attr(_safe_attr(shape, "Layer", None), "Name", "") or ""),
                    "parent_path": parent_path,
                    "bounds": {"x": round(b.x, 3), "y": round(b.y, 3), "width": round(b.width, 3), "height": round(b.height, 3)},
                    "locked": bool(_safe_attr(shape, "Locked", False)),
                }
                if int(_safe_attr(shape, "Type", -1)) == _CDR_TEXT_SHAPE:
                    try:
                        item["text"] = _get_text_content(shape.Text)
                        item["editable_text"] = True
                    except Exception:
                        item["editable_text"] = False
                items.append(item)

    return {
        "name": str(_safe_attr(doc, "FileName", "") or _safe_attr(doc, "Name", "Untitled")),
        "path": str(_safe_attr(doc, "FilePath", "") or ""),
        "modified": bool(_safe_attr(doc, "Modified", False)),
        "pages": int(doc.Pages.Count),
        "current_page": int(page.Index),
        "canvas": {
            "width": round(page_width, 3),
            "height": round(page_height, 3),
            "unit": "mm",
            "coordinate_space": "page_top_left",
        },
        "shape_count_returned": len(items),
        "truncated": include_shapes and len(items) >= max_shapes,
        "shapes": items,
    }


def _target_id(op: dict[str, Any]) -> str:
    target = op.get("target", op.get("shape_id", ""))
    if isinstance(target, dict):
        target = target.get("shape_id") or target.get("name") or ""
    if not target:
        raise ValueError("Operation target must contain shape_id or name")
    return str(target)


def _required_bounds(op: dict[str, Any]) -> Bounds:
    raw = op.get("bounds") or {}

    def _pick(keys):
        for k in keys:
            if op.get(k) is not None:
                return op[k]
            if raw.get(k) is not None:
                return raw[k]
        return None

    x = _pick(["x_mm", "x"])
    y = _pick(["y_mm", "y"])
    width = _pick(["width_mm", "width"])
    height = _pick(["height_mm", "height"])
    return Bounds(
        x=float(x),
        y=float(y),
        width=float(width),
        height=float(height),
    ).validate()


def apply_operations_raw(doc: Any, operations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not operations:
        raise ValueError("At least one operation is required")
    if len(operations) > 250:
        raise ValueError("A single transaction supports at most 250 operations")

    page = doc.ActivePage
    page_height = float(page.SizeHeight)
    shape_index = ShapeIndex(page)
    results: list[dict[str, Any]] = []

    with _with_bottom_left_reference(doc):
        for index, op in enumerate(operations):
            name = str(op.get("op", "")).strip().lower()
            if not name:
                raise ValueError(f"Operation {index} is missing 'op'")

            if name == "text.set_content":
                shape = shape_index.resolve(_target_id(op))
                old = _get_text_content(shape.Text)
                _set_text_content(shape.Text, str(op.get("value", "")))
                results.append({"index": index, "op": name, "shape_id": str(shape.StaticID), "old": old})

            elif name == "text.set_style":
                shape = shape_index.resolve(_target_id(op))
                text = shape.Text
                if op.get("font_family"):
                    _set_text_font(text, str(op["font_family"]))
                if float(op.get("font_size_pt", 0) or 0) > 0:
                    _set_text_size(text, float(op["font_size_pt"]))
                if "bold" in op:
                    _set_text_bold(text, bool(op["bold"]))
                results.append({"index": index, "op": name, "shape_id": str(shape.StaticID)})

            elif name in {"shape.set_bounds", "shape.move", "shape.resize"}:
                shape = shape_index.resolve(_target_id(op))
                current_w = float(shape.SizeWidth)
                current_h = float(shape.SizeHeight)
                current_left = float(shape.PositionX)
                current_bottom = float(shape.PositionY)
                current = corel_bounds_to_top_left(current_left, current_bottom, current_w, current_h, page_height)
                if name == "shape.set_bounds":
                    desired = _required_bounds(op)
                elif name == "shape.move":
                    desired = Bounds(float(op["x"]), float(op["y"]), current.width, current.height)
                else:
                    desired = Bounds(current.x, current.y, float(op["width"]), float(op["height"]))
                left, bottom, _, _ = bounds_to_corel(desired, page_height)
                shape.SetSize(desired.width, desired.height)
                shape.SetPosition(left, bottom)
                results.append({"index": index, "op": name, "shape_id": str(shape.StaticID), "bounds": desired.__dict__})

            elif name == "shape.create_rectangle":
                b = _required_bounds(op)
                left, bottom, right, top = bounds_to_corel(b, page_height)
                radius = float(op.get("corner_radius", 0.0) or 0.0)
                shape = page.ActiveLayer.CreateRectangle(left, bottom, right, top, radius, radius, radius, radius)
                shape.Name = str(op.get("name") or f"rect_{shape.StaticID}")
                shape_index.add(shape)
                results.append({"index": index, "op": name, "shape_id": str(shape.StaticID), "name": shape.Name})

            elif name == "shape.create_ellipse":
                b = _required_bounds(op)
                left, bottom, right, top = bounds_to_corel(b, page_height)
                shape = page.ActiveLayer.CreateEllipse(left, bottom, right, top)
                shape.Name = str(op.get("name") or f"ellipse_{shape.StaticID}")
                shape_index.add(shape)
                if op.get("fill_rgb") is not None:
                    r, g, bl = op["fill_rgb"]
                    shape.Fill.UniformColor.RGBAssign(r, g, bl)
                elif op.get("fill_cmyk") is not None:
                    shape.Fill.UniformColor.CMYKAssign(*[int(v) for v in op["fill_cmyk"]])
                if op.get("outline_rgb") is not None:
                    r, g, bl = op["outline_rgb"]
                    shape.Outline.Width = float(op.get("outline_width_pt", 1.0) or 1.0)
                    shape.Outline.Color.RGBAssign(r, g, bl)
                elif op.get("no_outline"):
                    shape.Outline.SetNoOutline()
                results.append({"index": index, "op": name, "shape_id": str(shape.StaticID), "name": shape.Name})

            elif name == "text.create_frame":
                b = _required_bounds(op)
                left, bottom, right, top = bounds_to_corel(b, page_height)
                text_value = str(op.get("text") if op.get("text") is not None else op.get("value", ""))
                shape = page.ActiveLayer.CreateParagraphText(left, top, right, bottom, text_value)
                shape.Name = str(op.get("name") or f"text_{shape.StaticID}")
                shape_index.add(shape)
                if op.get("font_family"):
                    _set_text_font(shape.Text, str(op["font_family"]))
                if float(op.get("font_size_pt", 0) or 0) > 0:
                    _set_text_size(shape.Text, float(op["font_size_pt"]))
                if "bold" in op:
                    _set_text_bold(shape.Text, bool(op["bold"]))
                results.append({"index": index, "op": name, "shape_id": str(shape.StaticID), "name": shape.Name})

            elif name in {"fill.set_cmyk", "fill.set_rgb"}:
                shape = shape_index.resolve(_target_id(op))
                if name.endswith("cmyk"):
                    values = op.get("value") or op.get("cmyk")
                    if not isinstance(values, list) or len(values) != 4:
                        raise ValueError("fill.set_cmyk requires value: [c,m,y,k]")
                    shape.Fill.UniformColor.CMYKAssign(*[int(v) for v in values])
                else:
                    values = op.get("value") or op.get("rgb")
                    if not isinstance(values, list) or len(values) != 3:
                        raise ValueError("fill.set_rgb requires value: [r,g,b]")
                    shape.Fill.UniformColor.RGBAssign(*[int(v) for v in values])
                results.append({"index": index, "op": name, "shape_id": str(shape.StaticID)})

            elif name == "shape.delete":
                shape = shape_index.resolve(_target_id(op))
                sid = str(shape.StaticID)
                shape.Delete()
                results.append({"index": index, "op": name, "shape_id": sid})

            elif name == "shape.rotate":
                shape = shape_index.resolve(_target_id(op))
                desired = float(op["angle_degrees"])
                current = float(_safe_attr(shape, "RotationAngle", 0.0) or 0.0)
                try:
                    shape.Rotate(desired - current)
                except Exception:
                    shape.RotationAngle = desired
                results.append({"index": index, "op": name, "shape_id": str(shape.StaticID), "absolute_angle_degrees": desired})

            elif name in {"append_page", "page.append", "page.add", "add_page"}:
                doc.AddPages(1)
                page = doc.Pages.Last
                page.Activate()
                width_mm = float(op.get("width_mm") or op.get("width") or 0.0)
                height_mm = float(op.get("height_mm") or op.get("height") or 0.0)
                if width_mm > 0 and height_mm > 0:
                    page.SetSize(width_mm, height_mm)
                page_height = float(page.SizeHeight)
                shape_index = ShapeIndex(page)
                results.append({
                    "index": index,
                    "op": name,
                    "page_index": int(page.Index),
                    "total_pages": int(doc.Pages.Count),
                    "width_mm": float(page.SizeWidth),
                    "height_mm": float(page.SizeHeight),
                })

            else:
                raise ValueError(f"Unsupported operation: {name}")

    return results
