"""Text tools: content, styling, overflow checks, and text-frame creation."""

from core.connection import get_connection
from core.models import ToolResult

_CDR_TEXT_SHAPE = 3
_CDR_PARAGRAPH_TEXT = 1
_CDR_MILLIMETER = 3
_ALIGNMENT_MAP = {"left": 0, "center": 3, "right": 1, "none": 0}


def _find_text_shape(shape_id: str):
    """Find a text shape by StaticID or name."""
    conn = get_connection()
    doc = conn.app.ActiveDocument
    if doc is None:
        return None
    target = str(shape_id)
    try:
        shapes = doc.ActivePage.Shapes
        try:
            shape = shapes(shape_id)
        except Exception:
            for s in shapes:
                try:
                    if str(s.StaticID) == target or s.Name == target:
                        shape = s
                        break
                except Exception:
                    continue
            else:
                return None
        try:
            if shape.Type == _CDR_TEXT_SHAPE:
                return shape
        except Exception:
            pass
        try:
            _ = shape.Text
        except Exception:
            return None
        return shape
    except Exception:
        return None


def _get_text_content(text) -> str:
    for getter in (
        lambda: text.Contents,
        lambda: text.GetContents(),
        lambda: text.Story.Text,
        lambda: text.Story,
    ):
        try:
            value = getter()
            if isinstance(value, str):
                return value
        except Exception:
            continue
    return ""


def _set_text_content(text, content: str) -> None:
    # 段落文本：CDR 只认 \r（段落分隔），\n 会被直接丢弃；而且事后用 Contents/SetContents
    # 会把 \r 降级成软换行（\x0b）。正确做法是先清空、再用 Story.InsertAfter 插入，
    # 这样 \r 才会保留为真正的段落分隔（每条独立成段）。
    try:
        if text.Type == _CDR_PARAGRAPH_TEXT:
            content = str(content).replace("\r\n", "\r").replace("\n", "\r")
            text.Contents = ""
            text.Story.InsertAfter(content)
            return
    except Exception:
        pass
    for setter in (
        lambda: setattr(text, "Contents", content),
        lambda: text.SetContents(2, content),
        lambda: setattr(text, "Story", content),
    ):
        try:
            setter()
            return
        except Exception:
            continue
    raise RuntimeError("This CorelDRAW version exposes no supported text-writing API")


def _set_text_font(text, font: str) -> None:
    for setter in (
        lambda: setattr(text.Story, "Font", font),
        lambda: setattr(text.FontProperties, "Name", font),
    ):
        try:
            setter()
            return
        except Exception:
            continue


def _set_text_size(text, size: float) -> None:
    for setter in (
        lambda: setattr(text.Story, "Size", size),
        lambda: setattr(text.FontProperties, "Size", size),
    ):
        try:
            setter()
            return
        except Exception:
            continue


def _set_text_bold(text, bold: bool) -> None:
    for setter in (
        lambda: setattr(text.Story, "Bold", bold),
        lambda: setattr(text.FontProperties, "Bold", bold),
    ):
        try:
            setter()
            return
        except Exception:
            continue


def _apply_default_text_style(shape, frame_height: float) -> None:
    text = shape.Text
    size = max(8.0, min(18.0, frame_height * 0.55))
    _set_text_size(text, size)
    try:
        shape.Fill.UniformColor.CMYKAssign(0, 0, 0, 100)
    except Exception:
        pass


def set_text_content(shape_id: str, content: str) -> ToolResult:
    """Replace text content; shape_id accepts a shape name or StaticID."""
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW is not connected")

    def _set():
        shape = _find_text_shape(shape_id)
        if shape is None:
            raise ValueError(f"Text shape not found: {shape_id}")
        old_content = _get_text_content(shape.Text)
        _set_text_content(shape.Text, content)
        text_type = "paragraph" if shape.Text.Type == _CDR_PARAGRAPH_TEXT else "artistic"
        return {"shape_id": shape_id, "old_content": old_content, "new_content": content, "text_type": text_type}

    result = conn.safe_call(_set)
    if result["success"]:
        return ToolResult.ok(f"Text replaced: '{result['result']['old_content']}' → '{content}'", **result["result"])
    return ToolResult.fail(result.get("error", "Text replacement failed"))


def set_text_style(
    shape_id: str,
    font: str = "",
    size: float = 0,
    bold: bool = False,
    italic: bool = False,
    alignment: str = "",
    font_name: str = "",
    font_size: float = 0,
) -> ToolResult:
    """Set font, size, bold, italic, and alignment for a text shape."""
    font = font or font_name
    size = size if size > 0 else font_size
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW is not connected")

    def _style():
        shape = _find_text_shape(shape_id)
        if shape is None:
            raise ValueError(f"Text shape not found: {shape_id}")
        changes = {}
        text = shape.Text
        if font:
            _set_text_font(text, font)
            changes["font"] = font
        if size > 0:
            _set_text_size(text, size)
            changes["size"] = size
        if bold:
            _set_text_bold(text, True)
            changes["bold"] = True
        if italic:
            try:
                text.FontProperties.Italic = True
                changes["italic"] = True
            except Exception:
                pass
        if alignment and alignment in _ALIGNMENT_MAP:
            try:
                text.Alignment = _ALIGNMENT_MAP[alignment]
                changes["alignment"] = alignment
            except Exception:
                pass
        if not changes:
            raise ValueError("No style changes were specified")
        return {"shape_id": shape_id, "changes": changes}

    result = conn.safe_call(_style)
    if result["success"]:
        changes = result["result"]["changes"]
        return ToolResult.ok(f"Text style updated: {changes}", **result["result"])
    return ToolResult.fail(result.get("error", "Text styling failed"))


def fit_text_to_frame(shape_id: str) -> ToolResult:
    """Fit paragraph text to its frame."""
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW is not connected")

    def _fit():
        shape = _find_text_shape(shape_id)
        if shape is None:
            raise ValueError(f"Text shape not found: {shape_id}")
        if shape.Text.Type != _CDR_PARAGRAPH_TEXT:
            raise ValueError(f"Fit-to-frame requires paragraph text; current type: {shape.Text.Type}")
        shape.Text.FitTextToFrame = True
        return {"shape_id": shape_id, "fitted": True}

    result = conn.safe_call(_fit)
    if result["success"]:
        return ToolResult.ok("Text fitted to frame", **result["result"])
    return ToolResult.fail(result.get("error", "Text fit-to-frame failed"))


def check_text_overflow(shape_id: str) -> ToolResult:
    """Check whether paragraph text overflows its frame."""
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW is not connected")

    def _check():
        shape = _find_text_shape(shape_id)
        if shape is None:
            raise ValueError(f"Text shape not found: {shape_id}")
        text_type = shape.Text.Type
        overflowing = False
        if text_type == _CDR_PARAGRAPH_TEXT:
            try:
                overflowing = shape.Text.Overflows
            except Exception:
                try:
                    overflowing = shape.Text.IsOverflowing
                except Exception:
                    pass
        content_length = 0
        content_length = len(_get_text_content(shape.Text))
        return {
            "shape_id": shape_id,
            "overflowing": overflowing,
            "text_type": "paragraph" if text_type == _CDR_PARAGRAPH_TEXT else "artistic",
            "content_length": content_length,
        }

    result = conn.safe_call(_check)
    if result["success"]:
        status = "overflowing" if result["result"]["overflowing"] else "normal"
        return ToolResult.ok(f"Text status: {status}", **result["result"])
    return ToolResult.fail(result.get("error", "Text overflow check failed"))


def convert_text_to_curves(shape_id: str) -> ToolResult:
    """Convert text to curves to remove production font dependencies."""
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW is not connected")

    def _convert():
        shape = _find_text_shape(shape_id)
        if shape is None:
            raise ValueError(f"Text shape not found: {shape_id}")
        shape.ConvertToCurves()
        return {"shape_id": shape_id, "converted": True}

    result = conn.safe_call(_convert)
    if result["success"]:
        return ToolResult.ok(f"Text converted to curves: {shape_id}", **result["result"])
    return ToolResult.fail(result.get("error", "Text-to-curves conversion failed"))


def create_text_frame(x: float, y: float, width: float, height: float, text: str, top_left: bool = True) -> ToolResult:
    """Create a paragraph text frame using top-left coordinates by default."""
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW is not connected")

    def _create():
        doc = conn.app.ActiveDocument
        doc.Unit = _CDR_MILLIMETER
        page_h = doc.ActivePage.SizeHeight if doc else 297.0
        layer = doc.ActivePage.ActiveLayer
        if top_left:
            left = x
            right = x + width
            top = page_h - y
            bottom = page_h - y - height
        else:
            left, top = x, y
            right, bottom = x + width, y + height
        shape = layer.CreateParagraphText(left, top, right, bottom, text)
        _apply_default_text_style(shape, height)
        shape.Name = f"text_{shape.StaticID}"
        return {
            "shape_id": str(shape.StaticID),
            "name": shape.Name,
            "width": width,
            "height": height,
            "x": x,
            "y": y,
            "content": text,
        }

    result = conn.safe_call(_create)
    if result["success"]:
        return ToolResult.ok(f"Text frame created: {width}×{height}", **result["result"])
    return ToolResult.fail(result.get("error", "Text-frame creation failed"))


def create_artistic_text(x: float, y: float, text: str, font_size: float = 12.0, bold: bool = False, top_left: bool = True) -> ToolResult:
    """Create one-line artistic text using top-left coordinates by default."""
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW is not connected")

    def _create():
        doc = conn.app.ActiveDocument
        doc.Unit = _CDR_MILLIMETER
        page_h = doc.ActivePage.SizeHeight if doc else 297.0
        layer = doc.ActivePage.ActiveLayer
        cy = (page_h - y) if top_left else y
        shape = layer.CreateArtisticText(x, cy, text)
        _set_text_size(shape.Text, font_size)
        if bold:
            _set_text_bold(shape.Text, True)
        shape.Name = f"art_text_{shape.StaticID}"
        return {
            "shape_id": str(shape.StaticID),
            "name": shape.Name,
            "x": x,
            "y": y,
            "content": text,
            "font_size": font_size,
        }

    result = conn.safe_call(_create)
    if result["success"]:
        return ToolResult.ok(f"Artistic text created: {text}", **result["result"])
    return ToolResult.fail(result.get("error", "Artistic-text creation failed"))


def set_text_alignment(shape_id: str, align_h: str = "left", align_v: str = "top") -> ToolResult:
    """Set horizontal and vertical text alignment."""
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW is not connected")

    h_map = {"left": 0, "right": 1, "center": 3, "justify": 4}
    v_map = {"top": 0, "center": 1, "middle": 1, "bottom": 2, "justify": 3}

    def _align():
        shape = _find_text_shape(shape_id)
        if shape is None:
            raise ValueError(f"Text shape not found: {shape_id}")
        
        t = shape.Text
        if align_h and align_h.lower() in h_map:
            try:
                t.Alignment = h_map[align_h.lower()]
            except Exception:
                try:
                    t.Story.Alignment = h_map[align_h.lower()]
                except Exception:
                    pass

        if align_v and align_v.lower() in v_map and shape.Text.Type == _CDR_PARAGRAPH_TEXT:
            try:
                frame = t.Frame
                frame.VerticalAlignment = v_map[align_v.lower()]
            except Exception:
                pass

        return {"shape_id": shape_id, "align_h": align_h, "align_v": align_v}

    result = conn.safe_call(_align)
    if result["success"]:
        return ToolResult.ok(f"Text alignment updated: horizontal={align_h}, vertical={align_v}", **result["result"])
    return ToolResult.fail(result.get("error", "Text alignment failed"))


def set_text_font_and_size(
    shape_id: str,
    font_name: str = "",
    font_size: float = 0.0,
    bold: bool = False,
    italic: bool = False,
    r: int = -1,
    g: int = -1,
    b: int = -1,
) -> ToolResult:
    """Set a text shape's font, size, bold, italic, and RGB color."""
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW is not connected")

    def _format():
        shape = _find_text_shape(shape_id)
        if shape is None:
            raise ValueError(f"Text shape not found: {shape_id}")
        
        t = shape.Text
        if font_name:
            _set_text_font(t, font_name)
        if font_size > 0:
            _set_text_size(t, font_size)
        if bold:
            _set_text_bold(t, True)
        if italic:
            try:
                t.FontProperties.Italic = True
            except Exception:
                pass

        if r >= 0 and g >= 0 and b >= 0:
            try:
                shape.Fill.UniformColor.RGBAssign(r, g, b)
            except Exception:
                pass

        return {
            "shape_id": shape_id,
            "font_name": font_name,
            "font_size": font_size,
            "bold": bold,
            "italic": italic,
            "color_rgb": [r, g, b] if r >= 0 else None,
        }

    result = conn.safe_call(_format)
    if result["success"]:
        return ToolResult.ok("Text formatting updated", **result["result"])
    return ToolResult.fail(result.get("error", "Text formatting failed"))



