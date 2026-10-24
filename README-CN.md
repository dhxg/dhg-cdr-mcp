# CorelDRAW Live MCP

---

## 1. 这个项目解决什么问题

设计师每天有大量重复、机械的 CorelDRAW 操作：改文字、调颜色、批量做门牌/制度牌、满网搜图再一张张贴进去、导出各种格式……这些工作费时且容易出错。

本项目把 CorelDRAW 的 COM 接口封装成一套 **MCP 工具服务**，让 Claude Desktop、Claude Code、Cursor、VS Code 等 AI 客户端通过自然语言直接驱动本地 CorelDRAW：

- **不用切换软件**：AI 直接操作你当前已打开的设计文件
- **安全实时编辑**：所有修改走"会话 + 版本校验"，改错了可一次 Undo 恢复
- **批量自动化**：搜图、置入、排版、导出全流程一条指令完成

> **平台限制**：仅支持 Windows（CorelDRAW COM API 依赖 Windows）。MCP Server 必须和 CorelDRAW 运行在同一台 Windows 电脑上。

---

## 2. 主要功能

生产默认启用 **compact 精简工具集（28 个工具）**，覆盖日常 90% 场景：

| 功能模块 | 代表工具 | 说明 |
|---|---|---|
| 安全实时编辑 | `corel_status`、`attach_active_document`、`inspect_document`、`apply_operations`、`render_preview`、`save_current_document`、`undo_last_edit` | 附着到已打开文档 → 检查 → 原子批量修改（一次 Undo）→ 预览 → 保存，全程会话+版本校验 |
| 批量搜图置入 | `batch_search_images`、`batch_search_and_place`、`batch_place_images` | 按关键词自动搜图（长边≥1000px、自动过滤水印/动图、并行下载），一次调用 PowerClip 置入选中的框 |
| 批量数据牌/制度牌 | `parse_board_records`、`batch_system_board` | 解析 Word/Excel/纯文本数据 → 批量复制模板底板，按网格排版并替换标题正文 |
| 组织架构图 | `create_org_chart` | 输入文字/JSON 数据，自动生成纵向/横向组织架构图 |
| 图形与位图 | `import_bitmap`、`import_svg`、`trace_bitmap`、`apply_gradient_fill`、`create_curve_shape`、`duplicate_shapes`、`get_selection` | 导入位图/SVG、位图转曲线、渐变填充、按阅读顺序读取选中元素 |
| 文件管理 | `create_new_document`、`save_document_as`、`export_document` | 新建文档、另存、导出 PDF/SVG/PNG 等 |

设置环境变量 `COREL_TOOL_PROFILE=legacy` 可切换到 **legacy 完整工具集（70+ 底层工具）**，包括：

- **模板生产**：门牌/招牌（`composite`）、智能发票/横幅/名片/海报（`smart_layout`）、工程图纸（`engineering`）
- **基础绘图**：矩形/椭圆/线段、布尔运算、群组/取消群组、对齐分布、旋转缩放、PowerClip（`shapes`）
- **文字**：内容替换、样式设置、文字转曲、溢出检测（`text`）
- **颜色**：CMYK/RGB/Pantone 填色、描边、渐变、透明度、页面背景（`colors`）
- **图层**：创建/查询/分配/显隐/锁定（`layers`）
- **印前检查**：尺寸检查、文字溢出、缺字体、颜色报告（`preflight`）
- **数据合并**：读取 Excel、批量合并、条形码/二维码生成（`data_merge`）

> legacy 工具集过大可能降低 AI 选工具的准确性，日常使用推荐保持 compact。

---

## 3. 安装方法

### 环境要求

- Windows 10/11
- CorelDRAW X6 或更高版本（需已安装；正式使用前请先验证你的具体版本）
- 64 位 Python 3.11–3.13（Python 位数需与 CorelDRAW 一致）

### 安装步骤

```powershell
# 1. 创建虚拟环境
py -3.12 -m venv .venv

# 2. 激活虚拟环境
.\.venv\Scripts\Activate.ps1

# 3. 安装依赖
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 可选依赖（按需安装）

```powershell
pip install ".[agent]"       # Streamlit + 内置 LLM Agent（可选）
pip install ".[datamerge]"   # Excel 数据、条码、二维码、图片辅助
pip install ".[https]"       # 本地 HTTPS 包装（可选）
pip install ".[all]"         # 全部安装
```

---

## 4. 使用方法

### 4.1 启动 MCP Server

先启动 CorelDRAW 并打开你要操作的文档，再启动服务：

```powershell
$env:COREL_ATTACH_POLICY = "existing_only"
python server\server.py --transport stdio
```

> 服务启动时**不会自动打开 CorelDRAW**，等第一个工具被调用时才懒连接，避免打扰你当前工作。

### 4.2 配置 MCP 客户端

以 Claude Desktop 为例，在它的 MCP 配置文件中加入（把两个路径换成你电脑上的真实路径）：

```json
{
  "mcpServers": {
    "coreldraw-live": {
      "command": "C:\\path\\to\\corel-mcp\\.venv\\Scripts\\python.exe",
      "args": [
        "C:\\path\\to\\corel-mcp\\server\\server.py",
        "--transport",
        "stdio"
      ],
      "env": {
        "PYTHONUNBUFFERED": "1",
        "COREL_ATTACH_POLICY": "existing_only",
        "COREL_TOOL_PROFILE": "compact"
      }
    }
  }
}
```

参考文件：仓库根目录的 `claude_desktop_config.example.json` 和 `mcp_config_guide.md`。

### 4.3 标准工作流（安全实时编辑）

每次修改建议按此顺序调用工具：

1. `corel_status` —— 确认连接与已打开文档
2. `list_open_documents` —— 列出可用文档
3. `attach_active_document`（或 `attach_open_document`）—— 附着当前文档
4. `inspect_document` —— 查看文档结构，拿到 shape_id
5. `apply_operations` —— 用返回的 `revision` 原子批量修改
6. `render_preview` —— 需要时渲染 PNG 预览核对
7. `save_current_document` —— 仅在用户明确要求时保存
8. `detach_document` —— 结束会话

> `attach_active_document` 绝不会新建或打开文档；`save_current_document` 绝不会擅自另存新文件名。

### 4.4 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `MCP_TRANSPORT` | `stdio` | 传输模式：`stdio` / `streamable-http` / `sse` |
| `MCP_HOST` | `127.0.0.1` | HTTP/SSE 模式监听地址 |
| `MCP_PORT` | `8765` | HTTP/SSE 模式监听端口 |
| `COREL_ATTACH_POLICY` | `existing_only` | 只附着已存在的 CorelDRAW 实例 |
| `COREL_TOOL_PROFILE` | `compact` | 工具集：`compact`（精简）/ `legacy`（完整） |
| `COREL_OUTPUT_ROOT` | 无 | 限制导出/保存路径只允许在指定目录内 |

### 4.5 坐标约定

所有公开几何数据统一使用**页面左上角为原点、Y 轴向下、单位毫米**：

```json
{
  "coordinate_space": "page_top_left",
  "unit": "mm",
  "bounds": {"x": 10, "y": 20, "width": 80, "height": 30}
}
```

坐标由驱动层只转换一次，AI 与 CorelDRAW 之间不存在重复换算。

---

## 5. 输入输出示例

### 示例 1：批量搜图并置入（一条指令完成全流程）

在 CDR 里选中 N 个框，然后对 AI 说"给这 4 个框找图贴上：牛肉面、麻辣烫、炸鸡、凉皮"。AI 会依次调用：

**输入**（`batch_search_and_place`）：

```json
{
  "keywords": ["牛肉面", "麻辣烫", "炸鸡", "凉皮"],
  "container_ids": null,
  "fit_mode": "fill",
  "min_long_edge": 1000
}
```

**输出**：每个关键词搜图（自动筛选长边≥1000px、无水印、非动图）并 PowerClip 置入对应容器，返回每个容器的置入结果：

```json
{
  "ok": true,
  "placed": [
    {"keyword": "牛肉面", "container_id": "136", "image": "D:/temp/牛肉面_01.jpg", "w_px": 1200, "h_px": 800},
    {"keyword": "麻辣烫", "container_id": "137", "image": "D:/temp/麻辣烫_02.jpg", "w_px": 1000, "h_px": 1000}
  ]
}
```

### 示例 2：安全实时编辑（原子批量修改）

**输入**（`apply_operations`，把标题改为促销文字并移动到新位置）：

```json
{
  "session_id": "sess_example",
  "expected_revision": 4,
  "label": "更新促销标题",
  "operations": [
    {
      "op": "text.set_content",
      "shape_id": "128",
      "value": "SUMMER SALE"
    },
    {
      "op": "text.set_style",
      "shape_id": "128",
      "font_family": "Montserrat",
      "font_size_pt": 30,
      "bold": true
    },
    {
      "op": "shape.move",
      "shape_id": "128",
      "x": 20,
      "y": 15
    }
  ]
}
```

**输出**：整批操作作为一个原子事务执行，返回新 revision；出错时整批回滚，不会留下半改状态。

compact 工具集支持的原子操作：

- `text.set_content` / `text.set_style` / `text.create_frame`
- `shape.set_bounds` / `shape.move` / `shape.resize` / `shape.create_rectangle` / `shape.rotate` / `shape.rename` / `shape.delete`
- `fill.set_cmyk` / `fill.set_rgb`

### 示例 3：批量数据牌/制度牌

**第 1 步 —— 解析数据**（`parse_board_records`，从 Excel/Word/文本提取记录）：

**输入**：

```json
{
  "source_type": "excel",
  "file_path": "D:/data/制度牌.xlsx"
}
```

**输出**（每条含标题+正文，供 AI 核对）：

```json
{
  "ok": true,
  "records": [
    {"title": "安全生产制度", "body": "1. 进入车间必须佩戴安全帽……"},
    {"title": "消防管理制度", "body": "1. 灭火器每月检查一次……"}
  ],
  "table_count": 0
}
```

**第 2 步 —— 批量排版**（`batch_system_board`，在 CDR 里选中一个做好的模板底板）：

**输入**：

```json
{
  "records": [
    {"title": "安全生产制度", "body": "1. 进入车间必须佩戴安全帽……"},
    {"title": "消防管理制度", "body": "1. 灭火器每月检查一次……"}
  ],
  "columns": 4,
  "gap": 10.0
}
```

**输出**：原模板保留，副本从模板右侧开始按网格排列（每排 4 个、间距 10mm），标题和正文逐块替换完成。

---

## 测试

平台无关的单元测试：

```powershell
python -m unittest discover -s tests -v
python -m compileall -q server tests
```

Windows/CorelDRAW 端到端测试（需本地 CorelDRAW 已启动）：

```powershell
python server\test_e2e.py
```

> 发布前必须在 Windows + 各受支持 CorelDRAW 版本上跑过最终发布门禁；Linux 上无法验证 COM 行为。

---

## 安全

- 不要提交 `.env`、API Key、日志、客户设计稿或崩溃转储到仓库
- 本地服务只使用 stdio 或仅回环地址（loopback）网络
- 不要把 CorelDRAW COM 自动化直接暴露到公网
- 覆盖写、破坏性编辑、远程执行前必须显式确认
- 设置 `COREL_OUTPUT_ROOT` 把导出/保存限制在指定目录
- 预览/导出默认 `overwrite=false`，目标文件已存在时拒绝覆盖

---

## License

Apache License 2.0。参见 `LICENSE` 与 `NOTICE`（含原版权方玄熵智能署名与本项目附加署名 dhxg）。
