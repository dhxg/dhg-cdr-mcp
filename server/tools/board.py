"""批量数据牌 / 制度牌。

两个工具：
- parse_board_records：解析数据（Word / Excel / 纯文本）成记录列表（每条 title + body），供用户核对。
- batch_system_board：读取当前选中的模板底板，按网格批量复制、替换标题/正文（保留样式）、
  长正文自动缩字号、各自群组，一次调用完成。

Word 解析用 python-docx 直接读文件（不启动 Word，速度快）：python-docx 的正文段落
（Document.paragraphs）天然不含表格内的段落，因此 Word 表格内容会被自动忽略。
"""

import os
import re

from core.connection import get_connection
from core.models import ToolResult
from tools.text import _get_text_content, _set_text_content
from tools.shapes import _collect_text_shapes, _safe_text_size

_CDR_MILLIMETER = 3
_CDR_PARAGRAPH_TEXT = 1


# ==================== 数据解析 ====================

def _para_is_bold(p) -> bool:
    """段落里所有非空 run 都加粗才算粗体。"""
    runs = [r for r in p.runs if r.text.strip()]
    if not runs:
        return False
    return all(r.bold for r in runs)


def _is_docx_heading(p, text: str, requested_level: int = 0) -> bool:
    """判断一个 python-docx 段落是否为标题：标题样式（Heading/标题 1-9），或短粗行自动识别。"""
    style_name = ""
    try:
        style_name = p.style.name or ""
    except Exception:
        pass
    digits = re.sub(r"heading|标题", "", style_name.lower()).strip()
    n = 0
    if digits:
        try:
            n = int(float(digits))
        except Exception:
            n = 0
    if requested_level > 0:
        return n == requested_level
    if 0 < n <= 9:
        return True
    # 自动识别：短粗行
    return 0 < len(text) <= 40 and _para_is_bold(p)


def _read_word_records(file_path: str, heading_level: int = 0) -> list:
    """用 python-docx 直接读，不启动 Word；只取正文段落，表格内容不提取。
    返回 (records, table_count)，table_count 为文档中的表格数量（用于最后提醒）。"""
    from docx import Document

    doc = Document(file_path)
    table_count = len(doc.tables)
    records = []
    title = ""
    body = []
    for p in doc.paragraphs:
        text = p.text.strip()
        if not text:
            continue
        if _is_docx_heading(p, text, heading_level):
            if title or body:
                records.append({"title": title, "body": "\n".join(body).strip()})
            title, body = text, []
        else:
            body.append(text)
    if title or body:
        records.append({"title": title, "body": "\n".join(body).strip()})
    return records, table_count


def _read_excel_records(file_path: str) -> list:
    from openpyxl import load_workbook

    wb = load_workbook(file_path, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    start = 0
    if rows:
        first = [str(c).strip() if c is not None else "" for c in rows[0]]
        if any(k in "".join(first) for k in ("标题", "正文", "内容", "title", "body")):
            start = 1
    records = []
    for r in rows[start:]:
        cells = ["" if c is None else str(c).strip() for c in r]
        if not any(cells):
            continue
        if len(cells) == 1:
            records.append({"title": cells[0], "body": ""})
        else:
            records.append({"title": cells[0], "body": "\n".join(c for c in cells[1:] if c)})
    wb.close()
    return records


def _read_text_records(text: str) -> list:
    """对话直接发：标题用全角（）或半角()单独成行标记，其下到下一个标题之间是正文。"""
    records = []
    title = None
    body_lines = []
    for raw in text.splitlines():
        line = raw.strip()
        m = re.match(r"^[（(](.+?)[）)]\s*$", line)
        if m:
            if title is not None:
                records.append({"title": title, "body": "\n".join(body_lines).strip()})
            title, body_lines = m.group(1).strip(), []
        elif title is not None:
            body_lines.append(raw.rstrip())
    if title is not None:
        records.append({"title": title, "body": "\n".join(body_lines).strip()})
    return records


def parse_board_records(
    source_type: str = "",
    file_path: str = "",
    text: str = "",
    heading_level: int = 0,
) -> ToolResult:
    """解析批量数据牌数据，返回记录列表（每条 title + body），供用户核对。

    Args:
        source_type: 来源类型 "word" / "excel" / "text"；留空且给了 file_path 时按扩展名判断。
        file_path: Word(.doc/.docx) 或 Excel(.xls/.xlsx/.xlsm) 文件路径。
        text: 对话直接发的纯文本，标题用全角（）或半角()标记。
        heading_level: Word 标题级别 1-9，0 表示自动识别。
    """
    source_type = (source_type or "").lower()
    if text and not file_path:
        source_type = "text"
    if not source_type and file_path:
        ext = os.path.splitext(file_path)[1].lower()
        if ext in (".doc", ".docx"):
            source_type = "word"
        elif ext in (".xls", ".xlsx", ".xlsm"):
            source_type = "excel"
        else:
            source_type = "text"

    table_count = 0
    try:
        if source_type == "word":
            if not file_path or not os.path.exists(file_path):
                return ToolResult.fail("Word 文件不存在，请确认路径")
            records, table_count = _read_word_records(file_path, int(heading_level))
            result = {"success": True, "result": records}
        elif source_type == "excel":
            if not file_path or not os.path.exists(file_path):
                return ToolResult.fail("Excel 文件不存在，请确认路径")
            result = {"success": True, "result": _read_excel_records(file_path)}
        else:
            if not text:
                return ToolResult.fail("没有收到文本内容，请把数据发给我（标题用（）标记）")
            result = {"success": True, "result": _read_text_records(text)}
    except Exception as e:
        return ToolResult.fail(f"数据解析失败: {e}")

    if not result["success"]:
        return ToolResult.fail(result.get("error", "数据解析失败"))
    records = result["result"]
    if not records:
        return ToolResult.fail("没有解析到任何记录，请检查数据格式")
    for i, r in enumerate(records):
        r["index"] = i + 1
    message = f"已解析 {len(records)} 条记录，请核对"
    if table_count > 0:
        message += f"；注意：文档中检测到 {table_count} 个表格，表格内容未提取"
    return ToolResult.ok(
        message,
        count=len(records),
        records=records,
        table_count=table_count,
    )


# ==================== 批量复制排版 ====================

def _is_paragraph(text_shape) -> bool:
    try:
        return int(text_shape.Text.Type) == _CDR_PARAGRAPH_TEXT
    except Exception:
        return False


def _is_overflowing(text_shape) -> bool:
    for getter in (
        lambda: bool(text_shape.Text.Overflows),
        lambda: bool(text_shape.Text.IsOverflowing),
    ):
        try:
            return getter()
        except Exception:
            continue
    return False


def _identify_title_body(text_shapes):
    """标题=字号最大的文字；正文=段落文本中字数最多的（无段落文本则取除标题外字数最多的）。"""
    if not text_shapes:
        return None, None
    title = max(text_shapes, key=_safe_text_size)
    paras = [t for t in text_shapes if _is_paragraph(t)]
    if paras:
        body = max(paras, key=lambda t: len(_get_text_content(t.Text)))
    else:
        rest = [t for t in text_shapes if t is not title]
        body = max(rest, key=lambda t: len(_get_text_content(t.Text))) if rest else None
    return title, body


def _replace_text_keep_style(text_shape, value: str) -> None:
    """替换文字内容，先记录字体/字号/字间距/对齐/行距等，改完再恢复（不调 FitTextToFrame）。"""
    text = text_shape.Text
    is_para = _is_paragraph(text_shape)
    font = char_space = word_space = align = line_space = pb = pa = None
    size = 0.0
    try:
        story = text.Story
        try:
            font = story.Font
        except Exception:
            pass
        try:
            size = float(story.Size)
        except Exception:
            pass
        try:
            char_space = story.CharSpacing
        except Exception:
            pass
        try:
            word_space = story.WordSpacing
        except Exception:
            pass
        if is_para:
            try:
                align = story.Alignment
            except Exception:
                pass
            try:
                line_space = story.LineSpacing
            except Exception:
                pass
            try:
                pb = story.ParaSpacingBefore
            except Exception:
                pass
            try:
                pa = story.ParaSpacingAfter
            except Exception:
                pass
    except Exception:
        story = None

    _set_text_content(text, str(value))

    if story is None:
        return
    try:
        if font:
            story.Font = font
        if size:
            story.Size = size
        if char_space is not None:
            story.CharSpacing = char_space
        if word_space is not None:
            story.WordSpacing = word_space
        if is_para:
            if align is not None:
                story.Alignment = align
            if line_space is not None:
                story.LineSpacing = line_space
            if pb is not None:
                story.ParaSpacingBefore = pb
            if pa is not None:
                story.ParaSpacingAfter = pa
    except Exception:
        pass


def _shrink_to_fit(text_shape, min_size: float = 6.0, step: float = 0.5):
    """段落正文溢出时，逐档缩小该副本字号到刚好放下；返回缩小的点数。"""
    if not _is_paragraph(text_shape) or not _is_overflowing(text_shape):
        return 0.0
    try:
        original = float(text_shape.Text.Story.Size)
        cur = original
        while cur > min_size:
            cur -= step
            text_shape.Text.Story.Size = cur
            if not _is_overflowing(text_shape):
                break
        return round(original - cur, 1)
    except Exception:
        return 0.0


def batch_system_board(
    records: list,
    columns: int = 4,
    gap: float = 10.0,
) -> ToolResult:
    """读取当前选中的模板底板，批量复制并按网格排版，替换标题/正文。

    用法：先在 CDR 里做好一个模板（底板 + 标题 + 正文），选中整个模板，然后调用本工具。
    原模板保留，副本从模板右侧开始按网格排列（一排 columns 个，间距 gap）。

    Args:
        records: 核对后的记录列表，每条 {"title": ..., "body": ...}。
        columns: 一排几个，默认 4。
        gap: 副本间距（mm），默认 10。
    """
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接")

    if not records:
        return ToolResult.fail("没有记录，请先用 parse_board_records 解析并核对")
    columns = int(columns) if int(columns) > 0 else 4
    gap = float(gap)

    def _do():
        doc = conn.app.ActiveDocument
        doc.Unit = _CDR_MILLIMETER
        sr = doc.SelectionRange
        if int(sr.Count) <= 0:
            raise RuntimeError("当前没有选中模板。请先在 CDR 里选中整个模板底板再试。")

        w = float(sr.SizeWidth)
        h = float(sr.SizeHeight)
        origin_x = w + gap

        doc.BeginCommandGroup("批量数据牌")
        try:
            doc.Application.Optimization = True
            placed = []
            for i, rec in enumerate(records):
                col = i % columns
                row = i // columns
                dx = origin_x + col * (w + gap)
                dy = -row * (h + gap)
                copy_range = sr.Duplicate(dx, dy)

                copy_texts = []
                for j in range(1, int(copy_range.Count) + 1):
                    _collect_text_shapes(copy_range.Item(j), copy_texts)
                ct, cb = _identify_title_body(copy_texts)
                if ct is not None:
                    _replace_text_keep_style(ct, rec.get("title", ""))
                shrunk = 0.0
                if cb is not None:
                    _replace_text_keep_style(cb, rec.get("body", ""))
                    shrunk = _shrink_to_fit(cb)

                group_id = ""
                try:
                    group_id = str(copy_range.Group().StaticID)
                except Exception:
                    pass

                placed.append({
                    "index": i + 1,
                    "title": rec.get("title", ""),
                    "group_id": group_id,
                    "shrink_pt": shrunk,
                })
        finally:
            doc.Application.Optimization = False
            doc.EndCommandGroup()

        return {
            "generated": len(records),
            "columns": columns,
            "gap_mm": gap,
            "placed": placed,
        }

    result = conn.safe_call(_do, timeout=300)
    if result["success"]:
        return ToolResult.ok("批量数据牌排版完成，请在 CDR 中查看", **result["result"])
    return ToolResult.fail(result.get("error", "批量排版失败"))
