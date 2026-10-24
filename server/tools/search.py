"""批量搜图工具：MCP server 端直接请求素材接口、按尺寸/清晰度筛选、并行下载。

替代原来的"助手用浏览器手动搜图"流程（截图—判断—点击—下载，N 个关键词 N 轮串行）。
现在一次工具调用完成：请求素材站 JSON 接口拿候选（含尺寸/清晰度）→ 自动筛选
（长边 >= min_long_edge、排除水印重灾站点、排除动图）→ 并行下载 → 可选直接
PowerClip 置入选中框。

素材源：百度图片 acjson 公开 JSON 接口（无需 key）。条目里的 objURL 是
ipprf 加密格式，用经典映射表解密还原为原始图片 URL；解密后按顺序尝试多个
候选（原图常有 403/404，参考公开爬虫实现，失败率高属正常，需逐个尝试）。

用户偏好：按"无水印、高清(长边>=1000px)、最清晰最贴合关键词"自动选图，
不弹窗询问。
"""

import json
import os
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, as_completed, wait

from core.models import ToolResult

# ========== 百度 acjson 接口与 objURL 解密 ==========

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# objURL 解密映射表（公开算法：先替换多字符 token，再逐字符翻译）
_STR_TABLE = {"_z2C$q": ":", "_z&e3B": ".", "AzdH3F": "/"}
_CHAR_TABLE = {
    "w": "a", "k": "b", "v": "c", "1": "d", "j": "e", "u": "f", "2": "g", "i": "h",
    "t": "i", "3": "j", "h": "k", "s": "l", "4": "m", "g": "n", "5": "o", "r": "p",
    "q": "q", "6": "r", "f": "s", "p": "t", "7": "u", "e": "v", "o": "w", "8": "1",
    "d": "2", "n": "3", "9": "4", "c": "5", "m": "6", "0": "7", "b": "8", "l": "9",
    "a": "0",
}

# 水印重灾站点黑名单（图库/素材站直链常带水印，直接排除）
_DENY_HOSTS = (
    "nipic.com", "699pic.com", "vcg.com", "quanjing.com", "51yuansu.com",
    "gettyimages", "shutterstock", "alamy", "123rf", "dreamstime",
    "huitu.com", "shejisucai", "sucai.redocn", "sccnn", "pixabay",
)
# 下载单文件大小上限（字节），避免个别超大原图拖慢流程
_MAX_BYTES = 50 * 1024 * 1024
# 接口/下载超时（秒）：挂起站点会拖慢整体，宁可跳过也不要干等
_HTTP_TIMEOUT = 6
# 每个关键词最多尝试下载的候选数
_DEFAULT_MAX_ATTEMPTS = 6
# 下载并发数
_DL_WORKERS = 6

# 快速宿主关键词：百度自有 CDN / 常用图床通常秒回，优先尝试；
# 外部小众图床（如 wallpaper 站）慢且易挂，降为兜底，避免每次都等超时。
_FAST_HOST_KEYWORDS = (
    "bdstatic.com", ".baidu.com", "sinaimg.cn", ".qq.com", "gtimg.com",
    "itc.cn", "y0cdn.cn", "yimutian.com", "bcebos.com", "y.qq.com",
)


def _host_rank(c) -> int:
    host = c["host"].lower()
    if any(k in host for k in _FAST_HOST_KEYWORDS):
        return 0
    if host in _SLOW_HOSTS:
        return 2
    return 1


# 运行时"慢站/挂起站"黑名单：本进程内某站点超时一次后，后续候选直接跳过，
# 避免同一批多次踩坑（如个别外部图床连不上要等满超时）。
_SLOW_HOSTS = set()


def _mark_slow_host(host: str):
    if host:
        _SLOW_HOSTS.add(host.lower())


def _is_timeout_error(exc) -> bool:
    """判断异常是否属于"挂起超时"（区别于快速 403/404/解析失败）。"""
    import socket
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return True
    if hasattr(exc, "reason") and isinstance(exc.reason, (TimeoutError, socket.timeout)):
        return True
    return False

# 默认输出目录：优先环境变量，其次系统临时目录
_DEFAULT_OUT_DIR = os.environ.get(
    "COREL_BATCH_SEARCH_DIR", os.path.join(os.environ.get("TEMP", "/tmp"), "batch_search")
)


def decode_objurl(url: str) -> str:
    """解密百度 objURL（ipprf 格式）为原始图片 URL。"""
    if "ipprf_" not in url:
        return url
    for k, v in _STR_TABLE.items():
        url = url.replace(k, v)
    return "".join(_CHAR_TABLE.get(ch, ch) for ch in url)


def _baidu_candidates(keyword: str, rn: int = 30):
    """请求百度图片 acjson 接口，返回候选列表。

    每条: {url, width, height, clarity, type, host}
    """
    params = {
        "tn": "resultjson_com", "ipn": "rj", "ct": "201326592", "fp": "result",
        "queryWord": keyword, "cl": "2", "lm": "-1", "ie": "utf-8", "oe": "utf-8",
        "word": keyword, "pn": "0", "rn": str(rn),
    }
    api = "https://image.baidu.com/search/acjson?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(api, headers={
        "User-Agent": _UA,
        "Referer": "https://image.baidu.com/search/index?tn=baiduimage&word="
                   + urllib.parse.quote(keyword),
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
        payload = json.loads(resp.read().decode("utf-8", "ignore"))

    out = []
    for d in payload.get("data") or []:
        if not isinstance(d, dict) or not d.get("objURL"):
            continue
        dec = decode_objurl(d["objURL"])
        if not (dec.startswith("http://") or dec.startswith("https://")):
            continue
        w, h = d.get("width") or 0, d.get("height") or 0
        try:
            clarity = int(d.get("clarityScore") or 0)
        except (TypeError, ValueError):
            clarity = 0
        out.append({
            "url": dec,
            "width": int(w), "height": int(h),
            "clarity": clarity,
            "type": (d.get("type") or "").lower(),
            "host": urllib.parse.urlparse(dec).netloc,
        })
    return out


def _filter_candidates(cands, min_long_edge: int):
    """按水印黑名单、动图、已知尺寸过滤；保序。跳过本进程内已判定为慢的站点。"""
    good = []
    for c in cands:
        host = c["host"].lower()
        if host in _SLOW_HOSTS:
            continue
        if any(h in host for h in _DENY_HOSTS):
            continue
        if c["type"] == "gif" or c["url"].lower().endswith(".gif"):
            continue
        if "watermark" in c["url"].lower() or "shuiyin" in c["url"].lower():
            continue
        if c["width"] and c["height"] and max(c["width"], c["height"]) < min_long_edge:
            continue
        good.append(c)
    return good


def _download_to_file(url: str, dest: str):
    """下载图片到 dest；返回 (ok, width, height, format)。"""
    from PIL import Image
    import io
    req = urllib.request.Request(url, headers={
        "User-Agent": _UA,
        "Referer": urllib.parse.urlparse(url).scheme + "://" + urllib.parse.urlparse(url).netloc + "/",
        "Accept": "*/*",
    })
    with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
        raw = resp.read(_MAX_BYTES + 1)
    if len(raw) > _MAX_BYTES:
        return False, 0, 0, ""
    img = Image.open(io.BytesIO(raw))
    img.verify()
    img = Image.open(io.BytesIO(raw))
    w, h = img.size
    fmt = (img.format or "jpeg").lower()
    if fmt == "jpeg":
        fmt = "jpg"
    with open(dest, "wb") as f:
        f.write(raw)
    return True, w, h, fmt


def _safe_filename(keyword: str) -> str:
    s = re.sub(r'[\\/:*?"<>|\s]+', "_", keyword.strip())
    return s[:40] or "image"


def _pick_download_path(out_dir: str, keyword: str, fmt: str) -> str:
    base = _safe_filename(keyword)
    n = 1
    while True:
        p = os.path.join(out_dir, f"{base}_{n:02d}.{fmt}")
        if not os.path.exists(p):
            return p
        n += 1


def _quiet_remove(path):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def _search_and_download(keyword: str, min_long_edge: int, out_dir: str):
    """单个关键词：拉候选 → 筛选 → 并行尝试下载前 N 个 → 返回最佳成功结果。

    下载先写临时 .part 文件，通过尺寸校验后用 os.replace 落为正式文件名
    （避免并发下文件名冲突、避免把失败/小图留在目录里）。
    提前取消：一旦确定"优先级更高的候选都已有结论"，就取消剩余下载，
    避免挂起站点拖慢整体；超时统一 _HTTP_TIMEOUT 秒。

    返回 dict 或 None（全部失败）。
    """
    try:
        cands = _baidu_candidates(keyword, rn=30)
    except Exception:
        return None
    cands = _filter_candidates(cands, min_long_edge)
    if not cands:
        return None

    # 优先快速宿主，其次清晰度高、位置靠前；慢站已由 _filter_candidates 排除
    cands.sort(key=lambda c: (_host_rank(c), -c["clarity"]))
    top = cands[:_DEFAULT_MAX_ATTEMPTS]

    os.makedirs(out_dir, exist_ok=True)
    base = _safe_filename(keyword)
    kept = {}  # url -> (dest, w, h, fmt, priority_index)

    with ThreadPoolExecutor(max_workers=min(_DL_WORKERS, len(top))) as ex:
        futures = {}
        for i, c in enumerate(top):
            tmp = os.path.join(out_dir, f"__tmp_{base}_{i:02d}.part")
            futures[ex.submit(_download_to_file, c["url"], tmp)] = (c, i, tmp)

        pending = set(futures)
        while pending:
            done, pending = wait(pending, timeout=1.0, return_when=FIRST_COMPLETED)
            for fut in done:
                c, i, tmp = futures[fut]
                try:
                    ok, w, h, fmt = fut.result()
                except Exception as exc:
                    ok, w, h, fmt = False, 0, 0, ""
                    if _is_timeout_error(exc):
                        _mark_slow_host(c["host"])
                if not ok:
                    _quiet_remove(tmp)
                    continue
                if w and h and max(w, h) < min_long_edge:
                    _quiet_remove(tmp)
                    continue
                dest = _pick_download_path(out_dir, keyword, fmt)
                try:
                    os.replace(tmp, dest)
                    kept[c["url"]] = (dest, w, h, fmt, i)
                except OSError:
                    _quiet_remove(tmp)
            # 已有成功候选，且所有未完成候选的优先级都低于它 → 取消剩余
            if kept:
                best_i = min(v[4] for v in kept.values())
                if all(i > best_i for (_, i, _) in (futures[f] for f in pending)):
                    for f in pending:
                        f.cancel()
                    pending = set()

    for c in top:  # 按优先级取第一个成功
        if c["url"] not in kept:
            continue
        dest, w, h, fmt, _ = kept[c["url"]]
        return {
            "keyword": keyword,
            "path": dest,
            "width": w, "height": h,
            "clarity": c["clarity"],
            "host": c["host"],
            "source_url": c["url"],
        }
    return None


def batch_search_images(
    keywords,
    min_long_edge: int = 1000,
    out_dir: str = None,
) -> ToolResult:
    """按关键词批量搜图并下载到本地（MCP server 端，不需要 CDR）。

    一次调用完成：请求素材接口拿候选 → 按尺寸/清晰度筛选（默认长边>=1000px、
    排除水印重灾站点和动图）→ 并行下载，每个关键词返回一张最优图。

    Args:
        keywords: 关键词列表，如 ["玉米", "红薯"]；也支持单个字符串。
        min_long_edge: 最小长边像素，默认 1000（高清门槛）。
        out_dir: 下载目录，默认系统临时目录下的 batch_search
            （可用环境变量 COREL_BATCH_SEARCH_DIR 覆盖）。
    """
    if isinstance(keywords, str):
        keywords = [keywords]
    keywords = [k.strip() for k in (keywords or []) if k and str(k).strip()]
    if not keywords:
        return ToolResult.fail("keywords 为空，请提供至少一个关键词")

    out_dir = out_dir or _DEFAULT_OUT_DIR
    t0 = time.time()
    items = []
    failed = []
    with ThreadPoolExecutor(max_workers=min(_DL_WORKERS, len(keywords))) as ex:
        futures = {ex.submit(_search_and_download, kw, int(min_long_edge), out_dir): kw for kw in keywords}
        for fut in as_completed(futures):
            kw = futures[fut]
            try:
                r = fut.result()
            except Exception:
                r = None
            if r:
                items.append(r)
            else:
                failed.append(kw)

    elapsed = round(time.time() - t0, 1)
    if not items:
        return ToolResult.fail(
            f"全部 {len(keywords)} 个关键词均未搜到可用图片（已尝试候选并过滤水印/小图）。"
            f"可尝试：换个关键词，或调低 min_long_edge（当前 {min_long_edge}）。",
            code="SEARCH_NO_RESULT",
        )
    msg = f"搜图完成：成功 {len(items)}/{len(keywords)} 个关键词，耗时 {elapsed}s"
    if failed:
        msg += f"；失败：{', '.join(failed)}"
    return ToolResult.ok(msg, items=items, failed=failed, elapsed_sec=elapsed)


def batch_search_and_place(
    keywords,
    container_ids=None,
    fit_mode: str = "fill",
    min_long_edge: int = 1000,
) -> ToolResult:
    """批量搜图并直接 PowerClip 置入（一次工具调用，替代浏览器手动搜图）。

    流程：读取当前选中框（或指定容器）→ 每个框一个关键词，server 端请求素材
    接口拿候选 → 按尺寸/清晰度筛选 → 并行下载 → 导入并 PowerClip 置入。

    Args:
        keywords: 关键词列表，长度须与容器数量一致；若只给 1 个关键词且容器
            多于 1 个，则所有框都用该关键词。
        container_ids: 容器 shape_id 列表（可省略，默认用 CDR 当前选中元素）。
        fit_mode: 内容适配方式，默认 fill（按比例填充），可选 fit / stretch / center。
        min_long_edge: 最小长边像素，默认 1000。
    """
    from tools import shapes

    conn = get_connection()
    if not conn.status.connected:
        return ToolResult.fail("CorelDRAW 未连接")

    # ---- 1. 解析容器 ----
    if container_ids:
        containers = [str(c) for c in container_ids]
    else:
        sel = shapes.get_selection()
        if not sel.success:
            return ToolResult.fail(sel.error or "读取选中失败")
        items = (sel.data or {}).get("items") or []
        if not items:
            return ToolResult.fail(
                "当前没有选中任何元素。请在 CorelDRAW 里框选要置入的图形后再调用，"
                "或显式传入 container_ids。"
            )
        containers = [it["shape_id"] for it in items]

    # ---- 2. 关键词归一 ----
    if isinstance(keywords, str):
        keywords = [keywords]
    keywords = [k.strip() for k in (keywords or []) if k and str(k).strip()]
    if not keywords:
        return ToolResult.fail("keywords 为空，请提供至少一个关键词")
    if len(keywords) == 1 and len(containers) > 1:
        keywords = keywords * len(containers)
    if len(keywords) != len(containers):
        return ToolResult.fail(
            f"关键词数量（{len(keywords)}）与容器数量（{len(containers)}）不一致。"
            "每个框对应一个关键词；或多个框共用同一个关键词时只给 1 个。"
        )

    # ---- 3. 搜图 + 并行下载（不涉及 COM，可在任意线程） ----
    t0 = time.time()
    out_dir = os.environ.get("COREL_BATCH_SEARCH_DIR", _DEFAULT_OUT_DIR)
    downloads = {}
    with ThreadPoolExecutor(max_workers=min(_DL_WORKERS, len(keywords))) as ex:
        futures = {ex.submit(_search_and_download, kw, int(min_long_edge), out_dir): kw for kw in keywords}
        for fut in as_completed(futures):
            kw = futures[fut]
            try:
                downloads[kw] = fut.result()
            except Exception:
                downloads[kw] = None

    missing = [(kw, cid) for kw, cid in zip(keywords, containers) if not downloads.get(kw)]
    if missing:
        return ToolResult.fail(
            "以下关键词未搜到可用图片（已按无水印/高清/清晰度筛选）："
            + "、".join(kw for kw, _ in missing)
            + "。可换个关键词或调低 min_long_edge 后重试；已成功的图片保留在下载目录。",
            code="SEARCH_NO_RESULT",
        )

    norm = [(str(cid), downloads[kw]["path"]) for kw, cid in zip(keywords, containers)]

    # ---- 4. 置入（COM，走 STA 线程） ----
    result = conn.safe_call(
        lambda: shapes._place_images_into_containers(norm, fit_mode), timeout=180
    )
    if not result["success"]:
        return ToolResult.fail(result.get("error", "批量置入失败"))

    placed = result["result"]
    elapsed = round(time.time() - t0, 1)
    search_info = []
    for kw, cid in zip(keywords, containers):
        d = downloads[kw]
        search_info.append({
            "container_id": str(cid),
            "keyword": kw,
            "path": d["path"],
            "width": d["width"],
            "height": d["height"],
            "clarity": d["clarity"],
            "host": d["host"],
        })

    return ToolResult.ok(
        f"一次调用完成：搜图+置入 {placed['placed']} 个（耗时 {elapsed}s，"
        f"{shapes._FIT_MODES.get(fit_mode, '')}）",
        placed=placed,
        search=search_info,
        elapsed_sec=elapsed,
    )


def get_connection():
    """懒连接 CDR（复用 core.connection 的单例，避免顶部导入 win32com）。"""
    from core.connection import get_connection as _get
    return _get()
