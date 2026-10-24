"""Top-Left Coordinate System Adapter for CorelDRAW

CorelDRAW native COM API uses mathematical coordinates where (0,0) is at the BOTTOM-LEFT
and Y increases UPWARDS. Standard screen and document design tools use Top-Left coordinates
where (0,0) is at the TOP-LEFT and Y increases DOWNWARDS.

This adapter converts Top-Left coordinates into CorelDRAW Y-coordinates to guarantee that
elements are never rendered upside-down or out of order.
"""

from dataclasses import dataclass
from typing import Tuple


COORDINATE_SPACE = "page_top_left"


@dataclass(frozen=True)
class Bounds:
    """Canonical public bounds in millimetres, measured from page top-left."""

    x: float
    y: float
    width: float
    height: float

    def validate(self) -> "Bounds":
        if self.width <= 0 or self.height <= 0:
            raise ValueError("width and height must be greater than zero")
        return self


def top_left_to_corel(top_y: float, shape_height: float, page_height: float) -> float:
    """将 Top-Left Y 坐标 (距离页面顶部的距离) 转换为 CorelDRAW Y 坐标 (距离页面底部的距离)。

    Args:
        top_y: 形状顶部距离页面顶部的距离 (mm)
        shape_height: 形状高度 (mm)
        page_height: 页面总高度 (mm)，如 A4 为 297mm

    Returns:
        CorelDRAW Y 坐标 (mm)，表示形状左下角距离页面底部的距离
    """
    return page_height - top_y - shape_height


def corel_to_top_left(corel_y: float, shape_height: float, page_height: float) -> float:
    """将 CorelDRAW Y 坐标 (距离页面底部的距离) 转换为 Top-Left Y 坐标 (距离页面顶部的距离)。"""
    return page_height - corel_y - shape_height


def normalize_rect_top_left(
    x: float,
    top_y: float,
    width: float,
    height: float,
    page_height: float,
) -> Tuple[float, float, float, float]:
    """标准化 Top-Left 矩形框并输出 (x, corel_y, width, height)

    Returns:
        (x, corel_y, width, height) 适合直接传给 CorelDRAW SetPosition / CreateRectangle
    """
    corel_y = top_left_to_corel(top_y, height, page_height)
    return x, corel_y, width, height


def top_left_to_corel_bounds(
    x: float,
    top_y: float,
    width: float,
    height: float,
    page_height: float,
) -> Tuple[float, float, float, float]:
    """将 Top-Left (x, top_y, w, h) 转换为 CorelDRAW 边界坐标 (left, bottom, right, top)。

    Returns:
        (left, bottom, right, top)
        - left = x
        - bottom = page_height - top_y - height
        - right = x + width
        - top = page_height - top_y
    """
    left = x
    right = x + width
    top = page_height - top_y
    bottom = page_height - top_y - height
    return left, bottom, right, top


def bounds_to_corel(bounds: Bounds, page_height: float) -> Tuple[float, float, float, float]:
    """Convert canonical bounds to Corel (left, bottom, right, top) once."""
    b = bounds.validate()
    return top_left_to_corel_bounds(b.x, b.y, b.width, b.height, page_height)


def corel_bounds_to_top_left(
    left: float,
    bottom: float,
    width: float,
    height: float,
    page_height: float,
) -> Bounds:
    return Bounds(
        x=float(left),
        y=float(page_height - bottom - height),
        width=float(width),
        height=float(height),
    )
