"""组合/宏工具 — 一键式完成完整的门牌生成、数据合并与导出工作流

用于简化 MCP 客户端（如 Claude Desktop / Cursor / ChatGPT）的工具调用序列，
将原先需要的 8-10 次离散工具调用收拢为 1 次高阶宏调用。
"""

import os
from pathlib import Path
from typing import Dict

from core.connection import get_connection
from core.models import ToolResult
from tools import colors, data_merge, document, export, shapes, text

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


def generate_sign_from_template(
    template_name_or_path: str,
    replacements: Dict[str, str],
    output_pdf_path: str = "",
    output_dxf_path: str = "",
    output_preview_path: str = "",
    convert_to_curves: bool = True,
    auto_fit_text: bool = True,
) -> ToolResult:
    """【一键生成门牌】从 CDR 模板打开、替换多个占位符文字、检测溢出、转曲并导出 PDF/DXF/PNG 预览图。

    Args:
        template_name_or_path: 模板文件名（位于 server/templates/）或绝对路径，如 "room_template.cdr"
        replacements: 占位符替换映射字典，例如 {"placeholder_room": "301", "placeholder_dept": "研发中心"}
        output_pdf_path: PDF 导出绝对或相对路径（为空则自动生成到 output/print/<name>.pdf）
        output_dxf_path: DXF 导出绝对或相对路径（为空则自动生成到 output/laser/<name>.dxf）
        output_preview_path: PNG 预览图路径（为空则自动生成到 output/preview/<name>.png）
        convert_to_curves: 导出前是否自动将文字转曲（建议 True）
        auto_fit_text: 发生文字溢出时是否自动自适应字号（建议 True）

    Returns:
        包含成功状态及导出的所有文件路径的 ToolResult
    """
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接，请先启动 CorelDRAW")

    # 1. 解析模板路径
    template_path = template_name_or_path
    if not os.path.isabs(template_path):
        candidate = _TEMPLATES_DIR / template_path
        if candidate.is_file():
            template_path = str(candidate)

    open_res = document.open_template(template_path)
    if not open_res.success:
        return ToolResult.fail(f"打开模板失败: {open_res.error}")

    results_detail = []

    # 2. 替换文字占位符
    for target_name, new_content in replacements.items():
        # 查找 shape
        shape_res = shapes.find_shape_by_name(target_name)
        shape_id = target_name
        if shape_res.success and shape_res.data and shape_res.data.get("found"):
            shape_id = shape_res.data.get("shape_id", target_name)

        txt_res = text.set_text_content(shape_id, str(new_content))
        if not txt_res.success:
            # 尝试通过原始名称操作
            txt_res = text.set_text_content(target_name, str(new_content))

        if txt_res.success:
            results_detail.append(f"替换 '{target_name}' → '{new_content}'")
            # 检查溢出
            overflow_res = text.check_text_overflow(shape_id)
            if overflow_res.success and overflow_res.data and overflow_res.data.get("is_overflow"):
                if auto_fit_text:
                    fit_res = text.fit_text_to_frame(shape_id)
                    if fit_res.success:
                        results_detail.append(f"  └─ 自动调整溢出文字字号成功")
        else:
            results_detail.append(f"警告：替换 '{target_name}' 失败: {txt_res.error}")

    # 准备导出路径
    base_name = replacements.get("placeholder_room", "sign_output")
    if "placeholder_room" not in replacements and replacements:
        base_name = list(replacements.values())[0]

    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)
    (out_dir / "print").mkdir(exist_ok=True)
    (out_dir / "laser").mkdir(exist_ok=True)
    (out_dir / "preview").mkdir(exist_ok=True)

    if not output_pdf_path:
        output_pdf_path = str(out_dir / "print" / f"{base_name}.pdf")
    if not output_dxf_path:
        output_dxf_path = str(out_dir / "laser" / f"{base_name}.dxf")
    if not output_preview_path:
        output_preview_path = str(out_dir / "preview" / f"{base_name}.png")

    # 3. 导出预览 PNG
    export.export_preview_png(output_preview_path, width_px=600)

    # 4. 文字转曲（在导出 PDF/DXF 前）
    if convert_to_curves:
        for target_name in replacements.keys():
            shapes.convert_to_curves(target_name)

    # 5. 导出 PDF
    pdf_res = export.export_pdf(output_pdf_path, color_profile="ISO_Coated_v2", bleed=3.0, crop_marks=True)
    
    # 6. 导出 DXF
    dxf_res = export.export_dxf(output_dxf_path, version="R14")

    # 7. 关闭文档
    document.close_document()

    exported_files = {
        "pdf": output_pdf_path if pdf_res.success else None,
        "dxf": output_dxf_path if dxf_res.success else None,
        "preview": output_preview_path if os.path.isfile(output_preview_path) else None,
    }

    return ToolResult.ok(
        f"门牌 '{base_name}' 生成成功！",
        files=exported_files,
        details=results_detail,
        pdf_success=pdf_res.success,
        dxf_success=dxf_res.success,
    )


def batch_generate_signs(
    excel_path: str,
    template_name_or_path: str,
    output_dir: str = "output",
    filename_column: str = "room",
) -> ToolResult:
    """【批量合并门牌】读取 Excel 数据表，循环替换模板占位符并批量生成 PDF 和 DXF 生产文件。

    Args:
        excel_path: Excel 数据文件路径 (.xlsx 或 .xls)
        template_name_or_path: CDR 模板文件路径或名称
        output_dir: 文件输出总目录，默认 "output"
        filename_column: 用作导出文件名的 Excel 列名（如 "room" 或 "id"）

    Returns:
        包含成功数、失败数及输出目录信息的 ToolResult
    """
    read_res = data_merge.read_excel_data(excel_path)
    if not read_res.success or not read_res.data:
        return ToolResult.fail(f"读取 Excel 数据失败: {read_res.error}")

    records = read_res.data.get("records", [])
    if not records:
        return ToolResult.fail("Excel 表中没有任何有效记录")

    success_count = 0
    fail_count = 0
    details = []

    for idx, record in enumerate(records, 1):
        # 尝试构建 filename
        file_key = str(record.get(filename_column, record.get("room", record.get("Room", f"sign_{idx}"))))
        
        # 将 Excel 字段转化为 placeholder_xxx
        replacements = {}
        for col, val in record.items():
            if str(col).startswith("placeholder_"):
                replacements[str(col)] = str(val)
            else:
                replacements[f"placeholder_{col}"] = str(val)
                replacements[str(col)] = str(val)

        pdf_path = os.path.join(output_dir, "print", f"{file_key}.pdf")
        dxf_path = os.path.join(output_dir, "laser", f"{file_key}.dxf")
        preview_path = os.path.join(output_dir, "preview", f"{file_key}.png")

        res = generate_sign_from_template(
            template_name_or_path=template_name_or_path,
            replacements=replacements,
            output_pdf_path=pdf_path,
            output_dxf_path=dxf_path,
            output_preview_path=preview_path,
        )

        if res.success:
            success_count += 1
            details.append(f"✅ 第 {idx} 条 [{file_key}]: 成功")
        else:
            fail_count += 1
            details.append(f"❌ 第 {idx} 条 [{file_key}]: 失败 - {res.error}")

    return ToolResult.ok(
        f"批量处理完成！共 {len(records)} 条：{success_count} 成功，{fail_count} 失败",
        total=len(records),
        success_count=success_count,
        fail_count=fail_count,
        output_dir=output_dir,
        details=details,
    )


def quick_create_sign(
    width_mm: float,
    height_mm: float,
    room_number: str,
    department_name: str,
    bg_cmyk: str = "0,0,0,80",
    text_cmyk: str = "0,0,0,0",
    output_pdf_path: str = "",
    output_dxf_path: str = "",
) -> ToolResult:
    """【零模板快速建牌】无模板情况下，根据长宽尺寸、房间号、部门名称快速画框、写字并导出生产稿。

    Args:
        width_mm: 门牌宽度 (mm)
        height_mm: 门牌高度 (mm)
        room_number: 房间号 (如 "301")
        department_name: 部门名称 (如 "研发中心")
        bg_cmyk: 背景色 CMYK 格式 "C,M,Y,K"，默认 "0,0,0,80" (深灰)
        text_cmyk: 文字 CMYK 格式 "C,M,Y,K"，默认 "0,0,0,0" (白色)
        output_pdf_path: PDF 导出路径
        output_dxf_path: DXF 导出路径

    Returns:
        包含成功状态与导出文件路径的 ToolResult
    """
    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接，请先启动 CorelDRAW")

    # 1. 创建新文档
    doc_res = document.create_document(width_mm, height_mm, "mm")
    if not doc_res.success:
        return ToolResult.fail(f"创建文档失败: {doc_res.error}")

    # 2. 画背景矩形
    bg_res = shapes.create_rectangle(0, 0, width_mm, height_mm, corner_radius=3)
    if bg_res.success and bg_res.data:
        bg_id = bg_res.data.get("shape_id", "")
        # 解析 CMYK
        try:
            c, m, y, k = [int(x.strip()) for x in bg_cmyk.split(",")]
            colors.set_fill_cmyk(bg_id, c, m, y, k)
        except Exception:
            pass

    # 3. 创建房间号文字 (顶部)
    room_y = height_mm * 0.45
    room_h = height_mm * 0.45
    tf_room = text.create_text_frame(10, room_y, width_mm - 20, room_h, room_number)
    if tf_room.success and tf_room.data:
        rid = tf_room.data.get("shape_id", "")
        shapes.find_shape_by_name(rid)
        try:
            c, m, y, k = [int(x.strip()) for x in text_cmyk.split(",")]
            colors.set_fill_cmyk(rid, c, m, y, k)
        except Exception:
            pass

    # 4. 创建部门名称文字 (底部)
    dept_y = height_mm * 0.1
    dept_h = height_mm * 0.3
    tf_dept = text.create_text_frame(10, dept_y, width_mm - 20, dept_h, department_name)
    if tf_dept.success and tf_dept.data:
        did = tf_dept.data.get("shape_id", "")
        try:
            c, m, y, k = [int(x.strip()) for x in text_cmyk.split(",")]
            colors.set_fill_cmyk(did, c, m, y, k)
        except Exception:
            pass

    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)
    (out_dir / "print").mkdir(exist_ok=True)
    (out_dir / "laser").mkdir(exist_ok=True)

    if not output_pdf_path:
        output_pdf_path = str(out_dir / "print" / f"{room_number}.pdf")
    if not output_dxf_path:
        output_dxf_path = str(out_dir / "laser" / f"{room_number}.dxf")

    # 转曲
    if tf_room.success and tf_room.data:
        text.convert_text_to_curves(tf_room.data.get("shape_id", ""))
    if tf_dept.success and tf_dept.data:
        text.convert_text_to_curves(tf_dept.data.get("shape_id", ""))

    # 导出
    pdf_res = export.export_pdf(output_pdf_path, bleed=3.0, crop_marks=True)
    dxf_res = export.export_dxf(output_dxf_path)

    document.close_document()

    return ToolResult.ok(
        f"快速创建门牌 '{room_number}' 完成 ({width_mm}×{height_mm}mm)",
        pdf_path=output_pdf_path if pdf_res.success else None,
        dxf_path=output_dxf_path if dxf_res.success else None,
    )
