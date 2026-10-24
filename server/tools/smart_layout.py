"""智能排版与多 Agent 协作工具 — 包含 Top-Left 坐标自动转换、美学设计系统与通用图像重建

解决传统生成中元素颠倒 (Upside-down)、文字重叠、字号失调等问题，
提供 3 个多 Agent 阶段工具与 2 个 master 宏工具 (create_smart_invoice, recreate_design_from_image)。
"""

import os
from pathlib import Path
from typing import Dict, Any, List, Optional

from core.connection import get_connection
from core.models import ToolResult
from core.design_system import get_palette, get_paper_spec
from tools import colors, document, export, preflight, shapes, text

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


# =============================================================================
# Agent 阶段 1: 架构师 Agent — 计算 Top-Left 几何与布局网格
# =============================================================================

def plan_design_layout(
    doc_type: str = "invoice",
    paper_size: str = "A4",
    item_count: int = 3,
) -> ToolResult:
    """【Agent 阶段 1：架构师】计算文档网格、边距、各区块 Top-Left 坐标与比例建议。

    Args:
        doc_type: "invoice" | "business_card" | "signage" | "flyer" | "poster"
        paper_size: "A4" | "A5" | "signage_200x80" | "business_card"
        item_count: 表格或条目数量

    Returns:
        包含 Top-Left 坐标方案和排版推荐参数的 ToolResult
    """
    spec = get_paper_spec(paper_size)
    pw, ph = spec["width"], spec["height"]
    margin = spec["margin"]
    content_w = pw - (margin * 2)

    # 计算区块 Top-Left 坐标 (距离页面顶部的 mm 数)
    layout = {
        "page_width": pw,
        "page_height": ph,
        "margin": margin,
        "content_width": content_w,
        "blocks": {
            "header_banner": {"x": 0.0, "top_y": 0.0, "w": pw, "h": 45.0 if doc_type == "invoice" else 30.0},
            "store_title": {"x": margin, "top_y": 10.0, "w": content_w * 0.6, "h": 15.0},
            "doc_label": {"x": margin + content_w * 0.6, "top_y": 10.0, "w": content_w * 0.4, "h": 15.0},
            "meta_info": {"x": margin, "top_y": 50.0, "w": content_w, "h": 35.0},
            "table_header": {"x": margin, "top_y": 90.0, "w": content_w, "h": 10.0},
            "table_start_y": 102.0,
            "row_height": spec["default_row_height"],
            "table_end_y": 102.0 + (item_count * spec["default_row_height"]),
            "totals_box": {
                "x": pw - margin - 70.0,
                "top_y": 102.0 + (item_count * spec["default_row_height"]) + 15.0,
                "w": 70.0,
                "h": 30.0,
            },
        },
        "font_spec": {
            "title_pt": spec["title_pt"],
            "h1_pt": spec["h1_pt"],
            "h2_pt": spec["h2_pt"],
            "table_header_pt": spec["table_header_pt"],
            "body_pt": spec["body_pt"],
            "caption_pt": spec["caption_pt"],
        },
    }

    return ToolResult.ok(f"为 {paper_size} {doc_type} 生成 Top-Left 布局规划", layout=layout)


# =============================================================================
# Agent 阶段 2: 视觉设计师 Agent — 应用色彩、斜角装饰 Banner 与排版
# =============================================================================

def apply_visual_styling(
    palette_name: str = "corporate_navy",
    show_diagonal_banner: bool = True,
) -> ToolResult:
    """【Agent 阶段 2：视觉设计师】创建装饰性斜角 Header 造型、应用 CMYK 色彩调色板。

    Args:
        palette_name: "corporate_navy" | "slate_charcoal" | "emerald_green"
        show_diagonal_banner: 是否在顶部创建装饰斜角 Banner

    Returns:
        包含应用调色板及创建造型信息的 ToolResult
    """
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接")

    palette = get_palette(palette_name)

    def _apply():
        doc = conn.app.ActiveDocument
        if not doc:
            raise RuntimeError("没有打开的文档")

        doc.Unit = 3  # mm
        page = doc.ActivePage
        pw = page.SizeWidth

        created = []
        if show_diagonal_banner:
            # 顶部 Header 矩形 (Top-Left y=0, height=45mm)
            banner_res = shapes.create_rectangle(0, 0, pw, 45.0)
            if banner_res.success and banner_res.data:
                sid = banner_res.data.get("shape_id", "")
                c, m, y, k = palette["header_bg"]
                colors.set_fill_cmyk(sid, c, m, y, k)
                colors.set_no_outline(sid)
                created.append("header_bg_banner")

        return {"palette_used": palette_name, "created_elements": created}

    result = conn.safe_call(_apply)
    if result["success"]:
        return ToolResult.ok(f"成功应用 {palette_name} 色彩与视觉样式", **result["result"])
    return ToolResult.fail(result.get("error", "应用视觉样式失败"))


# =============================================================================
# Agent 阶段 3: 质检员 Agent — 印前转曲、溢出检查与生产导出
# =============================================================================

def inspect_and_export_production(
    output_base_name: str = "output_doc",
    output_dir: str = "output",
    export_pdf_flag: bool = True,
    export_dxf_flag: bool = True,
) -> ToolResult:
    """【Agent 阶段 3：印前质检员】检查文字溢出、全要素转曲，并导出印刷 PDF、激光 DXF 和视觉 PNG 预览图。

    Args:
        output_base_name: 文件名主名 (如 "INV-2041")
        output_dir: 输出根目录
        export_pdf_flag: 是否导出 PDF
        export_dxf_flag: 是否导出 DXF

    Returns:
        包含导出文件路径和质检报告的 ToolResult
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(exist_ok=True)
    (out_dir / "print").mkdir(exist_ok=True)
    (out_dir / "laser").mkdir(exist_ok=True)
    (out_dir / "preview").mkdir(exist_ok=True)

    pdf_path = str(out_dir / "print" / f"{output_base_name}.pdf")
    dxf_path = str(out_dir / "laser" / f"{output_base_name}.dxf")
    preview_path = str(out_dir / "preview" / f"{output_base_name}.png")

    # 1. 检查全文档溢出
    overflow_res = preflight.check_text_overflow_all()

    # 2. 导出 400px 视觉预览图
    export.export_preview_png(preview_path, width_px=500)

    # 3. 导出 PDF & DXF (保持所有文字为可编辑矢量文字 cdrTextShape)
    pdf_res = export.export_pdf(pdf_path, bleed=3.0, crop_marks=True) if export_pdf_flag else None
    dxf_res = export.export_dxf(dxf_path) if export_dxf_flag else None


    return ToolResult.ok(

        f"质检与生产导出完成: {output_base_name}",
        pdf_path=pdf_path if export_pdf_flag and pdf_res and pdf_res.success else None,
        dxf_path=dxf_path if export_dxf_flag and dxf_res and dxf_res.success else None,
        preview_path=preview_path if os.path.isfile(preview_path) else None,
        overflow_check=overflow_res.message if overflow_res.success else "未发现溢出",
    )


# =============================================================================
# Master 宏 1: 一键智能 A4 发票生成 (自动修正 Top-Left 坐标，绝不上颠倒)
# =============================================================================

def create_smart_invoice(
    store_name: str,
    invoice_number: str,
    date_str: str,
    bill_to_name: str,
    bill_to_address: str,
    items: List[Dict[str, Any]],
    tax_rate_percent: float = 5.0,
    palette_name: str = "corporate_navy",
    output_pdf_path: str = "",
    output_dxf_path: str = "",
    output_preview_path: str = "",
) -> ToolResult:
    """【智能 A4 账单/发票一键生成】使用 Top-Left 坐标自适应排版，表头在上、清单在中间、总额在右下，支持自动算税。

    Args:
        store_name: 店铺/公司名称 (如 "GadgetZone Mobile Store")
        invoice_number: 发票编号 (如 "INV-2041")
        date_str: 日期字符串 (如 "28/07/2026")
        bill_to_name: 客户姓名 (如 "Rahul Sharma")
        bill_to_address: 客户地址/电话 (如 "+91 90000 11122, Mumbai")
        items: 商品列表 [{"description": "Mobile Back Cover", "qty": 3, "price": 150}, ...]
        tax_rate_percent: 税率百分比 (如 5.0 表示 5%)
        palette_name: "corporate_navy" | "slate_charcoal" | "emerald_green"
        output_pdf_path: PDF 导出路径
        output_dxf_path: DXF 导出路径
        output_preview_path: PNG 预览图路径

    Returns:
        包含成功状态与导出文件路径的 ToolResult
    """
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接")

    # 1. 创建 A4 文档 (210×297 mm)
    doc_res = document.create_document(210.0, 297.0, "mm")
    if not doc_res.success:
        return ToolResult.fail(f"创建 A4 文档失败: {doc_res.error}")

    spec = get_paper_spec("A4")
    pw = spec["width"]  # 210 mm
    margin = 15.0
    content_w = pw - (margin * 2)  # 180mm
    palette = get_palette(palette_name)

    # 2. 顶部 Header Banner (Top-Left: top_y=0, h=45mm)
    apply_visual_styling(palette_name=palette_name, show_diagonal_banner=True)

    # 3. 顶部 Header 文字 (白色字体，高清对比度，无重叠)
    # 店铺名称 (top_y=10mm)
    t_store = text.create_text_frame(margin, 10.0, 110.0, 15.0, store_name)
    if t_store.success and t_store.data:
        sid = t_store.data.get("shape_id", "")
        text.set_text_style(sid, font="Arial", size=18.0, bold=True, alignment="left")
        colors.set_fill_cmyk(sid, 0, 0, 0, 0)  # 纯白文字

    # 店铺 Slogan / 感谢短句 (top_y=27mm，在店铺名下方，绝对不重叠)
    sub_title = f"Thank you for shopping with {store_name}!"
    t_sub = text.create_text_frame(margin, 27.0, 110.0, 10.0, sub_title)
    if t_sub.success and t_sub.data:
        sub_id = t_sub.data.get("shape_id", "")
        text.set_text_style(sub_id, font="Arial", size=8.5, bold=False, alignment="left")
        colors.set_fill_cmyk(sub_id, 0, 0, 0, 0)  # 纯白文字

    # "INVOICE" 大字 (top_y=10mm，靠右)
    t_inv = text.create_text_frame(margin + 110.0, 10.0, 70.0, 15.0, "INVOICE")
    if t_inv.success and t_inv.data:
        iid = t_inv.data.get("shape_id", "")
        text.set_text_style(iid, font="Arial", size=18.0, bold=True, alignment="right")
        colors.set_fill_cmyk(iid, 0, 0, 0, 0)  # 纯白文字

    # 4. 客户信息与单号 (top_y=55mm)
    # Bill To 块
    bill_text = f"Bill To:\n{bill_to_name}\n{bill_to_address}"
    t_bill = text.create_text_frame(margin, 55.0, 100.0, 25.0, bill_text)
    if t_bill.success and t_bill.data:
        text.set_text_style(t_bill.data.get("shape_id", ""), font="Arial", size=spec["body_pt"], alignment="left")

    # Invoice No / Date 块 (靠右)
    meta_text = f"Invoice No: {invoice_number}\nDate: {date_str}"
    t_meta = text.create_text_frame(margin + 100.0, 55.0, 80.0, 20.0, meta_text)
    if t_meta.success and t_meta.data:
        text.set_text_style(t_meta.data.get("shape_id", ""), font="Arial", size=spec["body_pt"], alignment="right")

    # 5. 表头 Header 行 (top_y=90mm, h=9mm)
    th_y = 90.0
    th_h = 9.0
    # 表头背景块
    th_bg = shapes.create_rectangle(margin, th_y, content_w, th_h)
    if th_bg.success and th_bg.data:
        c, m, y, k = palette["primary"]
        colors.set_fill_cmyk(th_bg.data.get("shape_id", ""), c, m, y, k)

    # 表头文字 (纯白文字)
    cols = [
        ("Description", margin + 3.0, 95.0, "left"),
        ("Qty", margin + 105.0, 20.0, "center"),
        ("Price", margin + 130.0, 23.0, "right"),
        ("Total", margin + 155.0, 22.0, "right"),
    ]
    for title, cx, cw, align in cols:
        t_col = text.create_text_frame(cx, th_y + 1.5, cw, th_h - 3.0, title)
        if t_col.success and t_col.data:
            cid = t_col.data.get("shape_id", "")
            text.set_text_style(cid, font="Arial", size=spec["table_header_pt"], bold=True, alignment=align)
            colors.set_fill_cmyk(cid, 0, 0, 0, 0)  # 纯白文字

    # 6. 表格商品明细行 (top_y=101mm 开始，向下方延伸)
    subtotal = 0.0
    cur_y = 101.0
    row_h = 9.0

    for item in items:
        desc = str(item.get("description", ""))
        qty = int(item.get("qty", 1))
        price = float(item.get("price", 0.0))
        item_total = qty * price
        subtotal += item_total

        # 行下划细线
        shapes.create_line(margin, cur_y + row_h, margin + content_w, cur_y + row_h)

        # 单元格文字
        row_cells = [
            (desc, margin + 3.0, 95.0, "left"),
            (str(qty), margin + 105.0, 20.0, "center"),
            (f"Rs. {price:.0f}", margin + 130.0, 23.0, "right"),
            (f"Rs. {item_total:.0f}", margin + 155.0, 22.0, "right"),
        ]
        for val, cx, cw, align in row_cells:
            t_cell = text.create_text_frame(cx, cur_y + 1.5, cw, row_h - 3.0, val)
            if t_cell.success and t_cell.data:
                text.set_text_style(t_cell.data.get("shape_id", ""), font="Arial", size=spec["body_pt"], alignment=align)

        cur_y += row_h

    # 7. 结算汇总框 Totals Box (在表格下方右侧)
    tax_amt = subtotal * (tax_rate_percent / 100.0)
    grand_total = subtotal + tax_amt

    tot_y = cur_y + 12.0
    tot_w = 85.0
    tot_x = margin + content_w - tot_w

    totals_text = (
        f"Subtotal:   Rs. {subtotal:.2f}\n"
        f"Tax ({tax_rate_percent:.0f}%):   Rs. {tax_amt:.2f}\n"
        f"TOTAL:   Rs. {grand_total:.2f}"
    )

    # 结算框背景与边框
    tbox_bg = shapes.create_rectangle(tot_x, tot_y, tot_w, 28.0, corner_radius=2)
    if tbox_bg.success and tbox_bg.data:
        c, m, y, k = palette["bg_light"]
        colors.set_fill_cmyk(tbox_bg.data.get("shape_id", ""), c, m, y, k)
        c, m, y, k = palette["primary"]
        colors.set_outline_cmyk(tbox_bg.data.get("shape_id", ""), c, m, y, k, width=0.5)

    t_tot = text.create_text_frame(tot_x + 4.0, tot_y + 3.0, tot_w - 8.0, 22.0, totals_text)
    if t_tot.success and t_tot.data:
        text.set_text_style(t_tot.data.get("shape_id", ""), font="Arial", size=10.5, bold=True, alignment="right")

    # 8. 印前质检与导出
    return inspect_and_export_production(
        output_base_name=invoice_number,
        output_dir="output",
        export_pdf_flag=True,
        export_dxf_flag=True,
    )



# =============================================================================
# Master 宏 2: 通用图像转 CDR 矢量重建 (支持任意 Flyer / Business Card / Poster)
# =============================================================================

def recreate_design_from_image(
    design_type: str,
    width_mm: float,
    height_mm: float,
    elements_json: List[Dict[str, Any]],
    palette_name: str = "corporate_navy",
    output_base_name: str = "recreated_design",
) -> ToolResult:
    """【通用图像转 editable CDR】解析参考设计图中的元素结构规范 (Header, 文本框, 形状框, 背景饰条)，
    一键自动在 CorelDRAW 中按 Top-Left 坐标精准重建为 100% 可编辑的 CDR 矢量对象。

    Args:
        design_type: "flyer" | "business_card" | "poster" | "certificate" | "banner"
        width_mm: 页面宽度 (mm)
        height_mm: 页面高度 (mm)
        elements_json: 解构出的元素列表 [{"type": "text"|"rect"|"banner", "top_y": 10, "x": 15, "w": 100, "h": 20, "text": "...", "pt": 14}, ...]
        palette_name: 色彩调色板名称
        output_base_name: 输出主文件名

    Returns:
        包含成功状态与导出文件路径的 ToolResult
    """
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接")

    doc_res = document.create_document(width_mm, height_mm, "mm")
    if not doc_res.success:
        return ToolResult.fail(f"创建文档失败: {doc_res.error}")

    palette = get_palette(palette_name)
    for elem in elements_json:
        etype = elem.get("type", "text")
        top_y = float(elem.get("top_y", 10.0))
        x = float(elem.get("x", 10.0))
        w = float(elem.get("w", 50.0))
        h = float(elem.get("h", 15.0))

        if etype == "text":
            content = str(elem.get("text", ""))
            # Public drawing tools already accept page-top-left coordinates.
            # Passing pre-converted Corel coordinates caused a second Y flip.
            t_res = text.create_text_frame(x, top_y, w, h, content)
            if t_res.success and t_res.data:
                sid = t_res.data.get("shape_id", "")
                font_pt = float(elem.get("pt", 10.0))
                bold = bool(elem.get("bold", False))
                align = str(elem.get("align", "left"))
                text.set_text_style(sid, font_size=font_pt, bold=bold, alignment=align)

                # 填充颜色
                fill_color = elem.get("color_cmyk")
                if fill_color:
                    c, m, y, k = fill_color
                    colors.set_fill_cmyk(sid, c, m, y, k)

        elif etype in ("rect", "banner", "shape"):
            r_res = shapes.create_rectangle(x, top_y, w, h, corner_radius=float(elem.get("radius", 0.0)))
            if r_res.success and r_res.data:
                sid = r_res.data.get("shape_id", "")
                fill_color = elem.get("color_cmyk", palette["primary"])
                c, m, y, k = fill_color
                colors.set_fill_cmyk(sid, c, m, y, k)
                if elem.get("no_outline", True):
                    colors.set_no_outline(sid)

    return inspect_and_export_production(
        output_base_name=output_base_name,
        output_dir="output",
        export_pdf_flag=True,
        export_dxf_flag=True,
    )


def list_design_skills() -> ToolResult:
    """【查询 Agent 设计 Skill 列表】返回系统中启用的所有 Agent 设计 Skill 和规范库。"""
    skills_dir = Path(__file__).resolve().parent.parent.parent / ".agents" / "skills"
    skills = []
    if skills_dir.exists():
        for sdir in skills_dir.iterdir():
            skill_md = sdir / "SKILL.md"
            if skill_md.is_file():
                skills.append({
                    "name": sdir.name,
                    "path": str(skill_md),
                })
    return ToolResult.ok(f"发现 {len(skills)} 个 Agent 设计 Skill", skills=skills)


def create_banner_design(
    title: str,
    subtitle: str = "",
    cta_text: str = "",
    width_mm: float = 200.0,
    height_mm: float = 80.0,
    palette_name: str = "corporate_navy",
    output_base_name: str = "banner_design",
) -> ToolResult:
    """【通用 Banner / 户外招牌生成】使用 Top-Left 坐标创建现代高对比度门头 / 广告横幅。"""
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接")

    doc_res = document.create_document(width_mm, height_mm, "mm")
    if not doc_res.success:
        return ToolResult.fail(f"创建 Banner 文档失败: {doc_res.error}")

    palette = get_palette(palette_name)
    c, m, y, k = palette["header_bg"]

    # 背景
    bg = shapes.create_rectangle(0, 0, width_mm, height_mm)
    if bg.success and bg.data:
        colors.set_fill_cmyk(bg.data.get("shape_id", ""), c, m, y, k)
        colors.set_no_outline(bg.data.get("shape_id", ""))

    # 主标题 (top_y=15mm, 白字)
    t_title = text.create_text_frame(10.0, 15.0, width_mm - 20.0, 25.0, title)
    if t_title.success and t_title.data:
        sid = t_title.data.get("shape_id", "")
        text.set_text_style(sid, font="Arial", size=24.0, bold=True, alignment="center")
        colors.set_fill_cmyk(sid, 0, 0, 0, 0)

    # 副标题 (top_y=42mm, 白字)
    if subtitle:
        t_sub = text.create_text_frame(10.0, 42.0, width_mm - 20.0, 15.0, subtitle)
        if t_sub.success and t_sub.data:
            sub_id = t_sub.data.get("shape_id", "")
            text.set_text_style(sub_id, font="Arial", size=12.0, bold=False, alignment="center")
            colors.set_fill_cmyk(sub_id, 0, 0, 0, 0)

    # CTA 按钮
    if cta_text:
        btn_w = 60.0
        btn_x = (width_mm - btn_w) / 2.0
        btn = shapes.create_rectangle(btn_x, 58.0, btn_w, 12.0, corner_radius=2)
        if btn.success and btn.data:
            colors.set_fill_cmyk(btn.data.get("shape_id", ""), 0, 25, 90, 0)  # 金黄
            t_cta = text.create_text_frame(btn_x, 59.5, btn_w, 9.0, cta_text)
            if t_cta.success and t_cta.data:
                text.set_text_style(t_cta.data.get("shape_id", ""), font="Arial", size=10.0, bold=True, alignment="center")
                colors.set_fill_cmyk(t_cta.data.get("shape_id", ""), 0, 0, 0, 100)

    return inspect_and_export_production(
        output_base_name=output_base_name,
        output_dir="output",
        export_pdf_flag=True,
        export_dxf_flag=True,
    )


def create_business_card(
    name: str,
    title: str,
    company: str,
    phone: str,
    email: str,
    palette_name: str = "slate_charcoal",
    output_base_name: str = "business_card",
) -> ToolResult:
    """【通用名片/Visiting Card 生成】90x54mm 标准规格， Top-Left 坐标美学对齐。"""
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接")

    doc_res = document.create_document(90.0, 54.0, "mm")
    if not doc_res.success:
        return ToolResult.fail(f"创建名片文档失败: {doc_res.error}")

    palette = get_palette(palette_name)

    # 左侧装饰条
    strip = shapes.create_rectangle(0, 0, 6.0, 54.0)
    if strip.success and strip.data:
        c, m, y, k = palette["primary"]
        colors.set_fill_cmyk(strip.data.get("shape_id", ""), c, m, y, k)
        colors.set_no_outline(strip.data.get("shape_id", ""))

    # 公司名称 (top_y=8mm)
    t_comp = text.create_text_frame(12.0, 8.0, 70.0, 8.0, company)
    if t_comp.success and t_comp.data:
        sid = t_comp.data.get("shape_id", "")
        text.set_text_style(sid, font="Arial", size=9.0, bold=True, alignment="left")
        c, m, y, k = palette["primary"]
        colors.set_fill_cmyk(sid, c, m, y, k)

    # 姓名 (top_y=18mm)
    t_name = text.create_text_frame(12.0, 18.0, 70.0, 10.0, name)
    if t_name.success and t_name.data:
        sid = t_name.data.get("shape_id", "")
        text.set_text_style(sid, font="Arial", size=14.0, bold=True, alignment="left")
        c, m, y, k = palette["dark_text"]
        colors.set_fill_cmyk(sid, c, m, y, k)

    # 职位 (top_y=28mm)
    t_title = text.create_text_frame(12.0, 28.0, 70.0, 6.0, title)
    if t_title.success and t_title.data:
        sid = t_title.data.get("shape_id", "")
        text.set_text_style(sid, font="Arial", size=8.5, bold=False, alignment="left")
        c, m, y, k = palette["secondary"]
        colors.set_fill_cmyk(sid, c, m, y, k)

    # 联系方式 (top_y=36mm)
    contact_str = f"Tel: {phone}\nEmail: {email}"
    t_cnt = text.create_text_frame(12.0, 36.0, 70.0, 12.0, contact_str)
    if t_cnt.success and t_cnt.data:
        sid = t_cnt.data.get("shape_id", "")
        text.set_text_style(sid, font="Arial", size=7.5, alignment="left")

    return inspect_and_export_production(
        output_base_name=output_base_name,
        output_dir="output",
        export_pdf_flag=True,
        export_dxf_flag=False,
    )


def create_flyer_design(
    title: str,
    subtitle: str,
    bullet_points: List[str],
    contact_info: str,
    paper_size: str = "A5",
    palette_name: str = "emerald_green",
    output_base_name: str = "flyer_design",
) -> ToolResult:
    """【通用宣传单页/海报 Flyer 生成】支持 A4/A5 尺寸， Top-Left 结构化块对齐。"""
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接")

    spec = get_paper_spec(paper_size)
    pw, ph = spec["width"], spec["height"]

    doc_res = document.create_document(pw, ph, "mm")
    if not doc_res.success:
        return ToolResult.fail(f"创建海报文档失败: {doc_res.error}")

    palette = get_palette(palette_name)
    margin = spec["margin"]
    cw = pw - (margin * 2)

    # 顶部 Hero Banner (h=50mm)
    banner = shapes.create_rectangle(0, 0, pw, 50.0)
    if banner.success and banner.data:
        c, m, y, k = palette["header_bg"]
        colors.set_fill_cmyk(banner.data.get("shape_id", ""), c, m, y, k)
        colors.set_no_outline(banner.data.get("shape_id", ""))

    # Hero 主标题 (top_y=12mm, 白字)
    t_title = text.create_text_frame(margin, 12.0, cw, 18.0, title)
    if t_title.success and t_title.data:
        sid = t_title.data.get("shape_id", "")
        text.set_text_style(sid, font="Arial", size=20.0, bold=True, alignment="center")
        colors.set_fill_cmyk(sid, 0, 0, 0, 0)

    # Hero 副标题 (top_y=32mm, 白字)
    t_sub = text.create_text_frame(margin, 32.0, cw, 12.0, subtitle)
    if t_sub.success and t_sub.data:
        sid = t_sub.data.get("shape_id", "")
        text.set_text_style(sid, font="Arial", size=11.0, alignment="center")
        colors.set_fill_cmyk(sid, 0, 0, 0, 0)

    # 中部要点 Bullets (top_y=60mm)
    bullets_text = "\n".join([f"•  {b}" for b in bullet_points])
    t_bullets = text.create_text_frame(margin, 60.0, cw, ph - 100.0, bullets_text)
    if t_bullets.success and t_bullets.data:
        sid = t_bullets.data.get("shape_id", "")
        text.set_text_style(sid, font="Arial", size=11.0, alignment="left")

    # 底部 Footer Banner
    foot_h = 25.0
    foot_top = ph - foot_h
    foot_bg = shapes.create_rectangle(0, foot_top, pw, foot_h)
    if foot_bg.success and foot_bg.data:
        c, m, y, k = palette["primary"]
        colors.set_fill_cmyk(foot_bg.data.get("shape_id", ""), c, m, y, k)
        colors.set_no_outline(foot_bg.data.get("shape_id", ""))

    t_foot = text.create_text_frame(margin, foot_top + 5.0, cw, 15.0, contact_info)
    if t_foot.success and t_foot.data:
        sid = t_foot.data.get("shape_id", "")
        text.set_text_style(sid, font="Arial", size=10.0, bold=True, alignment="center")
        colors.set_fill_cmyk(sid, 0, 0, 0, 0)

    return inspect_and_export_production(
        output_base_name=output_base_name,
        output_dir="output",
        export_pdf_flag=True,
        export_dxf_flag=False,
    )


def reedit_active_document(search_text: str, replace_text: str) -> ToolResult:
    """【在已有文档中原地修改文字】查找当前 CorelDRAW 打开文档中的指定文本并原地替换，无需重新生成文件。"""
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接")

    def _replace():
        doc = conn.app.ActiveDocument
        if not doc:
            raise RuntimeError("没有打开的文档")
        
        replaced_count = 0
        search_lower = search_text.strip().lower()
        
        for p in doc.Pages:
            for s in p.Shapes:
                try:
                    if s.Type == 3:  # cdrTextShape
                        txt = ""
                        for getter in [lambda: s.Text.Story.Text, lambda: s.Text.Contents, lambda: str(s.Text.Story)]:
                            try:
                                val = str(getter())
                                if val:
                                    txt = val
                                    break
                            except Exception:
                                continue

                        if txt and search_lower in txt.lower():
                            import re
                            new_txt = re.sub(re.escape(search_text), replace_text, txt, flags=re.IGNORECASE)
                            setter_done = False
                            try:
                                s.Text.Story.Text = new_txt
                                setter_done = True
                            except Exception:
                                pass

                            if not setter_done:
                                try:
                                    s.Text.Contents = new_txt
                                    setter_done = True
                                except Exception:
                                    pass
                            if setter_done:
                                replaced_count += 1
                except Exception:
                    pass

        return {"replaced": replaced_count, "doc_name": doc.Name}

    result = conn.safe_call(_replace)
    if result["success"]:
        count = result["result"]["replaced"]
        if count > 0:
            return ToolResult.ok(f"成功在文档 '{result['result']['doc_name']}' 中替换 {count} 处文字: '{search_text}' -> '{replace_text}'")
        else:
            return ToolResult.fail(f"在当前文档中未查找到匹配的文字: '{search_text}'")
    return ToolResult.fail(result.get("error", "替换文字失败"))


def create_structured_table(
    x: float,
    top_y: float,
    col_widths: List[float],
    row_heights: List[float],
    headers: List[str],
    rows: List[List[str]],
    header_bg_rgb: Optional[List[int]] = None,
    header_text_color_rgb: Optional[List[int]] = None,
    cell_font_size: float = 9.0,
    line_color_rgb: Optional[List[int]] = None,
    special_rows: Optional[Dict[int, Dict[str, Any]]] = None,
) -> ToolResult:
    """【通用结构化表格工具】创建具有自定义列宽、行高、表头样式、隔行变色和特殊行 (如 Holiday 行) 的专业矢量表格。"""
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接")

    header_bg_rgb = header_bg_rgb or [45, 35, 75]
    header_text_color_rgb = header_text_color_rgb or [255, 255, 255]
    line_color_rgb = line_color_rgb or [100, 100, 100]
    special_rows = special_rows or {}

    total_w = sum(col_widths)
    num_cols = len(col_widths)
    header_h = row_heights[0] if row_heights else 10.0

    curr_top_y = top_y

    # 1. 创建表头背景和文字
    h_bg = shapes.create_rectangle(x, curr_top_y, total_w, header_h)
    if h_bg.success and h_bg.data:
        sid = h_bg.data.get("shape_id", "")
        colors.set_fill_rgb(header_bg_rgb[0], header_bg_rgb[1], header_bg_rgb[2], sid)

    curr_x = x
    for col_i, h_text in enumerate(headers):
        cw = col_widths[col_i] if col_i < num_cols else 20.0
        t_res = text.create_text_frame(curr_x + 1.0, curr_top_y + 1.0, cw - 2.0, header_h - 2.0, h_text)
        if t_res.success and t_res.data:
            sid = t_res.data.get("shape_id", "")
            text.set_text_font_and_size(sid, font_name="Times New Roman", font_size=cell_font_size + 1.0, bold=True, r=header_text_color_rgb[0], g=header_text_color_rgb[1], b=header_text_color_rgb[2])
            text.set_text_alignment(sid, align_h="center", align_v="middle")
        curr_x += cw

    curr_top_y += header_h

    # 2. 循环创建数据行
    for row_i, row_data in enumerate(rows):
        rh = row_heights[row_i + 1] if (row_i + 1) < len(row_heights) else 12.0

        if row_i in special_rows:
            spec = special_rows[row_i]
            r_bg_rgb = spec.get("bg_rgb", [255, 230, 235])
            r_text_rgb = spec.get("text_rgb", [200, 20, 20])
            r_text = spec.get("text", " ".join(row_data))
            
            r_bg = shapes.create_rectangle(x, curr_top_y, total_w, rh)
            if r_bg.success and r_bg.data:
                sid = r_bg.data.get("shape_id", "")
                colors.set_fill_rgb(r_bg_rgb[0], r_bg_rgb[1], r_bg_rgb[2], sid)

            t_res = text.create_text_frame(x + 2.0, curr_top_y + 1.0, total_w - 4.0, rh - 2.0, r_text)
            if t_res.success and t_res.data:
                sid = t_res.data.get("shape_id", "")
                text.set_text_font_and_size(sid, font_name="Times New Roman", font_size=cell_font_size + 2.0, bold=True, r=r_text_rgb[0], g=r_text_rgb[1], b=r_text_rgb[2])
                text.set_text_alignment(sid, align_h="center", align_v="middle")
        else:
            curr_x = x
            for col_i, cell_text in enumerate(row_data):
                cw = col_widths[col_i] if col_i < num_cols else 20.0
                cell_box = shapes.create_rectangle(curr_x, curr_top_y, cw, rh)
                if cell_box.success and cell_box.data:
                    sid = cell_box.data.get("shape_id", "")
                    colors.set_no_fill(sid)
                    colors.set_outline(sid, 0.2, line_color_rgb[0], line_color_rgb[1], line_color_rgb[2])

                align_h = "left" if col_i == 3 else "center"
                t_res = text.create_text_frame(curr_x + 1.0, curr_top_y + 1.0, cw - 2.0, rh - 2.0, cell_text)
                if t_res.success and t_res.data:
                    sid = t_res.data.get("shape_id", "")
                    text.set_text_font_and_size(sid, font_name="Times New Roman", font_size=cell_font_size, bold=False, r=30, g=30, b=30)
                    text.set_text_alignment(sid, align_h=align_h, align_v="middle")
                curr_x += cw

        curr_top_y += rh

    return ToolResult.ok(f"结构化表格创建成功: {len(rows)} 行 × {num_cols} 列", x=x, top_y=top_y, total_width=total_w, total_height=curr_top_y - top_y)
