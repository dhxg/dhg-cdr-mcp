import argparse
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from fastmcp import FastMCP
from loguru import logger

load_dotenv(Path(__file__).parent.parent / ".env")

from core.connection import close_connection, init_connection


def _auto_install_skill():
    """MCP启动时自动把skill文件复制到豆包的user_skills目录（不覆盖用户已有版本）。"""
    try:
        import shutil
        repo_skill_dir = Path(__file__).resolve().parent.parent / "skill" / "corel-cdr-operator"
        if not repo_skill_dir.exists():
            return
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        if not local_appdata:
            return
        doubao_skills_dir = Path(local_appdata) / "Doubao" / "User Data" / "Default" / ".doubao" / "agent_mode" / "workspace" / ".user_skills" / "corel-cdr-operator"
        if doubao_skills_dir.exists():
            return  # 已经存在，不覆盖用户自定义内容
        doubao_skills_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(repo_skill_dir, doubao_skills_dir)
        logger.info(f"已自动安装corel-cdr-operator skill到: {doubao_skills_dir}")
    except Exception as e:
        logger.debug(f"自动安装skill跳过: {e}")


_auto_install_skill()

_MCP_TRANSPORT = os.environ.get("MCP_TRANSPORT", "stdio")
_MCP_HOST = os.environ.get("MCP_HOST", "127.0.0.1")
_MCP_PORT = int(os.environ.get("MCP_PORT", "8765"))

mcp = FastMCP("coreldraw-live")


def _register_tool(function):
    """Register a callable across supported FastMCP 2.x/3.x APIs."""
    # The decorator form is stable across FastMCP 2.x and 3.x and avoids the
    # version-dependent add_tool(Tool) vs add_tool(callable) signature.
    mcp.tool()(function)


def setup_logging(is_stdio: bool = False):
    logger.remove()
    log_dir = Path(__file__).resolve().parent / "logs"
    log_dir.mkdir(exist_ok=True)
    if not is_stdio:
        logger.add(
            sys.stderr,
            level="INFO",
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        )
    logger.add(
        log_dir / "server.log",
        rotation="10 MB",
        retention="7 days",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function} - {message}",
    )



def register_tools():
    from tools import live, search, shapes, board, proofread

    # Compact is the production default: a small, session-safe tool surface is
    # more reliable across models.  Set COREL_TOOL_PROFILE=legacy to expose the
    # original 70+ low-level tools during migration.
    compact_tools = [
        live.corel_status,
        live.list_open_documents,
        live.attach_active_document,
        live.attach_open_document,
        live.create_new_document,
        live.inspect_document,
        live.apply_operations,
        live.render_preview,
        live.undo_last_edit,
        live.redo_last_edit,
        live.save_current_document,
        live.save_document_as,
        live.export_document,
        live.detach_document,
        shapes.import_bitmap,
        shapes.import_svg,
        shapes.replace_bitmap,
        shapes.create_curve_shape,
        shapes.apply_gradient_fill,
        shapes.trace_bitmap,
        shapes.duplicate_shapes,
        shapes.get_selection,
        shapes.batch_place_images,
        search.batch_search_images,
        search.batch_search_and_place,
        shapes.create_org_chart,
        board.parse_board_records,
        board.batch_system_board,
        proofread.extract_selected_text,
        proofread.mark_text_errors,
        proofread.restore_marked_colors,
        proofread.fix_text_errors,
    ]
    for tool in compact_tools:
        _register_tool(tool)

    if os.environ.get("COREL_TOOL_PROFILE", "compact").lower() != "legacy":
        return

    # Legacy compatibility catalog.
    from tools import (
        colors,
        composite,
        data_merge,
        document,
        engineering,
        export,
        layers,
        preflight,
        shapes,
        smart_layout,
        templates,
        text,
    )
    _register_tool(smart_layout.create_smart_invoice)
    _register_tool(smart_layout.create_banner_design)
    _register_tool(smart_layout.create_business_card)
    _register_tool(smart_layout.create_flyer_design)
    _register_tool(smart_layout.recreate_design_from_image)
    _register_tool(smart_layout.plan_design_layout)
    _register_tool(smart_layout.apply_visual_styling)
    _register_tool(smart_layout.inspect_and_export_production)
    _register_tool(smart_layout.list_design_skills)
    _register_tool(smart_layout.reedit_active_document)



    _register_tool(composite.generate_sign_from_template)
    _register_tool(composite.batch_generate_signs)
    _register_tool(composite.quick_create_sign)

    _register_tool(document.open_template)
    _register_tool(document.create_document)
    _register_tool(document.save_document)
    _register_tool(document.close_document)
    _register_tool(document.add_page)
    _register_tool(document.set_page_size)
    _register_tool(document.get_document_info)
    _register_tool(document.list_all_text_shapes)
    _register_tool(document.add_guideline)
    _register_tool(document.switch_page)
    _register_tool(document.delete_page)

    _register_tool(shapes.create_rectangle)
    _register_tool(shapes.create_ellipse)
    _register_tool(shapes.create_line)
    _register_tool(shapes.set_shape_size)
    _register_tool(shapes.set_shape_position)
    _register_tool(shapes.boolean_operation)
    _register_tool(shapes.convert_to_curves)
    _register_tool(shapes.group_shapes)
    _register_tool(shapes.find_shape_by_name)
    _register_tool(shapes.align_shapes)
    _register_tool(shapes.distribute_shapes)
    _register_tool(shapes.set_z_order)
    _register_tool(shapes.delete_shape)
    _register_tool(shapes.rotate_shape)
    _register_tool(shapes.ungroup_shapes)
    _register_tool(shapes.scale_shape)
    _register_tool(shapes.select_shapes)
    _register_tool(shapes.powerclip)

    _register_tool(text.set_text_content)
    _register_tool(text.set_text_style)
    _register_tool(text.fit_text_to_frame)
    _register_tool(text.check_text_overflow)
    _register_tool(text.convert_text_to_curves)
    _register_tool(text.create_text_frame)
    _register_tool(text.set_text_alignment)
    _register_tool(text.set_text_font_and_size)

    _register_tool(colors.set_fill_cmyk)
    _register_tool(colors.set_fill_rgb)
    _register_tool(colors.set_fill_pantone)
    _register_tool(colors.set_outline)
    _register_tool(colors.set_no_fill)
    _register_tool(colors.set_no_outline)
    _register_tool(colors.check_rgb_colors)
    _register_tool(colors.set_fountain_fill)
    _register_tool(colors.set_transparency)
    _register_tool(colors.set_page_background_rgb)
    _register_tool(colors.set_page_background_cmyk)
    _register_tool(colors.clear_page_background)

    _register_tool(smart_layout.create_structured_table)


    _register_tool(layers.create_layer)
    _register_tool(layers.get_layers)
    _register_tool(layers.assign_to_layer)
    _register_tool(layers.set_layer_visible)
    _register_tool(layers.lock_layer)

    _register_tool(export.export_pdf)
    _register_tool(export.export_dxf)
    _register_tool(export.export_ai)
    _register_tool(export.export_svg)
    _register_tool(export.export_png)
    _register_tool(export.export_jpeg)
    _register_tool(export.export_preview_png)
    _register_tool(export.batch_export)

    _register_tool(preflight.check_dimensions)
    _register_tool(preflight.check_text_overflow_all)
    _register_tool(preflight.check_missing_fonts)
    _register_tool(preflight.get_color_report)

    _register_tool(templates.list_templates)
    _register_tool(templates.get_template_info)
    _register_tool(templates.get_size_variant)

    _register_tool(engineering.populate_title_block)
    _register_tool(engineering.assemble_engineering_drawing)

    _register_tool(data_merge.read_excel_data)
    _register_tool(data_merge.merge_record)
    _register_tool(data_merge.batch_merge)
    _register_tool(data_merge.generate_barcode)
    _register_tool(data_merge.generate_qrcode)


def main():
    parser = argparse.ArgumentParser(description="CorelDRAW Live MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http", "sse"],
        default=_MCP_TRANSPORT,
        help="MCP Transport Protocol (stdio / streamable-http / sse)",
    )
    parser.add_argument("--host", default=_MCP_HOST, help="Host to bind for HTTP/SSE transport")
    parser.add_argument("--port", type=int, default=_MCP_PORT, help="Port to bind for HTTP/SSE transport")
    args = parser.parse_args()

    setup_logging(is_stdio=(args.transport == "stdio"))

    logger.info("CorelDRAW Live MCP v0.3.1 · 作者: dhxg")
    logger.info("Starting CorelDRAW Live MCP Server...")

    # 懒连接：启动时不主动连 CDR（避免用户没需要 CDR 时它被自动打开），
    # 等第一个 CDR 工具被调用时，get_connection() 才会连接。
    register_tools()
    profile = os.environ.get("COREL_TOOL_PROFILE", "compact").lower()
    logger.info(f"Tools registered (profile={profile})")

    transport = args.transport
    if transport != "stdio":
        logger.info(f"Network transport {transport} listening at http://{args.host}:{args.port}/mcp")

    try:
        if transport != "stdio":
            mcp.run(transport=transport, host=args.host, port=args.port)
        else:
            mcp.run(transport="stdio")
    finally:
        close_connection()
        logger.info("MCP server stopped")


if __name__ == "__main__":
    main()
