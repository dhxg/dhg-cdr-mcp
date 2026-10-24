# 2026-10-21: MCP 端批量搜图工具（一次调用完成）

## Added

- 新增 `batch_search_images` 工具：MCP server 端直接请求百度图片 acjson 素材接口
  拿候选（含尺寸/清晰度），按"无水印（站点黑名单）、高清（长边 ≥ min_long_edge，
  默认 1000px）、最清晰（clarityScore）最贴合（搜索排序）"自动筛选，并行下载到
  本地（默认下载到系统临时目录，可用环境变量 `COREL_BATCH_SEARCH_DIR` 覆盖）。单个关键词最多并行尝试 8 个候选，原图
  （objURL，ipprf 加密格式）通过公开映射表解密；下载后经 PIL 校验尺寸与完整性。
- 新增 `batch_search_and_place` 工具：一次调用完成"读选中框 → 搜图 → 筛选 →
  并行下载 → PowerClip 置入"全流程，替代原浏览器手动搜图（截图—判断—点击—
  下载，N 个关键词 N 轮串行）。关键词与容器 1:1，或单关键词复用到所有框。
- `batch_place_images` 的置入主体逻辑抽取为 `shapes._place_images_into_containers`，
  供新旧两个工具复用。

## Fixed

- `tests/test_server_registration.py` 的 compact 工具数断言由过期的 14 更新为 26
  （原断言早于 compact 列表扩展，属于存量失效），并补充对新增工具的断言。

## Perf（同日第二次提交）

- 下载/接口超时 20s → 6s：挂起站点不再干等。
- 快速宿主优先：百度自有 CDN（bdstatic / sinaimg / bcebos 等）优先尝试，
  外部小众图床降为兜底，避免"慢站占满并发 worker 排队"的病理。
- 运行时慢站黑名单：本进程内某站点超时一次即跳过其后续候选。
- 提前取消：已有成功候选且优先级更高的候选都有结论时，取消剩余下载。
- 实测 6 关键词（桑葚/红葡萄/芒果/荔枝/菠萝/猕猴桃）：46.3s → 3.2s。
