"""Print Design Intelligence Module — Safe zones, margins, print specs, and visual hierarchy rules."""

from typing import Dict, Any, Tuple

# Standard Print Specs
PRINT_SPECS = {
    "business_card": {
        "width_mm": 90.0,
        "height_mm": 54.0,
        "bleed_mm": 3.0,
        "safe_margin_mm": 3.5,
        "min_font_size": 7.0,
        "title_font_size": 18.0,
        "subtitle_font_size": 9.0,
    },
    "a4_flyer": {
        "width_mm": 210.0,
        "height_mm": 297.0,
        "bleed_mm": 3.0,
        "safe_margin_mm": 12.0,
        "min_font_size": 10.0,
        "title_font_size": 32.0,
        "subtitle_font_size": 16.0,
    },
    "banner_stand": {
        "width_mm": 800.0,
        "height_mm": 2000.0,
        "bleed_mm": 5.0,
        "safe_margin_mm": 40.0,
        "min_font_size": 24.0,
        "title_font_size": 96.0,
        "subtitle_font_size": 48.0,
    },
}


def get_print_spec(doc_type: str, width_mm: float = 0.0, height_mm: float = 0.0) -> Dict[str, Any]:
    """获取印刷规范与安全区 (Safe Margin / Harmful Area Guard)"""
    key = doc_type.lower()
    spec = PRINT_SPECS.get(key, {
        "width_mm": width_mm if width_mm > 0 else 210.0,
        "height_mm": height_mm if height_mm > 0 else 297.0,
        "bleed_mm": 3.0,
        "safe_margin_mm": max(3.5, min(width_mm, height_mm) * 0.05) if width_mm > 0 else 10.0,
        "min_font_size": 8.0,
        "title_font_size": 24.0,
        "subtitle_font_size": 12.0,
    })

    w = spec["width_mm"] if width_mm <= 0 else width_mm
    h = spec["height_mm"] if height_mm <= 0 else height_mm
    m = spec["safe_margin_mm"]

    safe_bounds = {
        "left": m,
        "top": m,
        "right": w - m,
        "bottom": h - m,
        "width": w - 2 * m,
        "height": h - 2 * m,
    }

    return {
        "width_mm": w,
        "height_mm": h,
        "bleed_mm": spec.get("bleed_mm", 3.0),
        "safe_margin_mm": m,
        "safe_bounds": safe_bounds,
        "min_font_size": spec.get("min_font_size", 8.0),
        "title_font_size": spec.get("title_font_size", 24.0),
        "subtitle_font_size": spec.get("subtitle_font_size", 12.0),
    }


def calculate_typography_scale(base_size: float, ratio: float = 1.333) -> Tuple[float, float, float]:
    """根据比例计算 3 级排版字号 (Body, Subhead, Title)"""
    body = max(7.0, base_size)
    subhead = round(body * ratio, 1)
    title = round(subhead * ratio, 1)
    return body, subhead, title
