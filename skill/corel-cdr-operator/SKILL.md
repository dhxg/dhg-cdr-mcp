---
name: corel-cdr-operator
description: 操作本地 CorelDRAW 2026 设计文件。当用户提到 CDR、CorelDRAW、改字、改色、画形状、导出设计稿、批量修改设计文件、导入图片到CDR、在CDR里画图、门牌、招牌、制度牌、海报设计时自动启用。必须通过已配置的 MCP 连接器"心哥cdr效率AI操作插件"完成所有操作，绝对禁止自己写 PowerShell / Python / win32com 直接调COM连CDR。
version: 2.0
---

# CorelDRAW 操作核心规则

你已接入 CorelDRAW MCP 连接器（"心哥cdr效率AI操作插件"）。**本文件只放每次必读的硬规则和工具清单；具体功能的详细参数/流程，按需读取 `references/` 下对应文件，不要一开始就全读。**

## 🔴 硬规则（每次必守）

1. **禁止自己写代码连 CDR**：所有操作只走 MCP 工具；GetActiveObject/Dispatch 在 CDR 2026 有兼容问题，自写会卡死。工具没有的功能，直接告诉用户"还没做进 MCP"，不要绕路写脚本。
2. **🔴 严禁删除用户未明确点名的元素**：绘制/修改一律在已有画面上叠加，禁止"先清空再画"；只有用户明确说"删除/去掉/清空"才可删。拿不准就保留。
3. **🔴 严禁自动保存**：临摹/导入/修改后不主动调保存、不说"我帮你存到某盘"；只有用户明确说"保存/另存为/存到某盘"才保存，且不与其他操作塞同一轮。
4. **按需连接**：只有真正要操作 CDR 时才连接/启动它，不需要时不会自动打开。
5. **CDR 操作成功后不渲染预览**（临摹并排对比除外），直接提示"请在 CDR 中查看"。
6. **一次说一件事**：不要把多个不相关修改塞进一次调用，出错难回退。

## 工具清单（32 个，按类）

| 分类 | 工具 | 用途 |
|---|---|---|
| 连接/文档 | corel_status | 查在线状态（按需连接） |
| | list_open_documents | 列已打开文档 |
| | attach_active_document | 绑定当前活动文档，拿 session_id |
| | attach_open_document | 按名称/路径绑定指定文档 |
| | create_new_document | 新建文档 |
| | inspect_document | 查看全部形状（ID/类型/位置/尺寸/文字） |
| | apply_operations | 执行改字/改色/画形状等批量操作 |
| | render_preview | 渲染 PNG 预览 |
| | undo_last_edit / redo_last_edit | 撤销 / 重做 |
| | save_current_document / save_document_as | 保存 / 另存为（仅用户要求时） |
| | export_document | 导出 pdf/svg/png/jpg/dxf |
| | detach_document | 解绑文档 |
| 绘图 | create_curve_shape | 自由曲线/不规则轮廓（旗帜、波浪） |
| | apply_gradient_fill | 渐变填充（线性/径向/圆锥/矩形） |
| 图片 | import_bitmap | 导入位图（自动降采样、空白页居中） |
| | import_svg | 导入 SVG 矢量（自动解锁、可编辑） |
| | replace_bitmap | 替换已有位图（支持 PowerClip 内） |
| | trace_bitmap | 临摹位图转矢量 |
| 批量 | duplicate_shapes | 批量复制群组、网格排列、逐个改字 |
| | get_selection | 读当前选中元素（最快定位） |
| | batch_place_images | 本地图片批量 PowerClip 置入 |
| | batch_search_images | 只搜图下载（不置入） |
| | batch_search_and_place | 搜图+PowerClip 置入一次完成 |
| | create_org_chart | 区域内自动绘制组织架构图 |
| 错别字检查 | extract_selected_text | 提取选中文字全文（供检查，返回准确文本供定位） |
| | mark_text_errors | 按字符范围分色标记错字（红=错字/蓝=语句不通/橙=逻辑问题，自动记原色） |
| | fix_text_errors | 按字符范围替换错字（标记色保留，可一键恢复） |
| | restore_marked_colors | 一键把所有标记恢复成原来的颜色 |
| 批量数据牌 | parse_board_records | 解析 Word/Excel/文本成记录（标题+正文） |
| | batch_system_board | 模板批量复制排版、替换标题正文 |

## 🔴 错别字检查硬规则（用户说"检查错别字"时必须走这套流程）

1. **绝对禁止**用 `apply_operations` / `fill.set_rgb` 通用改色工具来标错字——那会把整段文字全部变色，做不到只标错字本身
2. **标准流程**：
   ① `extract_selected_text` 拿到选中文字全文
   ② 通读检查：逐字看错别字、逐句看语法逻辑
   ③ `mark_text_errors` 直接标记（检查完不用问，直接标，红=错别字/蓝=语句不通/橙=逻辑问题）
   ④ 弹窗给用户两个选择：我帮你改 / 你自己改
   ⑤ 选"我帮你改"→ `fix_text_errors` 替换错字 → 再弹窗问是否恢复原色
   ⑥ 选"你自己改"→ 用户改完 → `restore_marked_colors` 恢复黑色
3. **定位错字**：直接在 `extract_selected_text` 返回的 text 字符串里找错字位置，不要自己手动重写文本（换行符、空格差异会导致索引偏移改错位置）

## 按需读取参考（什么场景读哪个）

| 场景 | 读取文件 |
|---|---|
| 改字/改色、标准操作流程、apply_operations 操作表、定位元素 | `references/basic-editing.md` |
| 画自由曲线/不规则轮廓、渐变填充 | `references/draw-shapes.md` |
| 导入位图/SVG、替换图片、超大图/空白页居中 | `references/images.md` |
| 批量复制门牌/群组、网格排列 | `references/duplicate.md` |
| 批量搜图并置入框 | `references/batch-search.md` |
| 画组织架构图 | `references/org-chart.md` |
| 批量数据牌/制度牌（解析+排版） | `references/batch-system-board.md` |
| 临摹/位图转矢量 | `references/trace-bitmap.md` |

## 🔴 开发新功能：必须走功能分支（改连接器代码时）

开发/扩展 MCP（不是日常用 CDR，而是改代码）时，禁止直接动 main（主线，稳定可用的主分支）：

1. 仓库根目录运行 `.\scripts\new-feature.ps1 start <功能名>`，自动从 main 建 `feature/功能名`（功能分支，临时开发分支）并切换。
2. 在分支上开发、在 CDR 实测（MCP 读当前磁盘文件）。
3. 跑通并经用户确认后，运行 `.\scripts\new-feature.ps1 finish -Tag <版本号>`，自动 merge（合并，把分支改动并入主线）、打 tag（版本标签）、删分支。
4. 做废用 `.\scripts\new-feature.ps1 discard`；查状态用 `.\scripts\new-feature.ps1 status`。

用户常在新对话验证功能、跑通后回主对话统一合并；无论哪个对话，开发新功能都先 `start` 建分支。
