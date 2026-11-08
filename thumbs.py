# -*- coding: utf-8 -*-
"""日报首页两个榜单的商品缩略图：按本次上榜集合下载 / 替换 / 清理。

为什么单独一个模块：daily.py 只关心行情数据，图片是「跟着榜单走的静态资源」，
生命周期与 catalog / pool 完全不同（前者每天换一茬，后者要留 365 天）。

【防盗链实测 2026-11-07】y.zdmimg.com 按 Referer 放行：
    空 Referer / smzdm 站内 Referer  → 200 image/jpeg
    https://elizond0.github.io/ 等第三方 → HTTP 567「访问受限」+ RequestId
所以下载时**绝不设置 Referer**；也不用伪装主站。存到 docs/thumbs/ 之后，
Pages 页面用同源相对路径 ./thumbs/ 引用，天然没有跨域 / 防盗链问题。

【纪律】图片 URL 只存在于本次抓取的内存 deals 里，
不写进 catalog.json / pool.json / db.json —— 数据库不存图。
文件名用 article_id，渲染时按 article_id 反查本模块返回的映射。

【护栏】抓取失败（stale / 离线 / 本次无图 URL）时调用方传 allow_download=False，
本模块只扫描现有文件、不下载也不删除，避免把页面上的图一次性清空。
"""

from __future__ import annotations

import re
import time
import urllib.request
from pathlib import Path

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
# 注意：不带 Referer。带上任何第三方域名都会被 CDN 判为盗链。
HEADERS = {"User-Agent": UA, "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"}
TIMEOUT = 12
MAX_BYTES = 500_000      # 单张上限，防止异常大图混进来
GAP = 0.15               # 每张之间歇一下，别对 CDN 打突发流量
SAFE_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def _ext(data: bytes) -> str | None:
    """按文件头判扩展名，不能信 URL 后缀。

    实测同一批图里既有 `xxx.jpg_a320.jpg` 真 JPEG，也有 `xxx.png_a320.jpg`
    实际是 PNG —— 后缀一律是 .jpg。按后缀存会让 Pages 返回错误的 Content-Type。
    """
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    return None


def _fetch(url: str) -> tuple[bytes, str] | None:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        data = r.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES or len(data) < 512:
        return None
    ext = _ext(data)
    return (data, ext) if ext else None


def _scan(dest: Path) -> dict[str, str]:
    """只扫描现有目录，返回 {article_id: 文件名}，不改动任何文件。"""
    out: dict[str, str] = {}
    for p in sorted(dest.iterdir()):
        if p.is_file() and SAFE_ID.match(p.stem):
            out.setdefault(p.stem, p.name)
    return out


def sync(items, dest: Path, *, allow_download: bool = True, log=print) -> dict[str, str]:
    """把「本次上榜商品」的缩略图同步到 dest，返回 {article_id: 文件名}。

    - 只处理同时有 article_id 与 thumb 的商品；
    - 同一个 id 的旧文件先删再写（实现「实时替换」，
      也避免同 id 留下 .jpg / .png 两份互相打架）；
    - 单张下载失败时保留该 id 已有文件，不让整页图裂；
    - 结尾清掉不在本次集合里的文件（「把旧的图片删去」）；
    - allow_download=False 或本次没有任何图 URL：只扫描、不下载也不删除。
    """
    dest.mkdir(parents=True, exist_ok=True)

    wanted: dict[str, str] = {}
    for it in items:
        aid = str(it.get("article_id") or "").strip()
        url = it.get("thumb")
        if aid and url and SAFE_ID.match(aid):
            wanted[aid] = url

    existing: dict[str, list[Path]] = {}
    for p in dest.iterdir():
        if p.is_file() and SAFE_ID.match(p.stem):
            existing.setdefault(p.stem, []).append(p)

    # 护栏：离线 / 抓取失败 / CDN 改结构导致一条图 URL 都没有时，
    # 绝不能把上次的图删光。页面继续显示旧图，比整页空白好得多。
    if not allow_download or not wanted:
        return {aid: files[0].name for aid, files in existing.items()}

    manifest: dict[str, str] = {}
    ok = fail = 0
    for aid, url in wanted.items():
        got = None
        try:
            got = _fetch(url)
        except Exception as e:  # noqa: BLE001 - 单张失败不能拖垮整轮
            log(f"  缩略图 {aid} 下载失败：{type(e).__name__}")
        if got:
            data, ext = got
            for old in existing.get(aid, []):
                try:
                    old.unlink()
                except OSError:
                    pass
            fname = aid + ext
            try:
                (dest / fname).write_bytes(data)
                manifest[aid] = fname
                ok += 1
            except OSError as e:
                log(f"  缩略图 {aid} 写入失败：{e}")
        else:
            fail += 1
            if existing.get(aid):
                manifest[aid] = existing[aid][0].name
        time.sleep(GAP)

    keep = set(manifest.values())
    removed = 0
    for files in existing.values():
        for p in files:
            if p.name not in keep:
                try:
                    p.unlink()
                    removed += 1
                except OSError:
                    pass
    log(f"  缩略图同步：下载 {ok} / 失败 {fail} / 清理 {removed}，目录现存 {len(keep)} 张")
    return manifest
