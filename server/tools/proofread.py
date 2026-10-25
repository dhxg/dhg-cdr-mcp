"""错别字检查辅助工具：提取选中文字 / 分色标记 / 恢复原色。

【功能规范】（使用者须知，公开分享同样适用）
- 流程规范：选中文字 → 提取 → 检查 → **检查完直接分色标记，不再询问**。
  标记不是可选项，是本功能的既定行为；标记只改颜色、不改内容，可一键恢复。
- 检查范围 3 类：错别字 / 语句不通 / 逻辑问题（标点错误不再检查）。
  颜色对应：红=错别字，蓝=语句不通，橙=逻辑问题。
- 标记前自动读取原色，撞色自动换反差色（changed_segments 注明），不混淆。
- 一键恢复：restore_marked_colors 还原全部标记为原色；标记记录持久化到
  系统临时目录（服务重启不丢）。

设计要点（省 Token / 额度，硬要求）：
- 三个工具全部是本地 COM 操作，不调用任何外部 API —— 0 Token、0 额度。
- 检查动作由对话侧 LLM（豆包）完成；插件只负责"读文字 / 标颜色 / 恢复"。
- 标记按字符段定位（CorelDRAW Story.Characters(Start, Length)，1-based），
  调用参数只传 shape_id + start/end + 类别，不重复传输文字内容。
- 标记前记录每段原色，restore_marked_colors 一键恢复；记录不到原色的段不
  标记，保证"标过的都一定能恢复"。
- 实测确认：CDR 2026 用 text.Story.Characters(Start, Length)（1-based）访问
  字符范围，其 .Fill.UniformColor 可读写；Text.Characters 属性不存在。

安全（遵守 corel-cdr-operator 硬规则）：
- 只改文字对象的填充颜色，不删除元素、不改文字内容、不保存文档。
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any

from core.connection import get_connection
from core.models import ToolResult
from core.operations import ShapeIndex
from tools.text import _get_text_content

_CDR_TEXT_SHAPE = 6  # CorelDRAW 2026: 6=文字, 3=曲线（get_selection 实测口径）
_CDR_MILLIMETER = 3

# 默认标记色（可用 color_map 覆盖）：
#   红 = 错别字，蓝 = 语句不通，橙 = 逻辑问题
#   （绿 = 标点错误，通道保留兼容，检查规范不再产出标点类）
_DEFAULT_COLORS: dict[str, tuple[int, int, int]] = {
    "typo": (255, 0, 0),
    "grammar": (0, 0, 255),
    "logic": (255, 140, 0),
    "punctuation": (0, 128, 0),
}

# 已标记状态：{shape_id: {"segments": [(start_1based, length, 原色rgb)], "object": 原色rgb|None}}
_MARKED_STATE: dict[str, dict[str, Any]] = {}
# 持久化到系统临时目录：服务重启后一键恢复依然可用（记录不丢）
_STATE_FILE = os.path.join(tempfile.gettempdir(), "xinge_cdr_mark_state.json")


def _load_state() -> None:
    """从磁盘加载标记记录（服务重启后恢复可用）。"""
    _MARKED_STATE.clear()
    try:
        with open(_STATE_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        for sid, st in data.items():
            _MARKED_STATE[str(sid)] = {
                "segments": [(int(s), int(l), tuple(rgb)) for s, l, rgb in st.get("segments", [])],
                "object": tuple(st["object"]) if st.get("object") else None,
            }
    except Exception:
        pass


def _save_state() -> None:
    """把标记记录写入磁盘（标记后/恢复后调用）。"""
    try:
        data = {
            sid: {
                "segments": [[s, l, list(rgb)] for s, l, rgb in st["segments"]],
                "object": list(st["object"]) if st.get("object") else None,
            }
            for sid, st in _MARKED_STATE.items()
        }
        with open(_STATE_FILE, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
    except Exception:
        pass

# 智能换色：标记前读原色，撞色时自动换成反差最大的颜色（避免与设计稿原色混淆）
_SMART_THRESHOLD = 250.0  # 感知距离阈值：低于此值视为"撞色"
_EXTRA_COLORS: list[tuple[int, int, int]] = [
    (255, 0, 0),      # 红
    (0, 0, 255),      # 蓝
    (255, 140, 0),    # 橙
    (0, 128, 0),      # 绿
    (128, 0, 255),    # 紫
    (0, 180, 180),    # 青
    (255, 0, 128),    # 品红
    (230, 200, 0),    # 黄
]


def _color_distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    """加权感知颜色距离（人眼对绿色更敏感）。"""
    dr, dg, db = a[0] - b[0], a[1] - b[1], a[2] - b[2]
    return (2 * dr * dr + 4 * dg * dg + 3 * db * db) ** 0.5


def _smart_color(old: tuple[int, int, int], preferred: tuple[int, int, int]) -> tuple[int, int, int]:
    """原色与目标色撞色时，从色板选与 old 反差最大的颜色。"""
    if _color_distance(old, preferred) >= _SMART_THRESHOLD:
        return preferred
    best, best_dist = preferred, -1.0
    for candidate in _EXTRA_COLORS:
        d = _color_distance(old, candidate)
        if d > best_dist:
            best, best_dist = candidate, d
    return best


def _read_color_rgb(color: Any) -> tuple[int, int, int] | None:
    """尽力读取 Color 对象当前 RGB；读不到返回 None（该段不标记）。"""
    for attr in ("RGBValue", "RGB"):
        try:
            value = getattr(color, attr)
        except Exception:
            continue
        if isinstance(value, str):
            s = value.strip().replace(" ", "")
            if s.startswith("#") and len(s) == 7:
                try:
                    return (int(s[1:3], 16), int(s[3:5], 16), int(s[5:7], 16))
                except Exception:
                    return None
            if "," in s:
                parts = [int(p) for p in s.split(",")]
                if len(parts) == 3:
                    return (parts[0], parts[1], parts[2])
        elif isinstance(value, int):
            return ((value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF)
    return None


def _story_chars(text: Any) -> Any | None:
    """返回 Story.Characters 方法（(Start, Length)，1-based）；不可用返回 None。"""
    try:
        fn = text.Story.Characters
        if not callable(fn):
            return None
        probe = fn(1, 1)  # 冒烟测试：验证通道可用
        _ = probe.Text
        return fn
    except Exception:
        return None


def _set_range_rgb(rng: Any, r: int, g: int, b: int) -> None:
    try:
        rng.Fill.UniformColor.RGBAssign(int(r), int(g), int(b))
    except Exception:
        raise RuntimeError("此 CorelDRAW 版本不支持字符段改色")


def _set_shape_rgb(shape: Any, r: int, g: int, b: int) -> None:
    try:
        shape.Fill.UniformColor.RGBAssign(int(r), int(g), int(b))
    except Exception:
        raise RuntimeError("此 CorelDRAW 版本不支持文字改色")


def _restore_marked(doc: Any, index: ShapeIndex) -> tuple[int, list[dict[str, Any]]]:
    """恢复全部已标记字符的原色；返回 (restored_chars, failed)。

    供 restore_marked_colors 与 fix_text_errors（改字前先恢复标记）共用。
    """
    restored_chars = 0
    failed: list[dict[str, Any]] = []
    for sid, state in list(_MARKED_STATE.items()):
        try:
            shape = index.resolve(sid)
        except Exception:
            failed.append({"shape_id": sid, "reason": "形状已不存在或不可用"})
            continue
        fn = None
        try:
            fn = _story_chars(shape.Text)
        except Exception:
            fn = None
        # 字符段记录优先恢复
        for start_1, length, old in list(state.get("segments", [])):
            try:
                if fn is not None:
                    _set_range_rgb(fn(start_1, length), old[0], old[1], old[2])
                    restored_chars += length
                    state["segments"].remove((start_1, length, old))
                else:
                    failed.append({"shape_id": sid, "reason": "Characters 不可用"})
                    break
            except Exception:
                failed.append({"shape_id": sid, "start": start_1, "length": length, "reason": "恢复失败"})
        # 整对象记录
        if state.get("object") is not None:
            old = state["object"]
            try:
                _set_shape_rgb(shape, old[0], old[1], old[2])
                restored_chars += 1
                state["object"] = None
            except Exception:
                failed.append({"shape_id": sid, "reason": "整对象恢复失败"})
        if not state["segments"] and state["object"] is None:
            _MARKED_STATE.pop(sid, None)
    return restored_chars, failed


def _collect_text_shapes(container: Any) -> list[Any]:
    """递归收集容器内的文字形状（支持群组与 PowerClip 下钻），按 StaticID 去重。

    用户选中的常是"底图+文字"的群组（门牌、制度牌等），必须下钻才能拿到文字。
    """
    found: dict[str, Any] = {}

    def walk(shapes: Any) -> None:
        for s in shapes:
            try:
                t = int(s.Type)
            except Exception:
                continue
            if t == _CDR_TEXT_SHAPE:
                sid = str(s.StaticID)
                if sid:
                    found[sid] = s
                continue
            try:
                nested = s.Shapes
                if int(nested.Count) > 0:
                    walk(nested)
            except Exception:
                pass
            try:
                contents = s.PowerClip.Shapes
                if int(contents.Count) > 0:
                    walk(contents)
            except Exception:
                pass

    walk(container)
    return list(found.values())


def extract_selected_text() -> ToolResult:
    """读取当前在 CorelDRAW 里选中的文字对象及其全文。

    返回 items：[{shape_id, text}]，text 供检查；标记时 start/end 以 text 的
    字符位置为准（0-based、闭区间 [start, end]）。
    """
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接")

    def _do() -> dict[str, Any]:
        doc = conn.app.ActiveDocument
        doc.Unit = _CDR_MILLIMETER
        sr = doc.SelectionRange
        n = int(sr.Count)
        if n <= 0:
            return {
                "count": 0,
                "items": [],
                "hint": "当前没有选中任何元素。请在 CorelDRAW 里点选要检查的文字，然后再说一次。",
            }
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        for i in range(1, n + 1):
            for s in _collect_text_shapes([sr.Item(i)]):
                sid = str(s.StaticID)
                if sid in seen:
                    continue
                seen.add(sid)
                try:
                    items.append({"shape_id": sid, "text": _get_text_content(s.Text)})
                except Exception:
                    continue
        if not items:
            return {"count": 0, "items": [], "hint": "选中内容里没有文字对象，请选中文字后重试。"}
        return {"count": len(items), "items": items}

    result = conn.safe_call(_do, timeout=40)
    if result["success"]:
        return ToolResult.ok("已读取选中文字", **result["result"])
    return ToolResult.fail(result.get("error", "读取选中文字失败"))


def mark_text_errors(errors: list[dict[str, Any]], color_map: dict[str, Any] | None = None) -> ToolResult:
    """按字符范围分色标记文字（只改颜色，不改内容、不保存）。

    errors: [{shape_id, start, end, type}]，start/end 为 0-based 字符索引、闭区间
    [start, end]，基于 extract_selected_text 返回的 text 位置；type ∈ typo
    （错别字）/ grammar（语句不通）/ logic（逻辑问题）（punctuation 通道保留
    兼容，检查规范不再产出标点类）。
    默认色：typo=红，grammar=蓝，logic=橙，punctuation=绿，color_map 可覆盖。
    标记前自动读取原色，原色与标记色撞色时自动改用反差最大的颜色
    （结果里 changed_segments 注明），避免与设计稿原有彩色文字混淆。
    按功能规范：检查完直接调用本工具标记，不再询问用户。
    字符段接口不可用时自动降级为整对象标记（结果里 mode 标明）。
    标记前记录原色；恢复请调用 restore_marked_colors。
    """
    colors = dict(_DEFAULT_COLORS)
    if color_map:
        for key, value in color_map.items():
            if isinstance(value, (list, tuple)) and len(value) == 3:
                try:
                    colors[str(key).strip().lower()] = (int(value[0]), int(value[1]), int(value[2]))
                except Exception:
                    pass

    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接")

    def _do() -> dict[str, Any]:
        if not errors:
            raise ValueError("errors 不能为空")
        _load_state()
        doc = conn.app.ActiveDocument
        doc.Unit = _CDR_MILLIMETER
        index = ShapeIndex(doc.ActivePage)
        applied_items = 0
        marked_chars = 0
        skipped: list[dict[str, Any]] = []
        changed_segments: list[dict[str, Any]] = []
        modes: dict[str, int] = {"char": 0, "object": 0}
        for idx, e in enumerate(errors):
            sid = str(e.get("shape_id", "") or "")
            if not sid:
                raise ValueError(f"errors[{idx}] 缺少 shape_id")
            shape = index.resolve(sid)
            if int(shape.Type) != _CDR_TEXT_SHAPE:
                raise ValueError(f"shape {sid} 不是文字对象")
            typ = str(e.get("type", "typo")).strip().lower()
            if typ not in colors:
                raise ValueError(f"errors[{idx}] type 只支持 typo/grammar/logic/punctuation，收到: {typ}")
            start = int(e.get("start", -1))
            end = int(e.get("end", -1))
            if start < 0 or end < start:
                raise ValueError(f"errors[{idx}] start/end 非法: start={start}, end={end}")
            text = _get_text_content(shape.Text)
            if end >= len(text):
                raise ValueError(f"errors[{idx}] end({end}) 超出文本长度(共 {len(text)} 字)")
            r, g, b = colors[typ]
            state = _MARKED_STATE.setdefault(sid, {"segments": [], "object": None})
            fn = _story_chars(shape.Text)
            if fn is not None:
                # 字符段级标记：CDR 1-based = Python 索引 + 1
                start_1 = start + 1
                length = end - start + 1
                seg = fn(start_1, length)
                old = _read_color_rgb(seg.Fill.UniformColor)
                if old is None:
                    # 段级读不到原色（继承默认色等）：降级读整对象填充色
                    shape_old = _read_color_rgb(shape.Fill.UniformColor)
                    if shape_old is None:
                        skipped.append({"shape_id": sid, "range": [start, end], "reason": "无法读取原色，未标记"})
                        continue
                    old = shape_old
                mark_rgb = _smart_color(old, (r, g, b))
                # 重复标记同一段时先清除旧记录，恢复始终以本次标记前的原色为准
                state["segments"] = [
                    s for s in state["segments"] if not (s[0] == start_1 and s[1] == length)
                ]
                state["segments"].append((start_1, length, old))
                _set_range_rgb(seg, *mark_rgb)
                marked_chars += length
                modes["char"] += 1
                if mark_rgb != (r, g, b):
                    changed_segments.append(
                        {
                            "shape_id": sid,
                            "range": [start, end],
                            "type": typ,
                            "original_rgb": list(old),
                            "marked_rgb": list(mark_rgb),
                        }
                    )
            else:
                # 降级：整对象标记
                old = _read_color_rgb(shape.Fill.UniformColor)
                if old is None:
                    skipped.append({"shape_id": sid, "range": [start, end], "reason": "无法读取原色，未标记"})
                    continue
                mark_rgb = _smart_color(old, (r, g, b))
                state["object"] = old  # 整对象重复标记：覆盖旧记录，以本次原色为准
                _set_shape_rgb(shape, *mark_rgb)
                marked_chars += len(text)
                modes["object"] += 1
                if mark_rgb != (r, g, b):
                    changed_segments.append(
                        {
                            "shape_id": sid,
                            "range": [start, end],
                            "type": typ,
                            "original_rgb": list(old),
                            "marked_rgb": list(mark_rgb),
                        }
                    )
            applied_items += 1
        if marked_chars == 0:
            raise RuntimeError("没有任何文字被标记（全部无法读取原色）")
        payload = {
            "applied_items": applied_items,
            "marked_chars": marked_chars,
            "modes": modes,
            "changed_segments": changed_segments,
            "skipped": skipped,
            "legend": {k: list(v) for k, v in colors.items()},
        }
        _save_state()
        return payload

    result = conn.safe_call(_do, timeout=120, idempotent=False)
    if result["success"]:
        payload = result["result"]
        mode_note = "（字符级定位）" if payload["modes"].get("char") else "（整对象标记）"
        return ToolResult.ok(
            f"已标记 {payload['marked_chars']} 个字符{mode_note}：红=错别字，蓝=语句不通；原色已记录",
            **payload,
        )
    return ToolResult.fail(result.get("error", "标记失败"))


def restore_marked_colors() -> ToolResult:
    """把之前 mark_text_errors 标记过的文字全部恢复为原色。"""
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接")

    def _do() -> dict[str, Any]:
        _load_state()
        if not _MARKED_STATE:
            return {"restored_chars": 0, "failed": [], "hint": "没有已标记的字符，无需恢复。"}
        doc = conn.app.ActiveDocument
        doc.Unit = _CDR_MILLIMETER
        index = ShapeIndex(doc.ActivePage)
        restored_chars, failed = _restore_marked(doc, index)
        payload = {"restored_chars": restored_chars, "failed": failed}
        _save_state()
        return payload

    result = conn.safe_call(_do, timeout=120, idempotent=False)
    if result["success"]:
        payload = result["result"]
        return ToolResult.ok(f"已恢复 {payload['restored_chars']} 处原色", **payload)
    return ToolResult.fail(result.get("error", "恢复原色失败"))


def fix_text_errors(errors: list[dict[str, Any]]) -> ToolResult:
    """按字符范围替换文字内容（改错别字 / 语序 / 语句）。

    errors: [{shape_id, start, end, replacement}]，start/end 为 0-based 字符索引、
    闭区间 [start, end]，基于 extract_selected_text 返回的 text 位置；
    replacement 为正确文字。
    功能规范：
    - 改字前自动恢复该文档的标记颜色（若有），先回到原色再改内容。
    - 同一对象多处修改按 start 从大到小处理，避免替换后索引漂移。
    - 只改指定范围文字，不删除元素、不保存文档。
    """
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接")

    def _do() -> dict[str, Any]:
        if not errors:
            raise ValueError("errors 不能为空")
        # 改字前自动恢复标记颜色（功能规范）
        _load_state()
        restored = 0
        if _MARKED_STATE:
            doc0 = conn.app.ActiveDocument
            doc0.Unit = _CDR_MILLIMETER
            index0 = ShapeIndex(doc0.ActivePage)
            restored, _ = _restore_marked(doc0, index0)
            _save_state()

        doc = conn.app.ActiveDocument
        doc.Unit = _CDR_MILLIMETER
        index = ShapeIndex(doc.ActivePage)
        applied: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []

        # 同一对象多处修改：按 start 降序处理，避免替换后索引漂移
        for err in sorted(errors, key=lambda e: (str(e.get("shape_id")), -int(e.get("start", 0)))):
            try:
                sid = str(err["shape_id"])
                start = int(err["start"])
                end = int(err["end"])
                replacement = str(err.get("replacement", "")).strip()
            except Exception:
                failed.append({"shape_id": err.get("shape_id"), "reason": "参数格式错误"})
                continue
            if not replacement:
                failed.append({"shape_id": sid, "range": [start, end], "reason": "replacement 不能为空"})
                continue
            try:
                shape = index.resolve(sid)
            except Exception:
                failed.append({"shape_id": sid, "reason": "形状已不存在或不可用"})
                continue
            try:
                text = _get_text_content(shape.Text)
            except Exception:
                failed.append({"shape_id": sid, "reason": "无法读取文字内容"})
                continue
            n = len(text)
            if start < 0 or end >= n or start > end:
                failed.append({"shape_id": sid, "range": [start, end], "reason": "范围越界"})
                continue
            fn = None
            try:
                fn = _story_chars(shape.Text)
            except Exception:
                fn = None
            if fn is None:
                failed.append({"shape_id": sid, "reason": "Characters 不可用，无法定位字符"})
                continue
            start_1 = start + 1
            length = end - start + 1
            try:
                seg = fn(start_1, length)
                old_text = text[start : end + 1]
                # 改字前读该段当前色（此时标记已恢复=原色）
                old_rgb = _read_color_rgb(seg.Fill.UniformColor)
                seg.Text = replacement
                # 替换后重设原色：Characters 替换新字符会继承被替换范围颜色
                if old_rgb is not None:
                    try:
                        _set_range_rgb(fn(start_1, len(replacement)), old_rgb[0], old_rgb[1], old_rgb[2])
                    except Exception:
                        pass
                applied.append(
                    {
                        "shape_id": sid,
                        "range": [start, end],
                        "replaced": old_text,
                        "with": replacement,
                    }
                )
            except Exception:
                failed.append({"shape_id": sid, "range": [start, end], "reason": "替换失败"})

        return {
            "restored_before_fix": restored,
            "applied_items": len(applied),
            "applied": applied,
            "failed": failed,
        }

    result = conn.safe_call(_do, timeout=120, idempotent=False)
    if result["success"]:
        payload = result["result"]
        return ToolResult.ok(
            f"已改 {payload['applied_items']} 处文字（改前恢复标记 {payload['restored_before_fix']} 字符）", **payload
        )
    return ToolResult.fail(result.get("error", "改字失败"))
