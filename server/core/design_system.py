"""设计系统 Token & Layout Mathematics

定义 CorelDRAW 自动化排版的专业规范：
- 印刷级 CMYK 调色板 (Corporate Navy, Slate Charcoal, Emerald, Gold)
- 纸张 Typography 比例规 (A4, A5, 名片, 标识门牌)
- 布局边距、表格行高与列对齐计算器
"""

from typing import Any, Dict, Tuple


# =============================================================================
# CMYK 调色板预设 (C, M, Y, K) 0-100 整数
# =============================================================================

PALETTES: Dict[str, Dict[str, Tuple[int, int, int, int]]] = {
    "corporate_navy": {
        "primary": (100, 75, 25, 45),       # 深海军蓝
        "secondary": (80, 40, 0, 0),        # 钢蓝
        "accent": (0, 30, 95, 0),           # 温暖金
        "dark_text": (0, 0, 0, 90),         # 90% 黑
        "muted_text": (0, 0, 0, 60),        # 60% 灰
        "bg_light": (3, 2, 2, 0),           # 柔和浅白
        "header_bg": (100, 75, 25, 45),     # 表头背景
        "header_text": (0, 0, 0, 0),        # 表头白字
    },
    "slate_charcoal": {
        "primary": (75, 68, 67, 90),        # 深炭灰
        "secondary": (50, 40, 40, 20),      # 烟灰
        "accent": (0, 70, 90, 0),           # 活力橙
        "dark_text": (0, 0, 0, 90),
        "muted_text": (0, 0, 0, 55),
        "bg_light": (2, 2, 2, 0),
        "header_bg": (75, 68, 67, 90),
        "header_text": (0, 0, 0, 0),
    },
    "emerald_green": {
        "primary": (85, 25, 65, 30),        # 翡翠绿
        "secondary": (60, 10, 45, 0),       # 薄荷绿
        "accent": (0, 45, 95, 0),           # 暖黄金
        "dark_text": (0, 0, 0, 90),
        "muted_text": (0, 0, 0, 60),
        "bg_light": (2, 1, 3, 0),
        "header_bg": (85, 25, 65, 30),
        "header_text": (0, 0, 0, 0),
    },
}


# =============================================================================
# 纸张 Font Sizes (pt) & Margins (mm)
# =============================================================================

PAPER_SPECS: Dict[str, Dict[str, Any]] = {
    "A4": {
        "width": 210.0,
        "height": 297.0,
        "margin": 15.0,
        "title_pt": 26.0,
        "h1_pt": 16.0,
        "h2_pt": 12.0,
        "table_header_pt": 10.0,
        "body_pt": 9.5,
        "caption_pt": 8.0,
        "default_row_height": 9.0,
    },
    "A5": {
        "width": 148.0,
        "height": 210.0,
        "margin": 10.0,
        "title_pt": 20.0,
        "h1_pt": 13.0,
        "h2_pt": 10.5,
        "table_header_pt": 9.0,
        "body_pt": 8.5,
        "caption_pt": 7.0,
        "default_row_height": 7.5,
    },
    "signage_200x80": {
        "width": 200.0,
        "height": 80.0,
        "margin": 10.0,
        "title_pt": 42.0,
        "h1_pt": 18.0,
        "h2_pt": 12.0,
        "table_header_pt": 11.0,
        "body_pt": 10.0,
        "caption_pt": 8.0,
        "default_row_height": 10.0,
    },
    "business_card": {
        "width": 90.0,
        "height": 54.0,
        "margin": 5.0,
        "title_pt": 14.0,
        "h1_pt": 10.0,
        "h2_pt": 8.0,
        "table_header_pt": 8.0,
        "body_pt": 7.0,
        "caption_pt": 6.0,
        "default_row_height": 6.0,
    },
}


def get_palette(name: str = "corporate_navy") -> Dict[str, Tuple[int, int, int, int]]:
    """获取指定名称的 CMYK 调色板"""
    return PALETTES.get(name.lower(), PALETTES["corporate_navy"])


def get_paper_spec(paper_name: str = "A4") -> Dict[str, Any]:
    """获取指定纸张的排版比例参数"""
    return PAPER_SPECS.get(paper_name.upper(), PAPER_SPECS["A4"])
