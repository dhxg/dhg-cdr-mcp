# 基础编辑：标准流程、apply_operations、定位元素

## 标准操作流程

### 第 1 步：确认连接
- 调 `corel_status` 确认 CDR 在线；CDR 没开时（你已明确要用）会自动启动，提示找不到就先手动打开 CorelDRAW。

### 第 2 步：绑定文档
- 调 `attach_active_document` 拿 `session_id`；用户指定文档名则用 `attach_open_document` 传 `name_or_path`。

### 第 3 步：查看现状（必做）
- 调 `inspect_document`（传 session_id），拿到所有形状的 `shape_id`、类型、位置、尺寸、文字内容。不能凭空猜 shape_id。

### 第 4 步：执行修改
- 调 `apply_operations`，传 `session_id`、`expected_revision`（第 3 步返回的 revision）、`label`（本次说明）、`operations`（操作数组，见下）。

### 第 5 步：预览（可选）
- 调 `render_preview` 渲染 PNG 给用户确认。

### 第 6 步：保存
- 仅用户明确要求时调 `save_current_document`。

## 坐标系统

- 原点：页面左上角；X 向右增加；Y 向下增加；单位：毫米。

## apply_operations 支持的操作

每个元素是一个操作对象，`op` 字段指定类型：

| op 名称 | 作用 | 关键参数 |
|---|---|---|
| `text.set_content` | 改文字内容 | `shape_id`, `value` |
| `text.set_style` | 改字体样式 | `shape_id`, `font_family`, `font_size_pt`, `bold` |
| `text.create_frame` | 新建文字框 | `x_mm`, `y_mm`, `width_mm`, `height_mm`, `value`, `font_family`, `font_size_pt`, `bold` |
| `shape.create_rectangle` | 画矩形 | `x_mm`, `y_mm`, `width_mm`, `height_mm`, `corner_radius` |
| `shape.create_ellipse` | 画椭圆/圆（正圆令宽=高） | `x_mm`, `y_mm`, `width_mm`, `height_mm`, `fill_rgb`, `outline_rgb`, `outline_width_pt`, `no_outline` |
| `shape.move` | 移动 | `shape_id`, `x_mm`, `y_mm` |
| `shape.resize` | 缩放 | `shape_id`, `width_mm`, `height_mm` |
| `shape.rotate` | 旋转 | `shape_id`, `angle_deg` |
| `shape.delete` | 删除（⚠️ 仅用户明确点名） | `shape_id` |
| `fill.set_cmyk` | CMYK 填色 | `shape_id`, `c`, `m`, `y`, `k`（0-100） |
| `fill.set_rgb` | RGB 填色 | `shape_id`, `r`, `g`, `b`（0-255） |

### 新建操作示例

新建文字框：
```json
{
  "op": "text.create_frame",
  "x_mm": 40, "y_mm": 80, "width_mm": 120, "height_mm": 30,
  "value": "CYBER MONDAY",
  "font_family": "Arial", "font_size_pt": 24, "bold": true
}
```

新建矩形：
```json
{
  "op": "shape.create_rectangle",
  "x_mm": 50, "y_mm": 100, "width_mm": 160, "height_mm": 90,
  "corner_radius": 8
}
```

能直接创建文字就不要让用户手动补；需要倾斜再调 `shape.rotate`。

## 定位元素（改之前怎么精准找到目标）

按优先级：

1. **🔴 用户在 CDR 选中了 → `get_selection`（最快最准）**
   - 读当前选中形状（多选、框选、群组），返回每个的 `shape_id`、类型、位置、尺寸、文字。
   - 用户说"把这个改了""改我选中的"，或有重复/难描述元素时，先调它拿 ID 再改。
   - count=0 提示用户先点选/框选，不瞎猜。
2. **用户直接描述内容/位置 → `inspect_document`**
   - 扫描整画布，按内容/位置匹配 shape_id。
3. 截图仅作辅助参考，不能直接拿到 shape_id。
