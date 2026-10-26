# 自由曲线绘制 与 渐变填充

## 自由曲线（旗帜、波浪、飘带、不规则图形）

需要画非矩形轮廓（飘扬红旗、波浪、飘带、异形底版）时，用 `create_curve_shape`，不要用矩形硬凑。

**参数：**
- `subpaths`：路径数组，每个路径：
  - `points`：点列表，单位 mm，原点在页面左上角、y 向下
    - 第一个点是起点：`{"x": 50, "y": 50}`
    - 后续每点为一段：
      - 直线段 `{"type": "line", "x": 100, "y": 100}`
      - 贝塞尔曲线段 `{"type": "curve", "x": 100, "y": 40,
        "cp1x": 60, "cp1y": 50,   # 控制柄1，靠近上一个点
        "cp2x": 90, "cp2y": 40}`  # 控制柄2，靠近当前点
  - `closed`：是否封闭（填色必须 true）
- `fill_rgb`：填充色 `[r,g,b]`；或 `fill_cmyk`：`[c,m,y,k]`
- 默认无描边

**画飘扬红旗思路：**
1. 用 `create_curve_shape` 画红旗波浪外轮廓（顶部 2-3 段贝塞尔做波浪），填红色
2. 再画几条深红/暗红曲线叠加表现褶皱阴影
3. 旗杆用矩形或直线（可用 apply_operations 的 shape.create_rectangle）

**注意：** 贝塞尔控制点是绝对坐标，工具会自动转换，按视觉位置给即可。

## 渐变填充

给形状做渐变（线性/径向/圆锥/矩形）时，用 `apply_gradient_fill`。

**参数：**
- `shape_id`：目标形状
- `start_rgb` / `end_rgb`：起止颜色 `[r,g,b]`（或 `start_cmyk`/`end_cmyk`）
- `gradient_type`：`"linear"`（线性，默认）/ `"radial"`（径向）/ `"conical"`（圆锥）/ `"square"`（矩形）
- `angle`：角度，线性：0 从左到右，90 从下到上
- `midpoint`：中点 0-100（默认 50）
- `edge_pad`：边缘留白 0-49
- `center_offset_x/y`：径向/圆锥中心偏移
- `color_stops`：多色渐变中间色标，`[{"position":33,"rgb":[r,g,b]}]`；不传则双色

**适用场景：** 海报背景、渐变底版、旗帜立体感、金属质感等。
