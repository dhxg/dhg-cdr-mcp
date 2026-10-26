# 组织架构图（区域内自动绘制，框+文字+正交连线一次成型）

`create_org_chart`：在用户指定区域内，把组织树画成标准架构图——圆角框、框内居中文字、父子之间正交折线连接，**严格按区域尺寸等比缩放、整体居中、不溢出**，画完可逐个编辑。

## 流程

**第 1 步：让用户先指定绘制区域（🔴 优先让工具自动读选中框）**
- 让用户在 CDR 里**选中要放架构图的矩形框并保持选中**，然后**直接调 `create_org_chart`、不传 region**——工具自动读当前选中框作为区域，把图（含标题）画在框内。这是最可靠的方式，避免中间选中状态丢失或坐标映射出错。
- 也可用 `region_shape_id` 指定某个框；或先 `get_selection` 取选中框的 `left_x_mm/top_y_mm/width_mm/height_mm` 拼 region（x=left_x_mm，y=top_y_mm，width=width_mm，height=height_mm）传入；用户也可直接给区域尺寸。
- 工具会在区域四周自动留 3mm 安全边距，内容不贴边、不溢出。
- 提示"没有找到绘制区域"则让用户先选中框再调。必须先确定区域。

**第 2 步：拿组织数据（三种给法都支持）**
1. **大白话**："总经理下面 3 个副总，第一个副总管安全部、综合部、市场部……" → 你整理成树。
2. **缩进文本**：每行一个职位，用空格/Tab 表示层级（传给 `text`）。
3. **Excel/结构化数据**：整理成嵌套树（传给 `data`）。
4. （特殊）用户已在 CDR 摆好框、只需对齐连线——本工具暂不支持，告知用户。

**第 3 步：把整理好的层级关系给用户核对**（确认没漏人、没排错、单根），用户确认后再画。

**第 4 步：确定方向（🔴 必须用弹窗数字选项，禁止输入框让用户手输）**
- 用 `interaction.ask` 弹窗、**带 display_option（可点击按钮）**，display_message 同时用 1/2 编号：
  - question_id：`org_direction`；header：`横版/竖版`
  - display_message：`请选择架构图方向（我给出了建议）：`
  - 选项：
    1. option_id `vertical`，label `竖版（从上到下）`，description：`适合宽而浅、每层人多的结构（底层一排多个部门）。`
    2. option_id `horizontal`，label `横版（从左到右）`，description：`适合窄而深、层级多的结构（一级一级往下）。`
- display_message 里给出推荐（宽浅选竖、深窄选横）；**禁止自由输入框手输方向**。

**第 5 步：选风格（🔴 必须弹窗数字选项，禁止输入框）**
- 用 `interaction.ask` 弹窗、带 display_option，display_message 用 1-7 编号：
  - question_id：`org_style`；header：`架构图风格`
  - display_message：`请选择架构图风格：`
  - 选项：
    1. option_id `orange`，label `橙金商务风`，description：`浅米黄底+橙色描边，最通用（默认推荐）。`
    2. option_id `blue`，label `经典商务蓝`，description：`浅蓝底+蓝色描边，正式稳重。`
    3. option_id `gray`，label `简约灰边风`，description：`白底+灰色描边，简洁干净。`
    4. option_id `solid`，label `实色填充风`，description：`深色底+白字，对比强烈。`
    5. option_id `green`，label `绿色清新风`，description：`浅绿底+绿色描边。`
    6. option_id `blackgold`，label `黑金高端风`，description：`黑底+金色描边，高端质感。`
    7. option_id `custom`，label `自定义`，description：`你描述颜色，我用 custom_style 实现。`
- **禁止自由输入框手输风格**。

**第 6 步：确认大标题（用户忘了也要主动提醒，用"输入文字"，不是数字选项）**
- 用户已在提示词给标题 → 直接用，进入第 7 步。
- 用户没给 → 主动提醒，用 `interaction.ask` 的**自由输入题（不带 display_option、不给 1/2/3）**，让用户直接输入：
  - question_id：`org_title`；header：`大标题`
  - display_message：`需要在架构图顶部加一个大标题吗？需要的话，请直接把标题文字发给我（例如“XX公司组织架构图”）；不需要就回复“不需要”。`
- 用户输入标题 → 用它；回复"不需要/不用" → 不加。
- 标题默认加大加粗深色（`title_style="dark"`）；想换主题色或自定义会在输入时说明。

**第 7 步：调 `create_org_chart` 一次绘制**
- 关键参数：`data`（嵌套树）或 `text`（缩进文本，二选一）、`direction`、`region`、`style`；
- 可选：`font_family`（默认微软雅黑）、`base_font_pt`（默认 12，按区域缩放）、`h_gap`/`v_gap`（同级/层间间距）、`corner_radius`、`custom_style`。
- **大标题**：第 6 步拿到的标题传 `title`；标题画在区域内顶部居中、加粗，架构图自动缩小下移、整体仍在区域内；标题样式用 `title_style`（`dark` 默认 / `theme` 主色 / `custom` 配合 `title_color`）；标题过长自动收字号保证不换行。
- 工具自动等比缩放、居中；区域过小导致字号低于 7pt 会**直接报错**并建议换方向/扩大区域，不会留半成品。

**第 8 步：成功后不渲染预览，直接提醒在 CDR 查看**；不要调 `render_preview`，提示"已绘制完成，请在 CDR 中查看"。不自动保存；用户说改字/换风格/改标题，再按框编辑。
