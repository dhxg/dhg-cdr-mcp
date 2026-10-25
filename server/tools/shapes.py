"""图形操作工具 — 创建/查找/修改形状，布尔运算，导入素材，对齐/分布/层级/旋转/缩放"""

import os
import time

from core.connection import get_connection
from core.models import ToolResult
from core.coordinates import top_left_to_corel_bounds


def _static_id(shape) -> str:
    """Return CorelDRAW StaticID in the string form expected by tools."""
    return str(shape.StaticID)


def _shape_matches(shape, shape_id: str) -> bool:
    target = str(shape_id)
    try:
        if str(shape.StaticID) == target:
            return True
    except Exception:
        pass
    try:
        return shape.Name == target
    except Exception:
        return False


def _create_shape_range(shapes):
    conn = get_connection()
    shape_range = conn.app.CreateShapeRange()
    for shape in shapes:
        shape_range.Add(shape)
    return shape_range


def _find_shape(shape_id: str):
    """按名称或 StaticID 查找形状。返回 Shape 对象或 None。"""
    conn = get_connection()
    doc = conn.app.ActiveDocument
    if not doc:
        return None
    try:
        page = doc.ActivePage
        shapes = page.Shapes
        # 先尝试按名称查找
        try:
            return shapes(shape_id)
        except Exception:
            pass
        # 遍历匹配
        for s in shapes:
            if _shape_matches(s, shape_id):
                return s
        return None
    except Exception:
        return None


def _shape_info(shape) -> dict:
    """提取形状信息"""
    try:
        info = {
            "name": shape.Name if shape.Name else "",
            "type": shape.Type,
            "width": round(shape.SizeWidth, 2),
            "height": round(shape.SizeHeight, 2),
        }
        try:
            info["center_x"] = round(shape.CenterX, 2)
            info["center_y"] = round(shape.CenterY, 2)
        except Exception:
            pass
        return info
    except Exception:
        return {"name": "", "type": -1}


def create_rectangle(x: float, y: float, width: float, height: float, corner_radius: float = 0, top_left: bool = True) -> ToolResult:
    """创建矩形。x,y 默认位 Top-Left 坐标 (top_y=距离顶部的距离)，支持圆角 (corner_radius)。"""
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接")

    def _create():
        doc = conn.app.ActiveDocument
        page_h = doc.ActivePage.SizeHeight if doc else 297.0
        layer = doc.ActivePage.ActiveLayer
        r = corner_radius if corner_radius > 0 else 0
        if top_left:
            left, bottom, right, top = top_left_to_corel_bounds(x, y, width, height, page_h)
        else:
            left, bottom, right, top = x, y, x + width, y + height
        shape = layer.CreateRectangle(left, bottom, right, top, r, r, r, r)
        shape.Name = f"rect_{shape.StaticID}"
        return {"shape_id": _static_id(shape), **_shape_info(shape), "corner_radius": corner_radius}

    result = conn.safe_call(_create)
    if result["success"]:
        return ToolResult.ok(f"矩形创建成功: {width}×{height}", **result["result"])
    return ToolResult.fail(result.get("error", "创建矩形失败"))


def create_ellipse(cx: float, cy: float, rx: float, ry: float, top_left: bool = True) -> ToolResult:
    """创建椭圆。cx,cy 为中心坐标 (top_left=True 时 cy 为距离顶部的距离)，rx,ry 为 X/Y 半径。"""
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接")

    def _create():
        doc = conn.app.ActiveDocument
        page_h = doc.ActivePage.SizeHeight if doc else 297.0
        layer = doc.ActivePage.ActiveLayer
        corel_cy = (page_h - cy) if top_left else cy
        left = cx - rx
        top = corel_cy + ry
        right = cx + rx
        bottom = corel_cy - ry
        shape = layer.CreateEllipse(left, top, right, bottom)
        shape.Name = f"ellipse_{shape.StaticID}"
        return {"shape_id": _static_id(shape), **_shape_info(shape), "rx": rx, "ry": ry}

    result = conn.safe_call(_create)
    if result["success"]:
        return ToolResult.ok(f"椭圆创建成功: rx={rx}, ry={ry}", **result["result"])
    return ToolResult.fail(result.get("error", "创建椭圆失败"))


def create_line(x1: float, y1: float, x2: float, y2: float, top_left: bool = True) -> ToolResult:
    """创建直线段。y1, y2 默认位 Top-Left 坐标 (距离顶部的距离)。"""
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接")

    def _create():
        doc = conn.app.ActiveDocument
        page_h = doc.ActivePage.SizeHeight if doc else 297.0
        layer = doc.ActivePage.ActiveLayer
        cy1 = (page_h - y1) if top_left else y1
        cy2 = (page_h - y2) if top_left else y2
        shape = layer.CreateLineSegment(x1, cy1, x2, cy2)
        shape.Name = f"line_{shape.StaticID}"
        return {"shape_id": _static_id(shape), **_shape_info(shape), "x1": x1, "y1": y1, "x2": x2, "y2": y2}

    result = conn.safe_call(_create)
    if result["success"]:
        return ToolResult.ok("直线创建成功", **result["result"])
    return ToolResult.fail(result.get("error", "创建直线失败"))



def set_shape_size(shape_id: str, width: float, height: float) -> ToolResult:
    """设置形状的精确尺寸（mm）。"""
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接")

    def _set():
        shape = _find_shape(shape_id)
        if shape is None:
            raise ValueError(f"未找到形状: {shape_id}")
        shape.SetSize(width, height)
        return {"shape_id": shape_id, "width": width, "height": height}

    result = conn.safe_call(_set)
    if result["success"]:
        return ToolResult.ok(f"形状尺寸已设为: {width}×{height} mm", **result["result"])
    return ToolResult.fail(result.get("error", "设置尺寸失败"))


def set_shape_position(shape_id: str, x: float, y: float) -> ToolResult:
    """设置形状的位置（mm）。"""
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接")

    def _set():
        shape = _find_shape(shape_id)
        if shape is None:
            raise ValueError(f"未找到形状: {shape_id}")
        shape.SetPosition(x, y)
        return {"shape_id": shape_id, "x": x, "y": y}

    result = conn.safe_call(_set)
    if result["success"]:
        return ToolResult.ok(f"形状移至: ({x}, {y})", **result["result"])
    return ToolResult.fail(result.get("error", "设置位置失败"))


_BOOLEAN_OPS = {"union": "Weld", "intersect": "Intersect", "subtract": "Trim", "exclude": "Simplify"}


def boolean_operation(shape_ids: str, operation: str) -> ToolResult:
    """对指定形状执行布尔运算。shape_ids 为逗号分隔的 ID 列表，operation 支持 union/intersect/subtract/exclude。"""
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接")

    if operation not in _BOOLEAN_OPS:
        return ToolResult.fail(f"不支持的布尔运算: {operation}，可选: {', '.join(_BOOLEAN_OPS.keys())}")

    def _operate():
        ids = [s.strip() for s in shape_ids.split(",") if s.strip()]
        if len(ids) < 2:
            raise ValueError("至少需要两个形状进行布尔运算")
        selected = []
        for sid in ids:
            shape = _find_shape(sid)
            if shape is None:
                raise ValueError(f"未找到形状: {sid}")
            selected.append(shape)
        selection = _create_shape_range(selected)
        method = getattr(selection, _BOOLEAN_OPS[operation])
        method()
        return {"operation": operation, "input_ids": ids, "result": "success"}

    result = conn.safe_call(_operate)
    if result["success"]:
        return ToolResult.ok(f"布尔运算完成: {operation}", **result["result"])
    return ToolResult.fail(result.get("error", "布尔运算失败"))


def convert_to_curves(shape_id: str) -> ToolResult:
    """将形状转换为曲线（印前必须操作）。"""
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接")

    def _convert():
        shape = _find_shape(shape_id)
        if shape is None:
            raise ValueError(f"未找到形状: {shape_id}")
        shape.ConvertToCurves()
        return {"shape_id": shape_id, "converted": True}

    result = conn.safe_call(_convert)
    if result["success"]:
        return ToolResult.ok(f"已转曲: {shape_id}", **result["result"])
    return ToolResult.fail(result.get("error", "转曲失败"))


def group_shapes(shape_ids: str) -> ToolResult:
    """将多个形状组合为一个群组。shape_ids 为逗号分隔的 ID 列表。"""
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接")

    def _group():
        ids = [s.strip() for s in shape_ids.split(",") if s.strip()]
        if len(ids) < 2:
            raise ValueError("至少需要两个形状才能组合")
        selected = []
        for sid in ids:
            shape = _find_shape(sid)
            if shape is None:
                raise ValueError(f"未找到形状: {sid}")
            selected.append(shape)
        group = _create_shape_range(selected).Group()
        return {"group_id": _static_id(group), "member_count": len(ids), "member_ids": ids}

    result = conn.safe_call(_group)
    if result["success"]:
        return ToolResult.ok(f"已组合 {result['result']['member_count']} 个形状", **result["result"])
    return ToolResult.fail(result.get("error", "组合失败"))


def find_shape_by_name(name: str) -> ToolResult:
    """按名称查找形状。返回形状的 ID、类型、尺寸等。"""
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接")

    def _find():
        shape = _find_shape(name)
        if shape is None:
            return {"found": False, "name": name}
        return {"found": True, **_shape_info(shape), "shape_id": _static_id(shape)}

    result = conn.safe_call(_find)
    if result["success"]:
        if result["result"]["found"]:
            return ToolResult.ok(f"找到形状: {name}", **result["result"])
        return ToolResult.ok(f"未找到形状: {name}", **result["result"])
    return ToolResult.fail(result.get("error", "查找形状失败"))


# ========== P0 排版必需品 ==========

_ALIGN_DIRECTIONS = {"left", "center", "right", "top", "middle", "bottom"}
_Z_ORDER_ACTIONS = {"front", "back", "forward", "backward"}
_CDR_MILLIMETER = 3


def _get_shape_bounds(shape):
    """获取形状的边界信息（位置 + 尺寸），用于对齐/分布计算。返回 dict 或 None。"""
    try:
        x = shape.PositionX
        y = shape.PositionY
        w = shape.SizeWidth
        h = shape.SizeHeight
        return {
            "x": x, "y": y, "w": w, "h": h,
            "center_x": x + w / 2, "center_y": y + h / 2,
            "right": x + w, "bottom": y + h,
        }
    except Exception:
        return None


def _get_page_size(doc):
    """获取当前页面的宽度和高度（mm）。"""
    try:
        doc.Unit = _CDR_MILLIMETER
        page = doc.ActivePage
        return page.SizeWidth, page.SizeHeight
    except Exception:
        return 0, 0


def align_shapes(shape_ids: str, alignment: str, reference: str = "selection") -> ToolResult:
    """将多个形状对齐。alignment: left/center/right/top/middle/bottom。
    reference='selection' 在形状间对齐，reference='page' 对齐到页面边缘。
    shape_ids 为逗号分隔的形状 ID 或名称列表。"""
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接")

    alignment = alignment.lower()
    if alignment not in _ALIGN_DIRECTIONS:
        return ToolResult.fail(f"不支持的对齐方式: {alignment}，可选: {', '.join(sorted(_ALIGN_DIRECTIONS))}")

    def _align():
        ids = [s.strip() for s in shape_ids.split(",") if s.strip()]
        if not ids:
            raise ValueError("请提供至少一个形状 ID")

        shapes = []
        bounds = []
        for sid in ids:
            shape = _find_shape(sid)
            if shape is None:
                raise ValueError(f"未找到形状: {sid}")
            b = _get_shape_bounds(shape)
            if b is None:
                raise ValueError(f"无法读取形状 {sid} 的位置信息")
            shapes.append(shape)
            bounds.append(b)

        if reference == "page":
            page_w, page_h = _get_page_size(conn.app.ActiveDocument)
            for shape, b in zip(shapes, bounds):
                if alignment == "left":
                    shape.SetPosition(0, b["y"])
                elif alignment == "center":
                    new_x = (page_w - b["w"]) / 2
                    shape.SetPosition(new_x, b["y"])
                elif alignment == "right":
                    shape.SetPosition(page_w - b["w"], b["y"])
                elif alignment == "top":
                    shape.SetPosition(b["x"], 0)
                elif alignment == "middle":
                    new_y = (page_h - b["h"]) / 2
                    shape.SetPosition(b["x"], new_y)
                elif alignment == "bottom":
                    shape.SetPosition(b["x"], page_h - b["h"])
        else:
            # selection 模式：以第一个形状为基准对齐其他形状
            if len(shapes) < 2:
                raise ValueError("selection 模式至少需要两个形状（或使用 reference='page'）")
            ref_bounds = bounds[0]
            for shape, b in zip(shapes[1:], bounds[1:]):
                if alignment == "left":
                    shape.SetPosition(ref_bounds["x"], b["y"])
                elif alignment == "center":
                    new_x = ref_bounds["center_x"] - b["w"] / 2
                    shape.SetPosition(new_x, b["y"])
                elif alignment == "right":
                    shape.SetPosition(ref_bounds["right"] - b["w"], b["y"])
                elif alignment == "top":
                    shape.SetPosition(b["x"], ref_bounds["y"])
                elif alignment == "middle":
                    new_y = ref_bounds["center_y"] - b["h"] / 2
                    shape.SetPosition(b["x"], new_y)
                elif alignment == "bottom":
                    shape.SetPosition(b["x"], ref_bounds["bottom"] - b["h"])

        return {"shape_count": len(shapes), "alignment": alignment, "reference": reference}

    result = conn.safe_call(_align)
    if result["success"]:
        return ToolResult.ok(f"对齐完成: {alignment} ({reference})", **result["result"])
    return ToolResult.fail(result.get("error", "对齐失败"))


def distribute_shapes(shape_ids: str, direction: str = "horizontal", spacing: float = 0) -> ToolResult:
    """将多个形状等距分布。direction: horizontal/vertical。spacing>0 时使用固定间距，
    否则在最小和最大边界之间均匀分布。shape_ids 为逗号分隔。"""
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接")

    direction = direction.lower()
    if direction not in ("horizontal", "vertical"):
        return ToolResult.fail("direction 仅支持 'horizontal' 或 'vertical'")

    def _distribute():
        ids = [s.strip() for s in shape_ids.split(",") if s.strip()]
        if len(ids) < 3:
            raise ValueError("分布至少需要三个形状")

        shapes = []
        bounds = []
        for sid in ids:
            shape = _find_shape(sid)
            if shape is None:
                raise ValueError(f"未找到形状: {sid}")
            b = _get_shape_bounds(shape)
            if b is None:
                raise ValueError(f"无法读取形状 {sid} 的位置信息")
            shapes.append(shape)
            bounds.append(b)

        if direction == "horizontal":
            # 按 X 排序
            pairs = sorted(zip(shapes, bounds), key=lambda p: p[1]["x"])
            if spacing > 0:
                # 固定间距，以第一个为起点
                ref_x = pairs[0][1]["x"]
                for i, (shape, b) in enumerate(pairs):
                    new_x = ref_x + i * spacing
                    shape.SetPosition(new_x, b["y"])
            else:
                # 均匀分布：总跨度 / (n-1)
                min_x = pairs[0][1]["x"]
                max_x = pairs[-1][1]["x"] + pairs[-1][1]["w"]
                total_span = max_x - min_x
                if len(pairs) > 1:
                    step = total_span / (len(pairs) - 1)
                else:
                    step = 0
                for i, (shape, b) in enumerate(pairs[1:-1]):
                    target_center_x = min_x + (i + 1) * step - b["w"] / 2
                    shape.SetPosition(target_center_x, b["y"])
        else:
            # 按 Y 排序
            pairs = sorted(zip(shapes, bounds), key=lambda p: p[1]["y"])
            if spacing > 0:
                ref_y = pairs[0][1]["y"]
                for i, (shape, b) in enumerate(pairs):
                    new_y = ref_y + i * spacing
                    shape.SetPosition(b["x"], new_y)
            else:
                min_y = pairs[0][1]["y"]
                max_y = pairs[-1][1]["y"] + pairs[-1][1]["h"]
                total_span = max_y - min_y
                if len(pairs) > 1:
                    step = total_span / (len(pairs) - 1)
                else:
                    step = 0
                for i, (shape, b) in enumerate(pairs[1:-1]):
                    target_center_y = min_y + (i + 1) * step - b["h"] / 2
                    shape.SetPosition(b["x"], target_center_y)

        return {"shape_count": len(shapes), "direction": direction, "spacing": spacing}

    result = conn.safe_call(_distribute)
    if result["success"]:
        return ToolResult.ok(f"分布完成: {direction} ({result['result']['shape_count']}个形状)", **result["result"])
    return ToolResult.fail(result.get("error", "分布失败"))


def set_z_order(shape_id: str, action: str) -> ToolResult:
    """控制形状的层级顺序。action: front(置顶)/back(置底)/forward(上移一层)/backward(下移一层)。"""
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接")

    action = action.lower()
    if action not in _Z_ORDER_ACTIONS:
        return ToolResult.fail(f"不支持的层级操作: {action}，可选: {', '.join(sorted(_Z_ORDER_ACTIONS))}")

    def _order():
        shape = _find_shape(shape_id)
        if shape is None:
            raise ValueError(f"未找到形状: {shape_id}")
        if action == "front":
            shape.OrderToFront()
        elif action == "back":
            shape.OrderToBack()
        elif action == "forward":
            shape.OrderForwardOne()
        elif action == "backward":
            shape.OrderBackOne()
        return {"shape_id": shape_id, "action": action}

    result = conn.safe_call(_order)
    if result["success"]:
        action_names = {"front": "置顶", "back": "置底", "forward": "上移一层", "backward": "下移一层"}
        return ToolResult.ok(f"层级调整: {shape_id} → {action_names.get(action, action)}", **result["result"])
    return ToolResult.fail(result.get("error", "层级操作失败"))


def delete_shape(shape_id: str) -> ToolResult:
    """删除指定的形状。"""
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接")

    def _delete():
        shape = _find_shape(shape_id)
        if shape is None:
            raise ValueError(f"未找到形状: {shape_id}")
        name = shape.Name or shape_id
        shape.Delete()
        return {"shape_id": shape_id, "name": name, "deleted": True}

    result = conn.safe_call(_delete)
    if result["success"]:
        return ToolResult.ok(f"已删除: {result['result']['name']}", **result["result"])
    return ToolResult.fail(result.get("error", "删除形状失败"))


def rotate_shape(shape_id: str, angle: float, center_x: float = 0, center_y: float = 0) -> ToolResult:
    """旋转形状。angle 为旋转角度（度，正值逆时针），center_x/center_y 为旋转中心（0=形状自身中心）。"""
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接")

    def _rotate():
        shape = _find_shape(shape_id)
        if shape is None:
            raise ValueError(f"未找到形状: {shape_id}")
        old_angle = 0.0
        try:
            old_angle = shape.RotationAngle
        except Exception:
            pass
        if center_x != 0 or center_y != 0:
            try:
                # 尝试设置旋转中心（CorelDRAW X6+ 支持）
                shape.RotationCenterX = center_x
                shape.RotationCenterY = center_y
            except Exception:
                pass
        shape.RotationAngle = angle
        return {"shape_id": shape_id, "angle": angle, "old_angle": round(old_angle, 2)}

    result = conn.safe_call(_rotate)
    if result["success"]:
        return ToolResult.ok(f"形状已旋转: {shape_id} → {angle}°", **result["result"])
    return ToolResult.fail(result.get("error", "旋转失败"))


def ungroup_shapes(shape_id: str, recursive: bool = False) -> ToolResult:
    """取消群组。shape_id 为群组形状的 ID；recursive=True 时递归取消全部子群组。"""
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接")

    def _ungroup():
        shape = _find_shape(shape_id)
        if shape is None:
            raise ValueError(f"未找到形状: {shape_id}")
        # 检查是否为群组
        try:
            is_group = shape.Type == 7  # cdrGroupShape
        except Exception:
            is_group = False
        if not is_group:
            # duck-type：尝试读取子形状
            try:
                _ = shape.Shapes
                is_group = True
            except Exception:
                pass
        if not is_group:
            raise ValueError(f"形状 {shape_id} 不是一个群组")

        if recursive:
            try:
                shape.UngroupAll()
            except Exception:
                shape.Ungroup()
        else:
            shape.Ungroup()
        return {"shape_id": shape_id, "recursive": recursive, "ungrouped": True}

    result = conn.safe_call(_ungroup)
    if result["success"]:
        detail = "递归取消群组" if recursive else "取消群组"
        return ToolResult.ok(f"{detail}: {shape_id}", **result["result"])
    return ToolResult.fail(result.get("error", "取消群组失败"))


def scale_shape(shape_id: str, scale_x: float, scale_y: float = 0, keep_proportion: bool = False) -> ToolResult:
    """等比/非等比缩放形状。scale_x 为 X 方向缩放因子（1.0=原尺寸，2.0=放大一倍）。
    scale_y 为 Y 方向缩放因子，为 0 时与 scale_x 相同（等比）。
    keep_proportion=True 时忽略 scale_y 强制等比缩放。"""
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接")

    if scale_x <= 0:
        return ToolResult.fail(f"缩放因子必须大于 0，当前 scale_x={scale_x}")

    scale_y = scale_y if scale_y > 0 else scale_x

    def _scale():
        shape = _find_shape(shape_id)
        if shape is None:
            raise ValueError(f"未找到形状: {shape_id}")
        old_w = shape.SizeWidth
        old_h = shape.SizeHeight
        new_w = old_w * scale_x
        new_h = old_h * (scale_x if keep_proportion else scale_y)
        # 保持中心点不变缩放
        cx = shape.PositionX + old_w / 2
        cy = shape.PositionY + old_h / 2
        shape.SetSize(new_w, new_h)
        shape.SetPosition(cx - new_w / 2, cy - new_h / 2)
        return {
            "shape_id": shape_id,
            "scale_x": scale_x,
            "scale_y": scale_x if keep_proportion else scale_y,
            "old_size": {"width": round(old_w, 2), "height": round(old_h, 2)},
            "new_size": {"width": round(new_w, 2), "height": round(new_h, 2)},
        }

    result = conn.safe_call(_scale)
    if result["success"]:
        r = result["result"]
        return ToolResult.ok(
            f"缩放: {r['old_size']['width']}×{r['old_size']['height']} "
            f"→ {r['new_size']['width']}×{r['new_size']['height']}",
            **r,
        )
    return ToolResult.fail(result.get("error", "缩放失败"))


# ========== P1 增强工具 ==========


def select_shapes(by_type: str = "", by_layer: str = "", by_name_pattern: str = "") -> ToolResult:
    """按条件选择形状并返回匹配的形状列表。
    by_type: rectangle/ellipse/curve/text/bitmap/group 等
    by_layer: 图层名称
    by_name_pattern: 名称包含此字符串的形状

    不修改 CorelDRAW 中的实际选中状态，只返回匹配列表供其他工具使用。"""
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接")

    _TYPE_MAP = {
        "rectangle": 1, "ellipse": 2, "curve": 4, "text": 3,
        "bitmap": 6, "group": 7, "line": 1, "polygon": 5,
    }

    def _select():
        doc = conn.app.ActiveDocument
        if not doc:
            raise RuntimeError("没有打开的文档")
        page = doc.ActivePage
        matched = []

        for s in page.Shapes:
            # 按图层过滤
            if by_layer:
                try:
                    if s.Layer.Name != by_layer:
                        continue
                except Exception:
                    continue

            # 按类型过滤
            if by_type:
                type_lower = by_type.lower()
                expected = _TYPE_MAP.get(type_lower, -1)
                try:
                    if expected >= 0 and s.Type != expected:
                        continue
                except Exception:
                    continue

            # 按名称模式过滤
            if by_name_pattern:
                try:
                    name = s.Name or ""
                    if by_name_pattern.lower() not in name.lower():
                        continue
                except Exception:
                    continue

            # 提取形状信息
            info = _shape_info(s)
            info["shape_id"] = ""
            try:
                info["shape_id"] = str(s.StaticID)
            except Exception:
                pass
            try:
                info["layer"] = s.Layer.Name
            except Exception:
                info["layer"] = ""
            matched.append(info)

        return {"count": len(matched), "shapes": matched, "criteria": {
            "by_type": by_type, "by_layer": by_layer, "by_name_pattern": by_name_pattern,
        }}

    result = conn.safe_call(_select)
    if result["success"]:
        r = result["result"]
        criteria_parts = []
        if by_type:
            criteria_parts.append(f"类型={by_type}")
        if by_layer:
            criteria_parts.append(f"图层={by_layer}")
        if by_name_pattern:
            criteria_parts.append(f"名称包含'{by_name_pattern}'")
        return ToolResult.ok(f"找到 {r['count']} 个匹配形状 ({', '.join(criteria_parts)})", **r)
    return ToolResult.fail(result.get("error", "选择形状失败"))


def powerclip(content_shape_id: str, container_shape_id: str) -> ToolResult:
    """将 content 形状放入 container 形状内（PowerClip）。
    类似于 AI 的剪切蒙版，用于将图案/文字限制在特定区域内。"""
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接")

    def _clip():
        content = _find_shape(content_shape_id)
        if content is None:
            raise ValueError(f"未找到内容形状: {content_shape_id}")
        container = _find_shape(container_shape_id)
        if container is None:
            raise ValueError(f"未找到容器形状: {container_shape_id}")

        placed = False
        for method in (
            lambda: content.AddToPowerClip(container, -2),
            lambda: _create_shape_range([content]).AddToPowerClip(container, -2),
            lambda: content.CreatePowerClip(container),
            lambda: container.PowerClip.Place(content),
            lambda: conn.app.ActiveDocument.CreatePowerClip(content, container),
        ):
            try:
                method()
                placed = True
                break
            except Exception:
                continue

        if not placed:
            raise RuntimeError("当前 CorelDRAW 版本不支持已知的 PowerClip API")

        return {
            "content_id": content_shape_id,
            "container_id": container_shape_id,
            "powerclip_created": True,
        }

    result = conn.safe_call(_clip)
    if result["success"]:
        return ToolResult.ok(
            f"PowerClip: {content_shape_id} → {container_shape_id}",
            **result["result"],
        )
    return ToolResult.fail(result.get("error", "PowerClip 操作失败"))


# ========== 批量置入图片（PowerClip） ==========

_FIT_MODES = {
    "fill": "按比例填充（填满容器、不变形、超出部分裁切，图完整可编辑）",
    "fit": "按比例拟合（全图可见、不变形、可能留白）",
    "stretch": "拉伸填充（填满容器、可能变形）",
    "center": "居中（原始大小、不缩放）",
}


def _import_image_shape(layer, page, image_path):
    """用 layer.Import 导入文件（保留透明通道），通过前后 ID 差集定位新位图。"""
    before = set(int(s.StaticID) for s in page.Shapes)
    layer.Import(os.path.abspath(image_path), 0, None)
    new = None
    for s in page.Shapes:
        if int(s.StaticID) not in before and int(s.Type) == 5:
            new = s
    return new


def _fit_powerclip_contents(container, fit_mode: str):
    """对 PowerClip 容器内的内容做适配。内容始终完整保留（不裁剪），可进容器编辑。"""
    inner = container.PowerClip.Shapes.Item(1)
    cw, ch = container.SizeWidth, container.SizeHeight
    iw, ih = inner.SizeWidth, inner.SizeHeight
    if fit_mode == "fill":
        k = max(cw / iw, ch / ih)
        inner.SetSize(iw * k, ih * k)
    elif fit_mode == "fit":
        k = min(cw / iw, ch / ih)
        inner.SetSize(iw * k, ih * k)
    elif fit_mode == "stretch":
        inner.SetSize(cw, ch)
    # center：不缩放，仅居中
    inner.CenterX = container.CenterX
    inner.CenterY = container.CenterY
    return round(inner.SizeWidth, 2), round(inner.SizeHeight, 2)


def _place_images_into_containers(norm, fit_mode: str):
    """把 [(container_id, image_path)] 批量导入并 PowerClip 进对应容器（在 COM 线程内执行）。

    - 预处理：等比降采样、保留透明通道、写入 300 DPI
    - 容器找不到时，会在所有 PowerClip 内部查找（支持替换框内已有图）
    - 返回汇总字典（placed / fit_mode / fit_description / items）
    """
    from PIL import Image
    conn = get_connection()
    doc = conn.app.ActiveDocument
    doc.Unit = _CDR_MILLIMETER
    page = doc.ActivePage
    layer = doc.ActiveLayer
    results = []
    for cid, ip in norm:
        container = _find_shape(cid)
        if container is None:
            container, _ = _find_shape_in_powerclip(cid)
        if container is None:
            raise ValueError(f"未找到容器形状: {cid}")
        # 预处理：等比降采样、保留透明通道、写入 300 DPI
        prepared, _, _, _ = _normalize_pil(
            Image.open(ip), max_long_edge=2000, dpi=300
        )
        try:
            pic = _import_image_shape(layer, page, prepared)
            if pic is None:
                raise RuntimeError(f"图片导入失败: {ip}")
            pic.AddToPowerClip(container)
            iw, ih = _fit_powerclip_contents(container, fit_mode)
            results.append({
                "container_id": cid,
                "inner_id": str(container.PowerClip.Shapes.Item(1).StaticID),
                "inner_width_mm": iw,
                "inner_height_mm": ih,
                "fit_mode": fit_mode,
            })
        finally:
            try:
                os.remove(prepared)
            except Exception:
                pass
    return {
        "placed": len(results),
        "fit_mode": fit_mode,
        "fit_description": _FIT_MODES[fit_mode],
        "items": results,
    }


def batch_place_images(items, fit_mode: str = "fill") -> ToolResult:
    """批量把本地图片导入并 PowerClip 进指定容器（如选中的方框/图形）。

    典型流程：用户在 CDR 选中 N 个框 → get_selection 拿到框 ID → 按关键词搜图下载 →
    调用本工具一次置入，每个框一张。

    Args:
        items: 列表，每项 {"container_id": 容器 shape_id, "image_path": 本地图片绝对路径}，
            与容器一一对应。
        fit_mode: 内容适配方式，默认 fill（按比例填充），可选 fit / stretch / center。
    """
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接")

    fit_mode = (fit_mode or "fill").lower()
    if fit_mode not in _FIT_MODES:
        fit_mode = "fill"

    norm = []
    for it in items:
        cid = it.get("container_id")
        ip = it.get("image_path")
        if not cid or not ip:
            return ToolResult.fail("每个 item 必须包含 container_id 和 image_path")
        if not os.path.isfile(ip):
            return ToolResult.fail(f"图片不存在: {ip}")
        norm.append((str(cid), ip))

    if not norm:
        return ToolResult.fail("items 为空，没有要置入的图片")

    result = conn.safe_call(lambda: _place_images_into_containers(norm, fit_mode), timeout=180)
    if result["success"]:
        return ToolResult.ok(
            f"已置入 {result['result']['placed']} 个图片：{_FIT_MODES[fit_mode]}",
            **result["result"],
        )
    return ToolResult.fail(result.get("error", "批量置入失败"))


# ========== 图片导入与替换 ==========

_CDR_MILLIMETER = 3


def _collect_occupied(doc, page=None):
    """收集所有可编辑层上现有元素的包围盒（含页面外粘贴板区域）。
    统一规范成 (minX, minY, maxX, maxY)。
    注意 CDR 坐标原点在页面左下角、Y 轴向上：BottomY 小、TopY 大。
    用 page.Layers 遍历（该版本 doc.Layers 不可用）。"""
    boxes = []
    if page is None:
        try:
            page = doc.ActivePage
        except Exception:
            page = None
    if page is None:
        return boxes
    for layer in page.Layers:
        try:
            for s in layer.Shapes:
                boxes.append((s.LeftX, s.BottomY, s.RightX, s.TopY))
        except Exception:
            continue
    return boxes


def _boxes_overlap(a, b, gap=0.0):
    # a, b 均为 (minX, minY, maxX, maxY)
    return not (a[2] + gap <= b[0] or b[2] + gap <= a[0]
                or a[3] + gap <= b[1] or b[3] + gap <= a[1])


def _find_free_slot(doc, page, w: float, h: float, gap: float = 8.0):
    """为一个以左上角定位、尺寸 w×h 的元素找空位。
    优先页面内；页面内放不下或已占满时，自动放到页面右侧、下侧的粘贴板区域。
    返回 (leftX, topY) 左上角坐标（CDR 里 TopY 是上边、值较大）。"""
    occupied = _collect_occupied(doc, page)

    def free(x, y_top):
        box = (x, y_top - h, x + w, y_top)  # 规范化为 minX,minY,maxX,maxY
        return not any(_boxes_overlap(box, b, gap) for b in occupied)

    left0 = page.LeftX; top0 = page.TopY
    right0 = page.RightX; bottom0 = page.BottomY

    # 0) 页面完全为空：直接放到页面正中心（水平+垂直居中）
    if len(occupied) == 0:
        page_cx = (left0 + right0) / 2
        page_cy = (bottom0 + top0) / 2
        return page_cx - w / 2, page_cy + h / 2

    # 页面内留安全边距，确保元素完整可见（不贴边、不被页面边缘切掉）
    pad = 3.0
    left = left0 + pad
    top = top0 - pad
    right = right0 - pad
    bottom = bottom0 + pad

    # 1) 页面内：左上角（页面没有内容时，第一个元素直接放这里）
    if free(left, top):
        return left, top
    # 2) 页面内：现有元素右侧 / 下侧（顺延）
    for (bx, bymin, bx2, bymax) in list(occupied):
        # 右侧：锚点 x=bx2+gap，上边对齐该元素上边 bymax
        if bx2 + gap + w <= right0 and bymax <= top0 and free(bx2 + gap, bymax):
            return bx2 + gap, bymax
        # 下侧：锚点 x=bx，上边=该元素下边 bymin-gap
        if bymin - gap - h >= bottom0 and free(bx, bymin - gap):
            return bx, bymin - gap
    # 3) 页面右侧（粘贴板）：从页面顶部往下（y 递减）顺延
    rx = right0 + gap
    ry_top = top0
    for _ in range(500):
        if free(rx, ry_top):
            return rx, ry_top
        ry_top -= h + gap
    # 4) 页面下方（粘贴板）：从页面左边往右（x 递增）顺延
    bx = left0
    by_top = bottom0 - gap
    for _ in range(500):
        if free(bx, by_top):
            return bx, by_top
        bx += w + gap
    return left0, bottom0 - gap - h


def _normalize_pil(img, max_long_edge: int = 2000, dpi: int = 300):
    """对 PIL 图像等比降采样并写入 DPI，存为临时 PNG。
    返回 (临时文件路径, 降采样比例, 图宽px, 图高px)。"""
    import tempfile
    from PIL import Image
    iw, ih = img.size
    scale = 1.0
    if max(iw, ih) > max_long_edge:
        scale = max_long_edge / max(iw, ih)
        img = img.resize((max(1, int(iw * scale)), max(1, int(ih * scale))), Image.LANCZOS)
    if img.mode == 'P':
        img = img.convert('RGBA')
    fd, tmp = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    img.save(tmp, dpi=(dpi, dpi))
    return tmp, scale, img.size[0], img.size[1]


def _prepare_image_for_import(image_path: str, max_long_edge: int = 2000, dpi: int = 300):
    """导入前预处理：等比降采样到合理像素并写入 DPI，避免无 DPI 的超大图
    导入后尺寸过大（可达1米）、PowerTRACE 描摹过慢导致连接器超时。

    返回 (处理后的临时文件路径, 降采样比例, 图宽px, 图高px)。
    """
    from PIL import Image
    return _normalize_pil(Image.open(image_path), max_long_edge=max_long_edge, dpi=dpi)


def _copy_image_to_clipboard(image_path: str):
    """把图片文件复制到Windows剪贴板（CF_DIB格式）。
    透明背景统一处理为白色，避免灰色杂边。"""
    import io
    import pythoncom
    import win32clipboard
    from PIL import Image

    pythoncom.CoInitialize()

    img = Image.open(image_path)
    # 如果有透明通道，合成到白色背景上，避免剪贴板BMP产生灰边
    if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
        img = img.convert('RGBA')
        background = Image.new('RGB', img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])  # 用alpha通道做mask
        img = background

    output = io.BytesIO()
    img.save(output, 'BMP')
    data = output.getvalue()[14:]
    output.close()

    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
    win32clipboard.CloseClipboard()


def _find_shape_in_powerclip(shape_id: str):
    """在所有PowerClip容器内部查找形状。返回 (shape, container) 或 (None, None)。"""
    conn = get_connection()
    doc = conn.app.ActiveDocument
    if not doc:
        return None, None
    page = doc.ActivePage
    for s in page.Shapes:
        try:
            pc = s.PowerClip
            if pc and pc.Shapes.Count > 0:
                for i in range(1, pc.Shapes.Count + 1):
                    inner = pc.Shapes.Item(i)
                    if _shape_matches(inner, shape_id):
                        return inner, s
        except Exception:
            continue
    return None, None


def import_bitmap(
    image_path: str,
    x_mm: float = -1.0,
    y_mm: float = -1.0,
    width_mm: float = 0.0,
) -> ToolResult:
    """把本地图片文件导入（放置）到当前 CDR 画布，返回生成的位图形状 ID。
    用剪贴板粘贴方式导入，单张图片稳定可靠。

    Args:
        image_path: 图片文件的绝对路径。
        x_mm: 放置位置左上角 X（mm），默认 -1 放页面左上边距处。
        y_mm: 放置位置左上角 Y（mm），默认 -1 放页面左上边距处。
        width_mm: 指定导入宽度（mm），高度按原始比例自动算；默认 0 保持原尺寸。
    """
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接")

    if not os.path.isfile(image_path):
        return ToolResult.fail(f"图片不存在: {image_path}")

    # 降采样到最长边 2000px + 写入 300 DPI（PIL 操作，在 COM 线程外）
    # 导入后物理尺寸 = 降采样像素 / 300 DPI，最长边 ≤ 169mm，保证描摹不崩
    prepared, dscale, pw_px, ph_px = _prepare_image_for_import(image_path)
    aspect = ph_px / pw_px
    full_w = pw_px / 300.0 * 25.4
    full_h = ph_px / 300.0 * 25.4

    def _do():
        import time
        doc = conn.app.ActiveDocument
        doc.Unit = _CDR_MILLIMETER
        layer = doc.ActiveLayer
        page = doc.ActivePage

        # 最终尺寸
        if width_mm and width_mm > 0:
            target_w = float(width_mm)
            target_h = float(width_mm) * aspect
        else:
            target_w = full_w
            target_h = full_h

        # paste 前先找空位（避免把刚粘贴的新形状算进占用）
        use_xy = (x_mm and x_mm >= 0 and y_mm and y_mm >= 0)
        if not use_xy:
            sx, sy = _find_free_slot(doc, page, target_w, target_h)

        _copy_image_to_clipboard(prepared)
        time.sleep(0.3)
        new_shape = layer.Paste()
        new_shape.SizeWidth = target_w
        new_shape.SizeHeight = target_h
        if use_xy:
            new_shape.LeftX = float(x_mm)
            new_shape.TopY = float(y_mm)
        else:
            new_shape.LeftX = sx
            new_shape.TopY = sy

        on_page = bool(new_shape.LeftX >= page.LeftX - 1 and new_shape.RightX <= page.RightX + 1
                       and new_shape.TopY <= page.TopY + 1 and new_shape.BottomY >= page.BottomY - 1)
        result = {
            "imported": True,
            "shape_id": str(new_shape.StaticID),
            "width_mm": round(new_shape.SizeWidth, 2),
            "height_mm": round(new_shape.SizeHeight, 2),
            "on_page": on_page,
        }
        try:
            os.remove(prepared)
        except Exception:
            pass
        return result

    result = conn.safe_call(_do, timeout=90)
    if result["success"]:
        return ToolResult.ok("图片已导入画布", **result["result"])
    return ToolResult.fail(result.get("error", "导入图片失败"))


def _unlock_locked_recursive(shape, counter: list) -> None:
    """递归解锁对象（等价于在对象上右键→解锁）：shape 被锁定就解锁；
    然后无论 shape 是什么类型，都尝试深入它的 .Shapes（群组、嵌套子群组、PowerClip
    等容器都有 Shapes 集合），把内部锁定的子对象一并解锁，不解散群组。"""
    # 1) 先解锁自身（锁定时可能无法访问内部，所以先解锁）
    try:
        if bool(shape.Locked):
            shape.Locked = False
            counter[0] += 1
    except Exception:
        pass
    # 2) 深入内部容器（不限定 Type=7，任何含 Shapes 的对象都遍历）
    try:
        subs = shape.Shapes
        if subs is not None and int(subs.Count) > 0:
            for sub in subs:
                _unlock_locked_recursive(sub, counter)
    except Exception:
        pass


def _collect_locked_ids_recursive(shape, id_set: set) -> None:
    """递归收集一个形状及其内部所有锁定对象的 StaticID。"""
    try:
        if bool(shape.Locked):
            id_set.add(int(shape.StaticID))
    except Exception:
        pass
    try:
        subs = shape.Shapes
        if subs is not None:
            for sub in subs:
                _collect_locked_ids_recursive(sub, id_set)
    except Exception:
        pass


def _collect_page_locked_ids(page) -> set:
    """收集当前页面所有图层、所有层级里已存在的锁定对象 ID。"""
    ids = set()
    try:
        for layer in page.Layers:
            try:
                for s in layer.Shapes:
                    _collect_locked_ids_recursive(s, ids)
            except Exception:
                continue
    except Exception:
        pass
    return ids


def _unlock_new_locked_recursive(shape, pre_locked: set, counter: list) -> None:
    """递归解锁"新出现"的锁定对象（StaticID 不在 pre_locked 里的），
    导入前就锁定的对象保持不动。"""
    try:
        sid = int(shape.StaticID)
        if bool(shape.Locked) and sid not in pre_locked:
            shape.Locked = False
            counter[0] += 1
    except Exception:
        pass
    try:
        subs = shape.Shapes
        if subs is not None:
            for sub in subs:
                _unlock_new_locked_recursive(sub, pre_locked, counter)
    except Exception:
        pass


def _import_vector_file(file_path, x_mm: float, y_mm: float, kind: str) -> ToolResult:
    """把本地矢量文件（SVG / PDF）导入当前 CDR 画布，保持矢量可编辑。
    自动处理图层锁、对象锁（只解本次导入的），并按规则定位（指定坐标/空白页居中/找空位）。"""
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接")

    def _do():
        doc = conn.app.ActiveDocument
        doc.Unit = _CDR_MILLIMETER
        page = doc.ActivePage
        layer = doc.ActiveLayer

        # 当前图层被锁定时自动解锁
        unlocked = False
        try:
            if not bool(layer.Editable):
                layer.Editable = True
                unlocked = True
        except Exception:
            pass

        # 导入前：全页面（所有图层、所有层级）记录已存在的锁定对象
        pre_locked = _collect_page_locked_ids(page)
        # 导入前页面是否为空（用于决定空白页是否居中）
        empty_before = len(_collect_occupied(doc, page)) == 0

        # 明确指定导入过滤器（AutoSense 对 PDF 会触发选项框/失败）
        ext = os.path.splitext(file_path)[1].lower()
        filter_id = {".pdf": 1333, ".svg": 1345, ".svgz": 1347}.get(ext, 0)

        before = set(int(s.StaticID) for s in page.Shapes)
        layer.Import(os.path.abspath(file_path), filter_id, None)

        new_id_set = set(
            int(s.StaticID) for s in page.Shapes if int(s.StaticID) not in before
        )
        if not new_id_set:
            raise RuntimeError(f"{kind} 导入后未检测到新对象，可能被过滤器拦截或文件无效。")
        new_shapes = [s for s in page.Shapes if int(s.StaticID) in new_id_set]

        # 自动解锁：扫描全页面所有图层、所有层级，只解锁"新出现"的锁定对象
        # （导入前就锁定的对象保持不动），覆盖深层群组/其他图层，避免漏解锁
        unlock_counter = [0]
        for layer2 in page.Layers:
            try:
                for s in layer2.Shapes:
                    _unlock_new_locked_recursive(s, pre_locked, unlock_counter)
            except Exception:
                continue
        unlocked_objects = unlock_counter[0]

        rng = conn.app.CreateShapeRange()
        for s in new_shapes:
            rng.Add(s)
        w = float(rng.SizeWidth)
        h = float(rng.SizeHeight)

        use_xy = (x_mm is not None and x_mm >= 0 and y_mm is not None and y_mm >= 0)
        if use_xy:
            dx = float(x_mm) - float(rng.LeftX)
            dy = float(y_mm) - float(rng.TopY)
            rng.Move(dx, dy)
            left, top = float(x_mm), float(y_mm)
        elif empty_before:
            # 导入前页面为空：放到页面正中心（水平+垂直居中）
            page_cx = (float(page.LeftX) + float(page.RightX)) / 2
            page_cy = (float(page.BottomY) + float(page.TopY)) / 2
            target_left = page_cx - w / 2
            target_top = page_cy + h / 2
            dx = target_left - float(rng.LeftX)
            dy = target_top - float(rng.TopY)
            rng.Move(dx, dy)
            left, top = target_left, target_top
        else:
            sx, sy = _find_free_slot(doc, page, w, h)
            dx = sx - float(rng.LeftX)
            dy = sy - float(rng.TopY)
            rng.Move(dx, dy)
            left, top = sx, sy

        return {
            "imported": True,
            "shape_id": str(new_shapes[0].StaticID),
            "shape_ids": [str(i) for i in sorted(new_id_set)],
            "shape_count": len(new_shapes),
            "left_x_mm": round(left, 2),
            "top_y_mm": round(top, 2),
            "width_mm": round(w, 2),
            "height_mm": round(h, 2),
            "layer_was_unlocked": unlocked,
            "unlocked_object_count": unlocked_objects,
        }

    result = conn.safe_call(_do, timeout=90, idempotent=False)
    if result["success"]:
        return ToolResult.ok(f"{kind} 已导入画布（保持矢量可编辑）", **result["result"])
    return ToolResult.fail(result.get("error", f"导入 {kind} 失败"))


def import_svg(
    svg_path: str,
    x_mm: float = -1.0,
    y_mm: float = -1.0,
) -> ToolResult:
    """把本地 SVG 矢量文件导入（放置）到当前 CDR 画布，保持为可编辑矢量（通常是一个群组，
    也可能是多个散开对象）。图层被锁定或对象被锁定时会自动解锁。

    Args:
        svg_path: SVG 文件的绝对路径。
        x_mm: 放置位置左上角 X（mm），默认 -1 自动定位（空白页居中/找空位）。
        y_mm: 放置位置左上角 Y（mm，上边），默认 -1 自动定位。
    """
    if not os.path.isfile(svg_path):
        return ToolResult.fail(f"SVG 文件不存在: {svg_path}")
    if not str(svg_path).lower().endswith(".svg"):
        return ToolResult.fail("只支持 .svg 矢量文件")
    return _import_vector_file(svg_path, x_mm, y_mm, "SVG")


def replace_bitmap(shape_id: str, new_image_path: str) -> ToolResult:
    """用新图片替换掉文档里已有的位图/图片对象，保持原位置和尺寸。
    支持页面顶层图片和PowerClip容器内部的图片。

    Args:
        shape_id: 要替换的位图形状 ID（StaticID 或名称）。
        new_image_path: 新图片文件的绝对路径。
    """
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接")

    if not os.path.isfile(new_image_path):
        return ToolResult.fail(f"新图片不存在: {new_image_path}")

    # 先在顶层找
    old = _find_shape(shape_id)
    container = None
    if not old:
        # 再在PowerClip容器里找
        old, container = _find_shape_in_powerclip(shape_id)

    if not old:
        return ToolResult.fail(f"未找到形状: {shape_id}")

    def _do():
        import time
        from PIL import Image
        doc = conn.app.ActiveDocument
        doc.Unit = _CDR_MILLIMETER
        # 记录旧图位置和尺寸
        old_x = old.LeftX
        old_y = old.TopY
        old_w = old.SizeWidth
        old_h = old.SizeHeight

        in_powerclip = container is not None

        if in_powerclip:
            # 进入PowerClip编辑模式
            container.PowerClip.EnterEditMode()
            time.sleep(0.2)

        # 删除旧图
        old.Delete()

        # 通过剪贴板粘贴导入新图
        layer = doc.ActiveLayer
        _copy_image_to_clipboard(new_image_path)
        time.sleep(0.3)
        new_shape = layer.Paste()

        # 保持宽度不变，高度按新图原始宽高比自动计算，避免变形
        # 同时保持和旧图相同的位置偏移
        img = Image.open(new_image_path)
        img_w, img_h = img.size
        aspect_ratio = img_h / img_w
        new_w = old_w
        new_h = new_w * aspect_ratio

        new_shape.LeftX = old_x
        new_shape.TopY = old_y
        new_shape.SizeWidth = new_w
        new_shape.SizeHeight = new_h

        if in_powerclip:
            # 退出PowerClip编辑模式
            container.PowerClip.LeaveEditMode()
            time.sleep(0.2)

        return {
            "old_shape_id": shape_id,
            "new_shape_id": str(new_shape.StaticID),
            "replaced": True,
            "in_powerclip": in_powerclip,
            "width_mm": round(new_w, 2),
            "height_mm": round(new_h, 2),
        }

    result = conn.safe_call(_do)
    if result["success"]:
        return ToolResult.ok("位图已替换", **result["result"])
    return ToolResult.fail(result.get("error", "替换位图失败"))


def trace_bitmap(
    shape_id: str = "",
    image_path: str = "",
    crop: list = None,
    trace_type: int = 1,
    smoothing: int = 30,
    detail_level: int = 100,
    color_mode: int = 2,
    color_count: int = 16,
    delete_original: bool = False,
    remove_background: bool = False,
    place: str = "beside",
) -> ToolResult:
    """描摹位图（调用 Corel PowerTRACE），把位图按轮廓自动转换成矢量形状。
    用于临摹 logo、文字、图形：在原图上按轮廓生成可编辑的矢量曲线。
    可直接传 image_path 自动导入；可用 crop 只临摹图片里的一部分区域。

    Args:
        shape_id: 已在画布上的位图形状 ID。留空则使用当前页面唯一的位图。
        image_path: 本地图片路径；传了就自动导入画布再描摹。
        crop: 只临摹图片中的一部分。格式 [left, top, right, bottom]，
            相对图片宽高的比例 0-1（0,0=左上角，1,1=右下角）。
            例如只临摹顶部 logo：[0.15, 0.0, 0.5, 0.25]。
        trace_type: 描摹类型 1-8（1 线条图/线条稿，数值越大越偏向图像）。
        smoothing: 平滑度 0-100（越大越平滑、节点越少）。
        detail_level: 细节级别 0-100（越大细节越丰富）。
        color_mode: 颜色模式，默认 2（跟随源图，可保留彩色）。
        color_count: 颜色数量（颜色较多时使用）。
        delete_original: 描摹后是否删除位图，默认 False（保留位图）。
        remove_background: 是否自动移除背景，默认 False。
        place: 结果位置，默认 "beside"（放在原图右侧并排显示，便于对比，且不删除原图）；
            "over" 为叠在原图正上方（会产生重影）。
    """
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接")

    if image_path and not os.path.isfile(image_path):
        return ToolResult.fail(f"图片不存在: {image_path}")

    # 校验并规范化 crop
    crop_box = None
    if crop:
        try:
            l, t, r, b = [float(v) for v in crop[:4]]
            l = max(0.0, min(1.0, l)); t = max(0.0, min(1.0, t))
            r = max(0.0, min(1.0, r)); b = max(0.0, min(1.0, b))
            if r <= l or b <= t:
                return ToolResult.fail("crop 区域无效：right 必须大于 left，bottom 必须大于 top")
            crop_box = [l, t, r, b]
        except Exception:
            return ToolResult.fail("crop 格式应为 [left, top, right, bottom] 比例 0-1")

    def _do():
        import time
        import tempfile
        from PIL import Image
        doc = conn.app.ActiveDocument
        doc.Unit = _CDR_MILLIMETER
        page = doc.ActivePage
        layer = doc.ActiveLayer
        base_x = page.LeftX
        base_y = page.TopY

        DPI = 300
        mmpp = 25.4 / DPI
        target = None
        prepared = None
        src_export = None
        direct_canvas = False

        if image_path:
            source_file = image_path
        else:
            # 找画布位图
            found = []
            if shape_id:
                for s in page.Shapes:
                    if s.Type == 5 and _shape_matches(s, shape_id):
                        found = [s]
                        break
            else:
                found = [s for s in page.Shapes if s.Type == 5]
            if len(found) > 1:
                raise RuntimeError("页面有多张位图，请用 shape_id 指定要描摹哪一张")
            if not found:
                raise RuntimeError("未找到可描摹的位图，请传 image_path 或先在 CDR 里放入图片")
            canvas_shape = found[0]
            if not crop_box:
                # 画布位图、无裁剪：直接描摹，不重新导入
                target = canvas_shape
                direct_canvas = True
            else:
                # 画布位图 + 裁剪：先导出
                fd, source_file = tempfile.mkstemp(suffix=".png")
                os.close(fd)
                canvas_shape.Bitmap.SaveAs(source_file)
                src_export = source_file

        # 文件处理路径（image_path，或画布位图 + crop）
        if not direct_canvas:
            pil_img = Image.open(source_file)
            iw0, ih0 = pil_img.size

            if crop_box:
                l, t, r, b = crop_box
                work = pil_img.crop((int(iw0 * l), int(ih0 * t), int(iw0 * r), int(ih0 * b)))
            else:
                work = pil_img

            # 降采样 + 写入 DPI，尺寸用降采样后的像素算（最长边 ≤169mm，描摹不崩）
            prepared, dscale, new_w, new_h = _normalize_pil(work, max_long_edge=2000, dpi=DPI)
            place_w = new_w * mmpp
            place_h = new_h * mmpp

            # 导入前先找空位：页面内优先，页面满了就放页面右侧/下侧的粘贴板
            slot_x, slot_y = _find_free_slot(doc, page, place_w, place_h)

            _copy_image_to_clipboard(prepared)
            time.sleep(0.3)
            target = layer.Paste()
            target.SizeWidth = place_w
            target.SizeHeight = place_h
            target.LeftX = slot_x
            target.TopY = slot_y

        # direct_canvas 描摹前保险：若画布位图过大，缩小到最长边 400mm 再描摹
        if direct_canvas:
            _safe_max = 400.0
            _long = max(target.SizeWidth, target.SizeHeight)
            if _long > _safe_max:
                _k = _safe_max / _long
                target.SizeWidth = target.SizeWidth * _k
                target.SizeHeight = target.SizeHeight * _k

        # 记录待描摹位图的位置
        orig_x = target.LeftX
        orig_y = target.TopY
        orig_w = target.SizeWidth
        orig_h = target.SizeHeight

        params = [
            int(trace_type),
            int(smoothing),
            int(detail_level),
            int(color_mode),
            0,
            int(color_count),
            bool(delete_original),
            bool(remove_background),
            False,
        ]
        result_group = target.Bitmap.Trace(*params).Finish()

        # 对齐描摹结果
        try:
            if place == "over":
                result_group.LeftX = orig_x
                result_group.TopY = orig_y
            elif place == "beside":
                result_group.LeftX = orig_x + orig_w + 10
                result_group.TopY = orig_y
        except Exception:
            pass

        n_children = None
        group_id = None
        try:
            n_children = result_group.Shapes.Count
            group_id = str(result_group.StaticID)
        except Exception:
            try:
                n_children = result_group.Count
            except Exception:
                pass

        # 清理临时文件
        for p in (prepared, src_export):
            if p:
                try:
                    os.remove(p)
                except Exception:
                    pass

        return {
            "traced": True,
            "cropped": crop_box is not None,
            "result_group_id": group_id,
            "shape_count": n_children,
            "trace_type": int(trace_type),
            "width_mm": round(orig_w, 2),
            "height_mm": round(orig_h, 2),
        }

    result = conn.safe_call(_do, timeout=180)
    if result["success"]:
        return ToolResult.ok("位图已描摹成矢量形状", **result["result"])
    return ToolResult.fail(result.get("error", "描摹位图失败"))


def create_curve_shape(
    subpaths: list,
    fill_rgb: list = None,
    fill_cmyk: list = None,
    outline_rgb: list = None,
    outline_width_pt: float = 0,
    no_outline: bool = True,
) -> ToolResult:
    """通过贝塞尔曲线/直线段创建自由形状，可绘制任意非矩形轮廓（旗帜、波浪、飘带、不规则图形等）。

    Args:
        subpaths: 路径数组（支持多个子路径）。每个路径是一个对象：
            - points: 点列表，单位mm，原点在页面左上角，y 向下为正
              - 第一个点是起点：{"x": 50, "y": 50}
              - 后续每个点为一段：
                - 直线段 {"type": "line", "x": 100, "y": 100}
                - 贝塞尔曲线段 {"type": "curve", "x": 100, "y": 40,
                    "cp1x": 60, "cp1y": 50,   # 控制柄1，靠近上一个点
                    "cp2x": 90, "cp2y": 40}   # 控制柄2，靠近当前点
            - closed: 是否封闭（true/false）。填色的图形必须封闭。
        fill_rgb: 填充色 [r, g, b]（0-255）
        fill_cmyk: 填充色 [c, m, y, k]（0-100），与 fill_rgb 二选一
        outline_rgb: 描边色 [r, g, b]，需要描边时传
        outline_width_pt: 描边宽度（磅），默认 0
        no_outline: 是否去掉描边，默认 true（干净的色块）
    """
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接")

    if not subpaths:
        return ToolResult.fail("subpaths 不能为空")

    def _do():
        import math
        doc = conn.app.ActiveDocument
        doc.Unit = _CDR_MILLIMETER
        page = doc.ActivePage
        ph = page.SizeHeight
        layer = doc.ActiveLayer

        def cy(y):
            # 页面坐标系 y 向下 -> CDR 坐标 y 向上
            return ph - y

        def _len_angle(cpx, cpy, nx, ny):
            # 控制点绝对坐标 -> 相对节点的（长度, 角度）
            dx, dy = cpx - nx, cpy - ny
            length = math.hypot(dx, dy)
            angle = math.degrees(math.atan2(dy, dx))
            return length, angle

        curve = doc.CreateCurve()

        for path in subpaths:
            points = path.get("points", [])
            if not points:
                continue
            first = points[0]
            prev_x = first["x"]
            prev_y = cy(first["y"])
            sp = curve.CreateSubPath(prev_x, prev_y)

            for pt in points[1:]:
                ptype = pt.get("type", "line")
                px = pt["x"]
                py = cy(pt["y"])
                if ptype == "curve":
                    # cp1 靠近上一个点（起始控制柄），cp2 靠近当前点（结束控制柄）
                    cp1x = pt.get("cp1x", pt["x"])
                    cp1y = cy(pt.get("cp1y", pt["y"]))
                    cp2x = pt.get("cp2x", pt["x"])
                    cp2y = cy(pt.get("cp2y", pt["y"]))
                    s_len, s_ang = _len_angle(cp1x, cp1y, prev_x, prev_y)
                    e_len, e_ang = _len_angle(cp2x, cp2y, px, py)
                    sp.AppendCurveSegment(px, py, s_len, s_ang, e_len, e_ang)
                else:
                    sp.AppendLineSegment(px, py)
                prev_x, prev_y = px, py

            if path.get("closed"):
                sp.Closed = True

        shape = layer.CreateCurve(curve)

        # 填充
        if fill_cmyk is not None:
            c, m, y, k = fill_cmyk
            shape.Fill.UniformColor.CMYKAssign(c, m, y, k)
        elif fill_rgb is not None:
            r, g, b = fill_rgb
            shape.Fill.UniformColor.RGBAssign(r, g, b)
        else:
            shape.Fill.ApplyNoFill()

        # 描边
        if outline_rgb is not None:
            r, g, b = outline_rgb
            width = outline_width_pt if outline_width_pt > 0 else 1.0
            shape.Outline.Width = width
            shape.Outline.Color.RGBAssign(r, g, b)
            shape.Outline.LineJoin = 2
            shape.Outline.LineCaps = 1
        elif no_outline:
            shape.Outline.SetNoOutline()

        return {
            "shape_id": str(shape.StaticID),
            "type": "curve",
            "width_mm": round(shape.SizeWidth, 2),
            "height_mm": round(shape.SizeHeight, 2),
            "left_mm": round(shape.LeftX, 2),
            "top_mm": round(ph - shape.TopY, 2),
        }

    result = conn.safe_call(_do)
    if result["success"]:
        return ToolResult.ok("自由曲线形状已创建", **result["result"])
    return ToolResult.fail(result.get("error", "创建曲线形状失败"))


def apply_gradient_fill(
    shape_id: str,
    start_rgb: list = None,
    end_rgb: list = None,
    start_cmyk: list = None,
    end_cmyk: list = None,
    gradient_type: str = "linear",
    angle: float = 0.0,
    midpoint: float = 50,
    edge_pad: float = 0,
    center_offset_x: float = 0.0,
    center_offset_y: float = 0.0,
    color_stops: list = None,
) -> ToolResult:
    """给已有形状应用渐变填充（线性/径向/圆锥/矩形），支持双色或多色渐变。

    Args:
        shape_id: 目标形状 ID（StaticID 或名称），支持 PowerClip 容器内的形状。
        start_rgb: 起始颜色 [r,g,b]（0-255）。
        end_rgb: 结束颜色 [r,g,b]。
        start_cmyk / end_cmyk: 用 CMYK 时传 [c,m,y,k]（0-100），与 rgb 二选一。
        gradient_type: 渐变类型，可选 "linear"（线性，默认）/"radial"（径向）/
            "conical"（圆锥）/"square"（矩形）。
        angle: 渐变角度（度）。线性：0 从左到右，90 从下到上。默认 0。
        midpoint: 中点位置 0-100，控制两色过渡位置，默认 50。
        edge_pad: 边缘留白 0-49，让两端颜色更实，默认 0。
        center_offset_x / center_offset_y: 径向/圆锥/矩形渐变中心偏移（百分比，-100~100）。
        color_stops: 多色渐变的中间色标列表，每项：
            {"position": 33, "rgb": [r,g,b]} 或 {"position": 66, "cmyk": [c,m,y,k]}
            不传则只用 start/end 双色。
    """
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接")

    def _color_spec(rgb, cmyk):
        if cmyk is not None:
            return ("cmyk", cmyk)
        if rgb is not None:
            return ("rgb", rgb)
        return None

    start_spec = _color_spec(start_rgb, start_cmyk)
    end_spec = _color_spec(end_rgb, end_cmyk)
    if not start_spec or not end_spec:
        return ToolResult.fail("必须同时提供 start 和 end 颜色（rgb 或 cmyk）")

    type_map = {"linear": 1, "radial": 2, "conical": 3, "square": 4}
    if gradient_type not in type_map:
        return ToolResult.fail("gradient_type 必须是 linear/radial/conical/square")
    gtype = type_map[gradient_type]

    def _do():
        import time
        doc = conn.app.ActiveDocument
        doc.Unit = _CDR_MILLIMETER
        app = conn.app

        # 在 COM 线程内查找形状（顶层，再 PowerClip）
        target = _find_shape(shape_id)
        container = None
        if not target:
            target, container = _find_shape_in_powerclip(shape_id)
        if not target:
            raise RuntimeError(f"未找到形状: {shape_id}")

        def make_color(spec):
            c = app.CreateColor()
            if spec[0] == "rgb":
                r, g, b = spec[1]
                c.RGBAssign(r, g, b)
            else:
                cc, m, y, k = spec[1]
                c.CMYKAssign(cc, m, y, k)
            return c

        c1 = make_color(start_spec)
        c2 = make_color(end_spec)

        in_powerclip = container is not None
        if in_powerclip:
            container.PowerClip.EnterEditMode()
            time.sleep(0.2)

        target.Fill.ApplyFountainFill(
            StartColor=c1, EndColor=c2, Type=gtype, Angle=angle,
            Steps=0, EdgePad=edge_pad, MidPoint=midpoint,
            CenterOffsetX=center_offset_x, CenterOffsetY=center_offset_y,
        )
        f = target.Fill.Fountain

        # 多色标
        if color_stops:
            for stop in color_stops:
                pos = stop.get("position", 50)
                if stop.get("rgb") is not None:
                    col = app.CreateColor()
                    r, g, b = stop["rgb"]
                    col.RGBAssign(r, g, b)
                elif stop.get("cmyk") is not None:
                    col = app.CreateColor()
                    cc, m, y, k = stop["cmyk"]
                    col.CMYKAssign(cc, m, y, k)
                else:
                    continue
                f.Colors.Add(col, pos)

        if in_powerclip:
            container.PowerClip.LeaveEditMode()
            time.sleep(0.2)

        color_count = f.Colors.Count
        return {
            "shape_id": str(target.StaticID),
            "gradient_type": gradient_type,
            "angle": angle,
            "midpoint": midpoint,
            "color_count": color_count,
            "in_powerclip": in_powerclip,
        }

    result = conn.safe_call(_do)
    if result["success"]:
        return ToolResult.ok("渐变填充已应用", **result["result"])
    return ToolResult.fail(result.get("error", "应用渐变填充失败"))


def _collect_text_shapes(shape, out=None):
    """递归收集一个形状/群组内的所有文字形状（type=6），支持嵌套群组。"""
    if out is None:
        out = []
    try:
        st = shape.Type
        if st == 6:
            out.append(shape)
        elif st == 7:
            for child in shape.Shapes:
                _collect_text_shapes(child, out)
    except Exception:
        pass
    return out


def _safe_text_size(text_shape) -> float:
    for getter in (
        lambda: float(text_shape.Text.Story.Size),
        lambda: float(text_shape.Text.FontProperties.Size),
    ):
        try:
            return getter()
        except Exception:
            continue
    return 0.0


def duplicate_shapes(
    shape_id: str,
    count: int = 1,
    per_row: int = 0,
    gap: float = 10.0,
    texts: list = None,
    target_text: str = "",
) -> ToolResult:
    """批量复制一个形状/群组并按网格整齐排列，可选逐个改文字（广告店门牌批量复制专用）。
    用 CorelDRAW 的 Shape.Duplicate 复制，底图、样式、位置结构完全一致，不重新导入。

    Args:
        shape_id: 要复制的模板形状/群组 ID（StaticID 或名称）。
        count: 最终总个数（含原始模板）。如 10 表示总共 10 个，自动复制 count-1 个副本。
        per_row: 一排几个，排满自动换行；默认 0 表示全部排在一行。
        gap: 副本之间的间距（mm），默认 10。
        texts: 可选，文字列表，长度等于 count，逐个把每个目标里的主文字
            （班级名/编号/人名）改成对应内容。
        target_text: 模板里要被替换的原始文字内容（用于在群组里定位要改的文字）；
            留空则自动找（群组里唯一文字，或字号最大的主标题）。
    """
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接")
    from tools.text import _get_text_content, _set_text_content

    count = int(count)
    if count < 1:
        return ToolResult.fail("count 必须 >= 1")
    if texts is not None and len(texts) != count:
        return ToolResult.fail(f"texts 数量({len(texts)})必须等于 count({count})")
    per_row = int(per_row) if per_row and per_row > 0 else count

    def _locate_target_text(shape):
        ts_list = _collect_text_shapes(shape)
        if target_text:
            for ts in ts_list:
                if _get_text_content(ts.Text).strip() == target_text.strip():
                    return ts
        if len(ts_list) == 1:
            return ts_list[0]
        if len(ts_list) > 1:
            return max(ts_list, key=_safe_text_size)
        return None

    def _do():
        doc = conn.app.ActiveDocument
        doc.Unit = _CDR_MILLIMETER
        page = doc.ActivePage

        orig = None
        for s in page.Shapes:
            if _shape_matches(s, shape_id):
                orig = s
                break
        if not orig:
            raise RuntimeError(f"未找到模板形状: {shape_id}")

        base_x = orig.LeftX
        base_y = orig.TopY
        w = orig.SizeWidth
        h = orig.SizeHeight

        if texts:
            orig_text_shape = _locate_target_text(orig)
            if not orig_text_shape:
                raise RuntimeError("模板里没有找到可替换的文字对象（可用 target_text 指定）")

        targets = [orig]
        result_ids = [str(orig.StaticID)]
        # 复制 count-1 个副本，按网格定位
        for i in range(1, count):
            dup = orig.Duplicate()
            row = i // per_row
            col = i % per_row
            dup.LeftX = base_x + col * (w + gap)
            dup.TopY = base_y - row * (h + gap)
            targets.append(dup)
            result_ids.append(str(dup.StaticID))

        changed = []
        if texts:
            # 改原始模板
            _set_text_content(orig_text_shape.Text, str(texts[0]))
            changed.append({"index": 0, "text": str(texts[0])})
            # 逐个改副本
            for i in range(1, count):
                ts = _locate_target_text(targets[i])
                if ts:
                    _set_text_content(ts.Text, str(texts[i]))
                    changed.append({"index": i, "text": str(texts[i])})

        return {
            "duplicated": True,
            "total_count": count,
            "per_row": per_row,
            "gap_mm": gap,
            "shape_ids": result_ids,
            "texts_changed": changed,
        }

    result = conn.safe_call(_do, timeout=120)
    if result["success"]:
        return ToolResult.ok("批量复制完成", **result["result"])
    return ToolResult.fail(result.get("error", "批量复制失败"))


def _sort_reading_order(items):
    """把选中元素按"阅读顺序"排序：先从上到下分行，同一行内从左到右。

    输入坐标统一为 page-top-left mm（与 inspect_document 一致）：
    top_y_mm 距页面顶部向下增长，数值越小越靠上；left_x_mm 数值越小越靠左。
    行容差取这些框高度中位数的一半（同行 top 差异在此内即视为同一行）。

    Returns:
        (ordered_items, row_of, col_of)
        - ordered_items: 从上到下、每行内从左到右排好的列表
        - row_of: {shape_id: 从上到下第几行 (1-based)}
        - col_of: {shape_id: 该行内从左到右第几列 (1-based)}
    """
    if not items:
        return items, {}, {}
    hs = sorted(float(d.get("height_mm") or 0) for d in items)
    tol = (hs[len(hs) // 2] * 0.5) or 1.0
    by_top = sorted(items, key=lambda d: float(d.get("top_y_mm") or 0))  # 上→下（top-left: y 小=在上）
    rows = []
    for it in by_top:
        top = float(it.get("top_y_mm") or 0)
        placed = False
        for row in rows:
            if abs(top - row["top"]) <= tol:
                n = len(row["items"])
                row["top"] = (row["top"] * n + top) / (n + 1)
                row["items"].append(it)
                placed = True
                break
        if not placed:
            rows.append({"top": top, "items": [it]})
    rows.sort(key=lambda r: r["top"])  # 行从上到下（top-left: y 小=在上）
    out = []
    row_of = {}
    col_of = {}
    for ri, row in enumerate(rows, start=1):
        row["items"].sort(key=lambda d: float(d.get("left_x_mm") or 0))  # 左→右
        for ci, it in enumerate(row["items"], start=1):
            row_of[str(it.get("shape_id"))] = ri
            col_of[str(it.get("shape_id"))] = ci
        out.extend(row["items"])
    return out, row_of, col_of


def get_selection() -> ToolResult:
    """读取当前在 CorelDRAW 里选中的形状（支持多选，含群组），返回每个选中元素的
    shape_id、类型、位置、尺寸和文字内容。
    用法：用户在 CDR 里点选要操作的元素，然后说"把这个改成XX"，用本工具先精准定位
    （拿到 shape_id），再调 apply_operations 修改，不用截图、不用描述位置。
    """
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接")
    from tools.text import _get_text_content

    type_name = {1: "rectangle", 3: "curve", 5: "bitmap", 6: "text", 7: "group"}

    def _describe(s, page_height):
        t = int(s.Type)
        # CorelDRAW 原生 COM 的 Y 轴向上增长（TopY = 形状顶部距页面底部的高度），
        # 这里统一转成 page-top-left Y（距页面顶部向下增长，数值越小越靠上），
        # 与 inspect_document 的 bounds.y 方向一致，避免调用方把上下看反。
        native_top_y = float(s.TopY)
        top_left_y = page_height - native_top_y
        d = {
            "shape_id": str(s.StaticID),
            "name": s.Name if s.Name else "",
            "type": type_name.get(t, str(t)),
            "type_code": t,
            "left_x_mm": round(float(s.LeftX), 2),
            "top_y_mm": round(top_left_y, 2),
            "width_mm": round(float(s.SizeWidth), 2),
            "height_mm": round(float(s.SizeHeight), 2),
        }
        if t == 6:
            d["text"] = _get_text_content(s.Text)
        return d

    def _do():
        doc = conn.app.ActiveDocument
        doc.Unit = _CDR_MILLIMETER
        # 读页面高度，用于把 CorelDRAW 原生 Y 轴翻转成 page-top-left
        page_h = 297.0
        for getter in ("SizeHeight", "PageSizeHeight", "Height"):
            try:
                page_h = float(getattr(doc.ActivePage, getter))
                break
            except Exception:
                continue
        # 用 SelectionRange 读选中（doc.Selection() 在无选中时返回 Type=8 占位，不可靠）
        sr = doc.SelectionRange
        n = int(sr.Count)
        if n <= 0:
            return {
                "count": 0,
                "items": [],
                "hint": "当前没有选中任何元素。请在 CorelDRAW 里点选（框选）要操作的元素，然后再说一次。",
            }
        items = []
        for i in range(1, n + 1):
            items.append(_describe(sr.Item(i), page_h))
        items, row_of, col_of = _sort_reading_order(items)
        for it in items:
            sid = str(it.get("shape_id"))
            it["row_from_top"] = row_of.get(sid, 1)
            it["col_from_left"] = col_of.get(sid, 1)
        return {"count": n, "items": items}

    result = conn.safe_call(_do, timeout=40)
    if result["success"]:
        return ToolResult.ok("已读取选中元素", **result["result"])
    return ToolResult.fail(result.get("error", "读取选中失败"))


# ========== 组织架构图自动绘制 ==========

_ORG_STYLES = {
    "orange": {
        "name": "橙金商务风",
        "box_fill": [255, 247, 230], "box_outline": [214, 148, 38],
        "text": [80, 50, 12], "connector": [160, 120, 70],
    },
    "blue": {
        "name": "经典商务蓝",
        "box_fill": [235, 243, 255], "box_outline": [40, 96, 180],
        "text": [18, 45, 90], "connector": [70, 110, 170],
    },
    "gray": {
        "name": "简约灰边风",
        "box_fill": [255, 255, 255], "box_outline": [150, 156, 165],
        "text": [55, 60, 70], "connector": [150, 156, 165],
    },
    "solid": {
        "name": "实色填充风",
        "box_fill": [38, 70, 130], "box_outline": [38, 70, 130],
        "text": [255, 255, 255], "connector": [130, 150, 185],
    },
    "green": {
        "name": "绿色清新风",
        "box_fill": [236, 247, 238], "box_outline": [46, 140, 80],
        "text": [24, 75, 45], "connector": [80, 140, 100],
    },
    "blackgold": {
        "name": "黑金高端风",
        "box_fill": [28, 28, 30], "box_outline": [200, 165, 90],
        "text": [220, 190, 120], "connector": [150, 130, 85],
    },
}


def _parse_org_text(text: str):
    """解析缩进文本（空格或 Tab 表示层级）为嵌套树。"""
    rows = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = 0
        for ch in raw:
            if ch == " ":
                indent += 1
            elif ch == "\t":
                indent += 4
            else:
                break
        rows.append((indent, stripped))
    if not rows:
        return None
    root = None
    stack = []  # (indent, node)
    for indent, label in rows:
        node = {"label": label, "children": []}
        while stack and stack[-1][0] >= indent:
            stack.pop()
        if stack:
            stack[-1][1]["children"].append(node)
        else:
            if root is not None:
                raise ValueError("缩进文本里有多个顶层节点，组织架构必须只有一个根")
            root = node
        stack.append((indent, node))
    return root


def _measure_box(label: str, font_pt: float):
    """按文字（多行、中英文）计算框的最小尺寸（mm）。"""
    lines = label.split("\n")
    fs_mm = font_pt * 25.4 / 72.0
    max_units = 0.0
    for ln in lines:
        units = 0.0
        for ch in ln:
            code = ord(ch)
            # CJK / 全角算 1.0，其余（英文数字符号）算 0.56
            units += 1.0 if code >= 0x2E80 else 0.56
        max_units = max(max_units, units)
    text_w = fs_mm * max(1.0, max_units)
    text_h = fs_mm * 1.35 * len(lines)
    box_w = max(12.0, text_w + 7.0)
    box_h = max(8.0, text_h + 5.6)
    return round(box_w, 2), round(box_h, 2)


def _plan_org_chart(root, direction, region, style, font_family, base_font_pt,
                    h_gap, v_gap, corner_radius, title="", title_style="dark",
                    title_color=None):
    """纯计算（不涉及 COM）：返回最终绘制计划（boxes/texts/lines/title 的 CDR 坐标）。"""
    vertical = direction == "vertical"

    # 1) 遍历：depth、框尺寸
    levels = {}
    all_nodes = []

    def walk(node, depth):
        node.setdefault("children", [])
        bw, bh = _measure_box(node["label"], base_font_pt)
        node["depth"] = depth
        node["box_w"], node["box_h"] = bw, bh
        # 抽象 p/l 轴上的尺寸
        if vertical:
            node["box_p"], node["box_l"] = bw, bh
            gap_p, gap_l = h_gap, v_gap
        else:
            node["box_p"], node["box_l"] = bh, bw
            gap_p, gap_l = v_gap, h_gap
        node["gap_p"], node["gap_l"] = gap_p, gap_l
        levels.setdefault(depth, []).append(node)
        all_nodes.append(node)
        for c in node["children"]:
            walk(c, depth + 1)

    walk(root, 0)

    gap_p = root["gap_p"]
    gap_l = root["gap_l"]

    # 2) 子树在 p 轴长度（自底向上）
    def calc_subtree(node):
        ch = node["children"]
        if not ch:
            node["subtree_p"] = node["box_p"]
        else:
            children_p = sum(calc_subtree(c) for c in ch) + gap_p * (len(ch) - 1)
            node["subtree_p"] = max(node["box_p"], children_p)
        return node["subtree_p"]

    calc_subtree(root)

    # 3) p 坐标（自顶向下）
    def layout_p(node, p_left):
        ch = node["children"]
        if not ch:
            node["p_c"] = p_left + node["subtree_p"] / 2
        else:
            children_p = sum(c["subtree_p"] for c in ch) + gap_p * (len(ch) - 1)
            cl = p_left + (node["subtree_p"] - children_p) / 2
            for c in ch:
                layout_p(c, cl)
                cl += c["subtree_p"] + gap_p
            node["p_c"] = (ch[0]["p_c"] + ch[-1]["p_c"]) / 2

    layout_p(root, 0.0)

    # 4) l 坐标（每层）
    max_d = max(levels)
    box_l_max = {d: max(n["box_l"] for n in levels[d]) for d in levels}
    l_c = {}
    top = 0.0
    for d in range(max_d + 1):
        l_c[d] = top + box_l_max[d] / 2
        top = l_c[d] + box_l_max[d] / 2 + gap_l
    for n in all_nodes:
        n["l_c"] = l_c[n["depth"]]

    nat_p = root["subtree_p"]
    nat_l = l_c[max_d] + box_l_max[max_d] / 2

    rl, rt = float(region["x"]), float(region["y"])
    W, H = float(region["width"]), float(region["height"])
    # 四周留安全边距，避免内容贴边/视觉上像超出区域
    SAFE = 3.0
    rl += SAFE
    rt -= SAFE
    W -= 2 * SAFE
    H -= 2 * SAFE

    # 5) 标题：迭代两次，确定标题高度（在区域内顶部，架构图缩小让位）
    def _text_units(txt):
        return sum(1.0 if ord(c) >= 0x2E80 else 0.56 for c in txt)

    title_info = None
    title_h = 0.0
    s = 1.0
    node_font = base_font_pt
    for _it in range(2):
        chart_top = rt - title_h
        chart_h = H - title_h
        if vertical:
            s = min(W / nat_p, chart_h / nat_l)
        else:
            s = min(W / nat_l, chart_h / nat_p)
        node_font = base_font_pt * s

        if title:
            t_font = node_font * 1.6
            t_fs_mm = t_font * 25.4 / 72.0
            t_w = t_fs_mm * _text_units(title)
            avail_w = W - 4.0  # 段落框边距
            if t_w > avail_w:  # 标题过长，收字号到不换行
                t_font = max(node_font, t_font * avail_w / max(t_w, 1.0))
            t_h = t_font * 25.4 / 72.0 * 1.2 + 9.0
            title_h = t_h
            if _it == 1:
                if title_style == "custom" and title_color:
                    tcolor = title_color
                elif title_style == "theme":
                    tcolor = style["box_outline"]
                else:
                    tcolor = [50, 50, 55]
                title_info = {
                    "label": title,
                    "left": rl, "top": rt, "right": rl + W, "bottom": rt - title_h,
                    "x": rl + W / 2, "y": rt - title_h / 2,
                    "font_pt": t_font, "color": tcolor,
                }
        else:
            break

    MIN_FONT = 7.0
    if node_font < MIN_FONT:
        raise ValueError(
            f"区域 {W:.0f}×{H:.0f}mm 太小，字号会小于 {MIN_FONT:.0f}pt。"
            f"建议：换一个方向（{('横版' if vertical else '竖版')}）、加大区域，或精简内容。"
        )

    chart_top = rt - title_h
    chart_h = H - title_h
    if vertical:
        off_p = (W - nat_p * s) / 2
        off_l = (chart_h - nat_l * s) / 2
    else:
        off_p = (chart_h - nat_p * s) / 2
        off_l = (W - nat_l * s) / 2

    def to_cd(p, l):
        if vertical:
            return rl + (p * s + off_p), chart_top - (l * s + off_l)
        return rl + (l * s + off_l), chart_top - (p * s + off_p)

    # 6) 框 + 文字
    boxes, texts = [], []
    for n in all_nodes:
        x, y = to_cd(n["p_c"], n["l_c"])
        bw, bh = n["box_w"] * s, n["box_h"] * s
        boxes.append({
            "left": x - bw / 2, "right": x + bw / 2,
            "top": y + bh / 2, "bottom": y - bh / 2,
            "corner": max(0.0, corner_radius * s),
        })
        texts.append({
            "x": x, "y": y, "label": n["label"],
            "font_pt": base_font_pt * s, "font_family": font_family,
        })

    # 7) 连接线（抽象 p/l，统一逻辑）
    seg = []
    for n in all_nodes:
        ch = n["children"]
        if not ch:
            continue
        l_out = n["l_c"] + n["box_l"] / 2
        l_in = ch[0]["l_c"] - ch[0]["box_l"] / 2
        p_parent = n["p_c"]
        if len(ch) == 1:
            seg.append((p_parent, l_out, p_parent, l_in))
        else:
            l_bus = (l_out + l_in) / 2
            seg.append((p_parent, l_out, p_parent, l_bus))
            seg.append((ch[0]["p_c"], l_bus, ch[-1]["p_c"], l_bus))
            for c in ch:
                seg.append((c["p_c"], l_bus, c["p_c"], l_in))
    lines = []
    for pa, la, pb, lb in seg:
        x1, y1 = to_cd(pa, la)
        x2, y2 = to_cd(pb, lb)
        lines.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2})

    return {
        "direction": ("vertical" if vertical else "horizontal"),
        "style": style["name"],
        "node_count": len(all_nodes),
        "depth": max_d + 1,
        "final_font_pt": round(node_font, 1),
        "scale": round(s, 3),
        "region": {"x": rl, "y": rt, "width": W, "height": H},
        "title": title_info,
        "boxes": boxes, "texts": texts, "lines": lines,
        "palette": style,
    }


def create_org_chart(
    data: dict = None,
    text: str = "",
    direction: str = "vertical",
    region: dict = None,
    style: str = "orange",
    font_family: str = "Microsoft YaHei",
    base_font_pt: float = 12.0,
    h_gap: float = 10.0,
    v_gap: float = 14.0,
    corner_radius: float = 2.5,
    custom_style: dict = None,
    title: str = "",
    title_style: str = "dark",
    title_color: list = None,
    region_shape_id: str = "",
) -> ToolResult:
    """在指定区域内自动绘制组织架构图（框+文字+正交连接线），自动按区域尺寸适配、不溢出、整体居中；
    可在区域内顶部加一个居中大标题。

    典型流程：先在 CDR 选中一个框（get_selection 拿到位置尺寸）或直接给 region → 整理组织树 →
    核对层级 → 本工具一次绘制。

    Args:
        data: 嵌套树，{"label": "总经理", "children": [{"label": "副经理", "children": [...]}]}，
            与 text 二选一。
        text: 缩进文本（空格/Tab 表示层级，每行一个职位）。
        direction: "vertical" 竖版（从上到下，适合宽浅、每层人多）；
            "horizontal" 横版（从左到右，适合窄深、层级多）。
        region: 绘制区域，CDR 坐标 {"x": LeftX, "y": TopY(上边), "width": W, "height": H}，
            可直接用 get_selection 返回的 left_x_mm/top_y_mm/width_mm/height_mm。
            若不传 region，工具会自动读取当前 CDR 选中的框（或 region_shape_id 指定的框）作为区域。
        region_shape_id: 可选，指定某个矩形框的 shape_id 作为区域（一般直接让工具读当前选中框即可）。
        style: 风格预设：orange(橙金)/blue(商务蓝)/gray(简约灰)/solid(实色)/green(绿色)/
            blackgold(黑金)/custom(配合 custom_style)。
        font_family: 字体名，默认微软雅黑。
        base_font_pt: 基准字号（pt），绘制时会按区域自动缩放。
        h_gap / v_gap: 同级水平间距 / 层间垂直间距（mm）。
        corner_radius: 框圆角（mm）。
        custom_style: 自定义配色 {"box_fill":[r,g,b],"box_outline":[...],"text":[...],"connector":[...]}。
        title: 大标题文字（如"XX公司组织架构图"）；留空则不加标题。
        title_style: 大标题样式："dark"加大加粗深色（默认）/"theme"用所选风格主色/"custom"配合 title_color。
        title_color: 自定义大标题颜色 [r,g,b]。
    """
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接")

    # 解析树
    root = None
    if data:
        root = data
    elif text:
        try:
            root = _parse_org_text(text)
        except ValueError as e:
            return ToolResult.fail(str(e))
    if root is None:
        return ToolResult.fail("必须提供 data（嵌套树）或 text（缩进文本）")

    direction = (direction or "vertical").lower()
    if direction not in ("vertical", "horizontal"):
        return ToolResult.fail("direction 必须是 vertical（竖版）或 horizontal（横版）")

    # 区域：优先 region 字典；没传则读 region_shape_id 指定的框，或当前 CDR 选中的框
    if not region or not all(k in region for k in ("x", "y", "width", "height")):
        wanted_id = region_shape_id or ""

        def _read_region():
            doc = conn.app.ActiveDocument
            doc.Unit = _CDR_MILLIMETER
            sh = None
            if wanted_id:
                for s in doc.ActivePage.Shapes:
                    if str(s.StaticID) == str(wanted_id):
                        sh = s
                        break
            else:
                sr = doc.SelectionRange
                if int(sr.Count) >= 1:
                    sh = sr.Item(1)
            if sh is None:
                return None
            return {
                "x": float(sh.LeftX), "y": float(sh.TopY),
                "width": float(sh.SizeWidth), "height": float(sh.SizeHeight),
            }

        rr = conn.safe_call(_read_region, timeout=40)
        if not rr["success"] or rr.get("result") is None:
            return ToolResult.fail(
                "没有找到绘制区域：请先在 CDR 里选中要放架构图的矩形框（且保持选中），或直接提供 region。"
            )
        region = rr["result"]

    if float(region["width"]) <= 0 or float(region["height"]) <= 0:
        return ToolResult.fail("区域宽高必须大于 0")

    # 配色
    if style == "custom" and custom_style:
        pal = {
            "name": "自定义",
            "box_fill": custom_style.get("box_fill", [255, 255, 255]),
            "box_outline": custom_style.get("box_outline", [120, 120, 120]),
            "text": custom_style.get("text", [40, 40, 40]),
            "connector": custom_style.get("connector", [120, 120, 120]),
        }
    else:
        pal = _ORG_STYLES.get(style, _ORG_STYLES["orange"])

    # 纯计算（出错在抛给用户前返回，不会在 CDR 留下半成品）
    try:
        plan = _plan_org_chart(
            root, direction, region, pal, font_family, float(base_font_pt),
            float(h_gap), float(v_gap), float(corner_radius),
            title=(title or ""), title_style=(title_style or "dark"),
            title_color=title_color,
        )
    except ValueError as e:
        return ToolResult.fail(str(e))

    def _draw():
        from tools.text import _set_text_size, _set_text_font, _set_text_bold
        doc = conn.app.ActiveDocument
        doc.Unit = _CDR_MILLIMETER
        layer = doc.ActivePage.ActiveLayer
        palette = plan["palette"]

        # 先画连接线（在框下面）
        line_ids = []
        for ln in plan["lines"]:
            s = layer.CreateLineSegment(ln["x1"], ln["y1"], ln["x2"], ln["y2"])
            try:
                s.Outline.Color.RGBAssign(*palette["connector"])
                s.Outline.Width = max(0.4, 0.6 * plan["scale"])
                s.Outline.LineCaps = 1
                s.Name = "org_line"
            except Exception:
                pass
            line_ids.append(str(s.StaticID))

        # 画框
        box_ids = []
        for b in plan["boxes"]:
            r = b["corner"]
            rect = layer.CreateRectangle(
                b["left"], b["bottom"], b["right"], b["top"], r, r, r, r
            )
            try:
                rect.Fill.UniformColor.RGBAssign(*palette["box_fill"])
            except Exception:
                pass
            try:
                rect.Outline.Color.RGBAssign(*palette["box_outline"])
                rect.Outline.Width = max(0.5, 0.9 * plan["scale"])
                rect.Outline.LineJoin = 2
            except Exception:
                pass
            rect.Name = f"org_box_{rect.StaticID}"
            box_ids.append(str(rect.StaticID))

        # 画文字（段落文本，框内居中，支持多行；CDR 换行符必须用 \r）
        text_ids = []
        for i, t in enumerate(plan["texts"]):
            b = plan["boxes"][i]
            para_label = t["label"].replace("\r\n", "\r").replace("\n", "\r")
            tshape = layer.CreateParagraphText(
                b["left"], b["top"], b["right"], b["bottom"], para_label
            )
            _set_text_size(tshape.Text, max(6.0, t["font_pt"]))
            if font_family:
                _set_text_font(tshape.Text, font_family)
            # 水平居中（对 Story 生效；缩进清零避免挤位）
            for attr in ("FirstLineIndent", "LeftIndent", "RightIndent"):
                try:
                    setattr(tshape.Text.Story, attr, 0.0)
                except Exception:
                    pass
            for setter in (
                lambda: setattr(tshape.Text.Story, "Alignment", 3),
                lambda: setattr(tshape.Text, "Alignment", 3),
            ):
                try:
                    setter()
                    break
                except Exception:
                    continue
            try:
                tshape.Text.Frame.VerticalAlignment = 1  # 垂直居中
            except Exception:
                pass
            try:
                tshape.Fill.UniformColor.RGBAssign(*palette["text"])
            except Exception:
                pass
            tshape.Name = f"org_text_{tshape.StaticID}"
            text_ids.append(str(tshape.StaticID))

        # 画大标题（区域内顶部，段落文本居中，自动不换行）
        title_ids = []
        ti = plan.get("title")
        if ti:
            tshape = layer.CreateParagraphText(
                ti["left"], ti["top"], ti["right"], ti["bottom"], ti["label"]
            )
            _set_text_size(tshape.Text, max(6.0, ti["font_pt"]))
            if font_family:
                _set_text_font(tshape.Text, font_family)
            try:
                _set_text_bold(tshape.Text, True)
            except Exception:
                pass
            for attr in ("FirstLineIndent", "LeftIndent", "RightIndent"):
                try:
                    setattr(tshape.Text.Story, attr, 0.0)
                except Exception:
                    pass
            for setter in (
                lambda: setattr(tshape.Text.Story, "Alignment", 3),
                lambda: setattr(tshape.Text, "Alignment", 3),
            ):
                try:
                    setter()
                    break
                except Exception:
                    continue
            try:
                tshape.Text.Frame.VerticalAlignment = 1
            except Exception:
                pass
            try:
                tshape.Fill.UniformColor.RGBAssign(*ti["color"])
            except Exception:
                pass
            tshape.Name = f"org_title_{tshape.StaticID}"
            title_ids.append(str(tshape.StaticID))

        return {
            "created": True,
            "direction": plan["direction"],
            "style": plan["style"],
            "node_count": plan["node_count"],
            "depth": plan["depth"],
            "final_font_pt": plan["final_font_pt"],
            "scale": plan["scale"],
            "title": ti["label"] if ti else "",
            "title_font_pt": round(ti["font_pt"], 1) if ti else 0,
            "box_count": len(box_ids),
            "line_count": len(line_ids),
            "text_count": len(text_ids),
            "box_ids": box_ids,
            "text_ids": text_ids,
            "line_ids": line_ids,
            "title_ids": title_ids,
        }

    result = conn.safe_call(_draw, timeout=180)
    if result["success"]:
        r = result["result"]
        dname = "竖版（从上到下）" if r["direction"] == "vertical" else "横版（从左到右）"
        tstr = f"、含大标题《{r['title']}》" if r.get("title") else ""
        return ToolResult.ok(
            f"组织架构图已绘制：{r['node_count']}个框、{r['depth']}层、{dname}、{r['style']}、字号{r['final_font_pt']}pt{tstr}",
            **r,
        )
    return ToolResult.fail(result.get("error", "组织架构图绘制失败"))
