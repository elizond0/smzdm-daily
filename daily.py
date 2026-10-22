#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""值得买每日优惠推送。

  python daily.py              正常跑（当天已推送则跳过）
  python daily.py --force      忽略当天已推送状态，强制再跑一次
  python daily.py --dry-run    抓取并生成报表，但不推送
  python daily.py --no-crawl   不联网，用上次缓存重新生成并推送
  python daily.py --probe      只探测是否被风控，不做任何抓取

防封控的三条硬规则：
  1. 请求预算封顶，超了直接停；
  2. 两次请求随机间隔，不等速轮询；
  3. 一旦识别到验证码页，立刻放弃当日剩余请求并冷却，绝不重试。
"""

from __future__ import annotations

import argparse
import configparser
import hashlib
import html as H
import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import faxian  # noqa: E402
import probe  # noqa: E402

# 本地默认写到 build/；云端（GitHub Actions）用 SMZDM_BUILD 指到持久化目录
BUILD = Path(os.environ.get("SMZDM_BUILD") or (BASE / "build"))
LOGS = BUILD / "logs"
STATE = BUILD / "state"
CACHE = BUILD / "cache"
REPORTS = BUILD / "reports"
TOAST = BASE / "tools" / "toast.ps1"

MARK_PUSH = STATE / "last_push.txt"
MARK_COOL = STATE / "cooldown_until.txt"
STREAK = STATE / "blocked_streak.txt"
CATALOG = CACHE / "catalog.json"
POOL = CACHE / "pool.json"
WATCHLIST = BASE / "watchlist.txt"
LAST_DATA = CACHE / "latest.json"
RUN_HISTORY = CACHE / "run_history.json"

# 数据源：全部好价排行榜 · 12H最热 · 全部分类 · 全部商城
# h2=3小时 h3=12小时 h4=24小时；f0=全部分类 c0=全部商城；p{}=页码
FEED_TPL = "https://faxian.smzdm.com/h3s0t0f0c0p{}/"
FEED_NAME = "12H最热"

# 券类/红包类帖子不是商品，剔除
JUNK = re.compile(r"每日可领|红包|外卖|满\d+减|神券|领券|话费|流量|积分兑换|抽奖|签到")
# 只是标注出来、不剔除。这类价格需要额外操作（凑单、淘金币抵扣、试用装），
# 报表里用醒目样式提醒，真想去掉可以在 config 的 exclude_conds 里填。
WARN_CONDS = {"凑单", "淘金币", "试用"}

# 品类词表。匹配时按词长优先，所以「洗衣液」不会被「洗衣」抢走，
# 「电视盒子」也不会被「电视机」误判。
CATEGORIES = {
    "食品生鲜": (
        "大米 小米 面粉 食用油 花生油 橄榄油 菜籽油 玉米油 调和油 牛奶 酸奶 奶粉 奶酪 奶酪棒 "
        "芝士 黄油 零食 饼干 坚果 瓜子 薯片 薯条 锅巴 麻花 桃酥 沙琪玛 雪饼 米饼 蛋黄派 "
        "曲奇 威化 蛋卷 爆米花 巧克力 糖果 果冻 果脯 杏干 葡萄干 芒果干 山楂 话梅 蜜饯 "
        "牛肉 猪肉 鸡肉 羊肉 牛排 鸡翅 鸡腿 鸡胸肉 鸡爪 鸭脖 卤味 肉脯 肉干 肉松 火腿 香肠 "
        "腊肠 培根 午餐肉 鱼 虾仁 大虾 海鲜 三文鱼 鱼豆腐 蟹棒 水果 苹果 香蕉 橙子 葡萄 "
        "西瓜 草莓 芒果 蔬菜 番茄 鸡蛋 咸蛋 水饺 饺子 包子 汤圆 馄饨 火锅 丸子 关东煮 "
        "速冻 冷冻 酱油 食醋 料酒 食盐 调味 咖啡 咖啡液 挂耳 速溶 茶叶 绿茶 红茶 奶茶 "
        "饮料 可乐 汽水 气泡水 苏打水 矿泉水 天然水 山泉水 纯净水 饮用水 椰子汁 椰汁 果汁 "
        "豆奶 乳酸菌 茶饮料 运动饮料 方便面 泡面 酸辣粉 自热 自热米饭 罐头 蜂蜜 麦片 燕麦 "
        "燕麦片 五谷 杂粮 红枣 枸杞 腰果 巴旦木 开心果 核桃 夏威夷果 碧根果 榛子 花生 "
        "蚕豆 青豆 海苔 银耳 阿胶 八宝粥 面包 蛋糕 月饼 粽子 豆干 豆腐干 腐竹 辣条 蛋挞 "
        "披萨 速食 螺蛳粉 米线 米粉 粉丝 挂面 面条 年糕 早餐 蕉 吐司 馍片 西梅 炸鸡 肉串 "
        "腿肉"
    ).split(),
    "电脑数码": (
        "手机 平板 笔记本 电脑 显示器 键盘 鼠标 耳机 音箱 音响 摄像头 路由器 交换机 硬盘 "
        "固态 内存条 U盘 移动硬盘 充电器 充电宝 数据线 电源 显卡 主板 机箱 散热器 手环 "
        "智能手表 相机 镜头 打印机 投影仪 电视盒子 游戏机 手柄 网线 读卡器 拓展坞 手机壳 "
        "钢化膜 硬盘盒 声卡 麦克风 摄像头"
    ).split(),
    "家用电器": (
        "冰箱 洗衣机 空调 电视机 微波炉 烤箱 空气炸锅 电磁炉 电饭煲 压力锅 破壁机 榨汁机 "
        "豆浆机 咖啡机 热水器 净水器 饮水机 加湿器 除湿机 电风扇 风扇 取暖器 吸尘器 扫地机 "
        "洗地机 吹风机 剃须刀 电动牙刷 电水壶 电煮锅 电饼铛 洗碗机 消毒柜 油烟机 燃气灶 "
        "挂烫机 熨斗"
    ).split(),
    "日用百货": (
        "纸巾 卷纸 抽纸 湿巾 湿厕纸 厨房纸 卫生纸 手帕纸 洗衣液 洗衣凝珠 洗衣粉 洗洁精 "
        "柔顺剂 清洁剂 消毒液 垃圾袋 保鲜膜 保鲜袋 牙膏 牙刷 洗发水 沐浴露 护发素 洗手液 "
        "香皂 毛巾 浴巾 拖鞋 内衣 袜子 收纳 衣架 拖把 抹布 手套 雨伞 水杯 保温杯 餐具 "
        "保鲜盒 电池 灯泡 插座 插排 面霜 乳液 精华 防晒 面膜 口红 粉底 眼霜 爽肤水 "
        "护手霜 身体乳 卸妆 香水 洗面奶 洁面 眼罩 枕 床单 被套 卫生巾 安心裤 餐巾纸 "
        "修护霜 特润霜 保湿霜"
    ).split(),
    "酒类": ("白酒 啤酒 葡萄酒 红酒 黄酒 威士忌 伏特加 果酒 洋酒 浓香型 酱香型 "
             "五粮液 茅台 剑南春 泸州老窖 洋河 汾酒").split(),
}

# (词, 品类) 按词长降序，保证「智能手表」先于「手表」、「洗衣液」先于「洗衣」
_WORD2CAT = sorted(
    ((w, cat) for cat, words in CATEGORIES.items() for w in words),
    key=lambda x: -len(x[0]),
)


def classify(title: str) -> str:
    """按标题猜品类，命中不到就归「其他」。"""
    for word, cat in _WORD2CAT:
        if word in title:
            return cat
    return "其他"


def split_list(raw: str) -> list[str]:
    return [x.strip() for x in re.split(r"[,，、]", raw or "") if x.strip()]


# ---------------------------------------------------------------- 配置与状态
def load_config() -> configparser.ConfigParser:
    cp = configparser.ConfigParser()
    path = BASE / "config.ini"
    if path.exists():
        cp.read(path, encoding="utf-8")
    return cp


def log(msg: str) -> None:
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    print(line)
    try:
        LOGS.mkdir(parents=True, exist_ok=True)
        with (LOGS / "runs.log").open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def export_db(catalog: "Catalog") -> int:
    """导出数据库给 docs/db.html 用。

    按「历史最低折扣」升序排——也就是这个商品历史上最狠能到几折，
    没有折扣数据的排在最后。只保留展示需要的字段，用紧凑 JSON 控制体积。
    """
    rows = []
    for rec in catalog.records.values():
        if not rec.get("title"):
            continue
        rows.append({
            "t": rec.get("title"),
            "p": rec.get("last_price"),
            "o": rec.get("last_origin"),
            "l": rec.get("low"),
            "d": rec.get("low_disc"),
            "u": rec.get("url"),
            "m": rec.get("mall"),
            "c": rec.get("category"),
            "n": rec.get("hits", 0),
            "f": rec.get("first"),
            "s": rec.get("last"),
        })
    rows.sort(key=lambda r: (r["d"] is None, r["d"] or 999, r["t"] or ""))
    payload = {"updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
               "total": len(rows), "items": rows}
    try:
        (BUILD / "db.json").write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8")
    except OSError:
        pass
    return len(rows)


def record_run(status: str, meta: dict | None = None, note: str = "",
               pushed: bool = False) -> None:
    """把本次运行的结果追加到历史，供云端「运行概览」页面展示。

    status 取值：ok（正常推送）/ test（静默测试）/ dry（只出报表）/
                skipped（今天已推或冷却中）/ failed（抓取失败）
    只保留最近 60 次，避免文件无限增长。
    """
    now = datetime.now()
    entry: dict = {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M"),
        "status": status,
        "pushed": pushed,
        "note": note,
    }
    if meta:
        entry.update({
            "source": meta.get("scanned", 0),
            "requests": meta.get("requests", 0),
            "blocked": bool(meta.get("blocked")),
            "hot": meta.get("hot_count", 0),
            "feed": meta.get("feed_count", 0),
            "catalog": meta.get("catalog_count", 0),
            "min_disc": meta.get("min_disc", ""),
        })
    try:
        hist = json.loads(RUN_HISTORY.read_text(encoding="utf-8"))
        if not isinstance(hist, list):
            hist = []
    except (OSError, ValueError):
        hist = []
    hist.append(entry)
    try:
        CACHE.mkdir(parents=True, exist_ok=True)
        RUN_HISTORY.write_text(json.dumps(hist[-60:], ensure_ascii=False, indent=1),
                               encoding="utf-8")
    except OSError:
        pass


def read_mark(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def skip_reason(force: bool) -> str | None:
    """--force 只绕过「今日已推送」，绕不过风控冷却。

    冷却期发请求只会把封禁时间往后推，这是踩过的坑，所以强制项也不放行。
    真要排查，删 build/state/cooldown_until.txt 即可。
    """
    today = datetime.now().strftime("%Y-%m-%d")
    cool = read_mark(MARK_COOL)
    if cool:
        try:
            until = datetime.fromisoformat(cool)
            if datetime.now() < until:
                return f"风控冷却中，{until:%m-%d %H:%M} 之后才会再请求"
        except ValueError:
            pass
    if not force and read_mark(MARK_PUSH) == today:
        return "今天已经推送过了（--force 可强制重跑）"
    return None


def set_cooldown(base_hours: float) -> None:
    """被拦后进入冷却。

    连续被拦说明这个出口 IP 已经进了观察名单，此时按原频率重试只会
    加深处罚。所以冷却时长随连续拦截次数翻倍，最长封顶 24 小时——
    这比单纯拉长请求间隔更有效，因为它减少的是「总请求数」。
    """
    streak = read_streak() + 1
    STATE.mkdir(parents=True, exist_ok=True)
    STREAK.write_text(str(streak), encoding="utf-8")
    hours = min(base_hours * (2 ** (streak - 1)), 24)
    until = datetime.now() + timedelta(hours=hours)
    MARK_COOL.write_text(until.isoformat(timespec="seconds"), encoding="utf-8")
    log(f"连续第 {streak} 次被拦，冷却 {hours:g} 小时至 {until:%m-%d %H:%M}")


def read_streak() -> int:
    try:
        return max(0, int(read_mark(STREAK) or 0))
    except ValueError:
        return 0


def reset_streak() -> None:
    """抓取成功就清零，下次被拦重新从基础冷却算起。"""
    if STREAK.exists():
        STREAK.unlink(missing_ok=True)


# ---------------------------------------------------------------- 抓取
class BudgetExceeded(Exception):
    pass


class Fetcher:
    """受控请求器：预算封顶 + 随机间隔 + 拦截识别。"""

    def __init__(self, cfg: configparser.ConfigParser):
        self.budget = cfg.getint("crawl", "request_budget", fallback=8)
        self.imin = cfg.getfloat("crawl", "interval_min", fallback=6)
        self.imax = cfg.getfloat("crawl", "interval_max", fallback=12)
        self.used = 0
        self.headers = {
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://www.smzdm.com/",
        }

    def get(self, url: str) -> str:
        if self.used >= self.budget:
            raise BudgetExceeded(f"已达当日请求预算 {self.budget} 次")
        if self.used > 0:
            gap = random.uniform(self.imin, self.imax)
            log(f"  等待 {gap:.1f}s ...")
            time.sleep(gap)
        self.used += 1
        log(f"  请求 {self.used}/{self.budget}  {url}")
        req = urllib.request.Request(url, headers=self.headers)
        with urllib.request.urlopen(req, timeout=25) as r:
            doc = r.read().decode("utf-8", "ignore")
        probe.check_blocked(doc)   # 抛 probe.BlockedError
        return doc


def crawl(f: Fetcher, pages: int) -> dict:
    """抓 12H 最热好价榜，按页面顺序给每条编号（rank_no），后面两个榜都用它。"""
    data = {"deals": [], "errors": [], "blocked": False, "requests": 0}
    seen: set[str] = set()

    for page in range(1, pages + 1):
        try:
            items = faxian.parse_feed(f.get(FEED_TPL.format(page)))
        except probe.BlockedError as e:
            data["blocked"] = True
            data["errors"].append(f"第{page}页被拦截：{e}")
            log(f"  第{page}页被拦截，立即停止后续请求")
            break
        except BudgetExceeded as e:
            data["errors"].append(str(e))
            break
        except Exception as e:  # noqa: BLE001
            data["errors"].append(f"第{page}页失败 {type(e).__name__}")
            log(f"  第{page}页失败：{type(e).__name__}")
            continue

        fresh = 0
        for it in items:
            aid = it.get("article_id")
            if aid and aid in seen:
                continue
            if aid:
                seen.add(aid)
            it["source"] = FEED_NAME
            it["rank_no"] = len(data["deals"]) + 1
            data["deals"].append(it)
            fresh += 1
        log(f"  第{page}页 {fresh} 条")

    data["requests"] = f.used
    log(f"  累计 {len(data['deals'])} 条")
    return data


# ---------------------------------------------------------------- 清洗与筛选
def annotate(it: dict) -> dict:
    """标注拿到这个价需要什么门槛，供推送里提示。"""
    blob = it.get("title", "") + it.get("desc", "")
    conds = []
    if "88VIP" in blob:
        conds.append("88VIP")
    if "淘金币" in blob:
        conds.append("淘金币")
    if "凑单" in blob:
        conds.append("凑单")
    if "试用价" in blob:
        conds.append("试用")
    if re.search(r"需用券|需领券", it.get("price_text", "") + blob):
        conds.append("需券")
    if "秒杀" in blob:
        conds.append("秒杀")
    if re.search(r"学生|会员", it.get("title", "")):
        conds.append("会员")
    it["conds"] = conds
    return it


def clean_deals(items: list[dict]) -> list[dict]:
    out, seen = [], set()
    for it in items:
        aid = it.get("article_id")
        if not it.get("title") or not it.get("price"):
            continue
        if aid and aid in seen:
            continue
        if JUNK.search(it["title"]) or it["title"].startswith("过期"):
            continue
        if aid:
            seen.add(aid)
        out.append(annotate(it))
    return out


def load_watchlist() -> list[str]:
    """读取关注关键词。一行一个，# 开头为注释。"""
    try:
        raw = WATCHLIST.read_text(encoding="utf-8")
    except OSError:
        return []
    out = []
    for line in raw.splitlines():
        w = line.strip()
        if w and not w.startswith("#"):
            out.append(w)
    return out


def decorate(d: dict, catalog: "Catalog", cutoff: str, drop_pct: float,
             keep_days: int) -> dict:
    """补上「首次见到 / 历史新低 / 近期推过」三个标记。

    本次抓取的商品和 24 小时池子里的商品都要过这一步——
    池子里的记录是上一轮存下来的，推送状态可能已经变了，必须重新算。
    """
    _, rec = catalog.find(d)
    d["pushed_before"] = False
    d["price_dropped"] = False
    if rec is None:
        d["first_seen"] = True
        d["low_price"] = None
        d["is_low"] = False
        return d

    d["first_seen"] = False
    low = rec.get("low")
    if low is not None:
        d["low_price"] = low
        d["is_low"] = d["price"] < low - 1e-9   # 严格低于才算新低
    else:
        d["low_price"] = None
        d["is_low"] = False

    if keep_days > 0:
        pushed_on = rec.get("push_date")
        if pushed_on and pushed_on >= cutoff:
            prev = rec.get("push_price")
            cheaper = bool(prev) and d["price"] < prev * (1 - drop_pct / 100.0)
            if cheaper:
                d["price_dropped"] = True
            else:
                d["pushed_before"] = True
    return d


def pick(items: list[dict], cfg: configparser.ConfigParser,
         catalog: "Catalog", pool: "Pool") -> tuple[list[dict], dict, list[dict]]:
    """返回 (折扣榜, 统计, 好价榜候选)。

    好价榜候选保持数据源原始顺序，且**包含没有原价的商品**——
    这类商品进不了折扣榜（算不出折扣），但仍是好价，应该出现在表单里。
    """
    max_items = cfg.getint("filter", "max_items", fallback=10)
    min_disc = cfg.getfloat("filter", "min_discount_pct", fallback=30)
    max_price = cfg.getfloat("filter", "max_price", fallback=0)

    cats = set(split_list(cfg.get("interest", "categories", fallback="")))
    blocks = split_list(cfg.get("interest", "block_keywords", fallback=""))
    only = split_list(cfg.get("interest", "only_keywords", fallback=""))
    min_zhi = cfg.getint("quality", "min_zhi", fallback=0)
    min_cmt = cfg.getint("quality", "min_comment", fallback=0)
    exclude = set(split_list(cfg.get("filter", "exclude_conds", fallback="")))

    stat = {"total": len(items), "no_discount": 0, "block_kw": 0, "only_kw": 0,
            "category": 0, "quality": 0, "price": 0, "excluded": 0,
            "dedup": 0, "price_drop": 0}

    keep_days = cfg.getint("dedup", "days", fallback=7)
    drop_pct = cfg.getfloat("dedup", "price_drop_pct", fallback=0)
    cutoff = (datetime.now() - timedelta(days=keep_days)).strftime("%Y-%m-%d")

    words = load_watchlist()
    cand = []
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    for d in items:
        title = d.get("title", "")
        if blocks and any(w in title for w in blocks):
            stat["block_kw"] += 1
            continue
        if only and not any(w in title for w in only):
            stat["only_kw"] += 1
            continue
        d["category"] = classify(title)
        if cats and d["category"] not in cats:
            stat["category"] += 1
            continue
        # 热度：点「值」数或评论数，满足其一
        if min_zhi > 0 or min_cmt > 0:
            if not ((min_zhi > 0 and d.get("zhi", 0) > min_zhi)
                    or (min_cmt > 0 and d.get("comments", 0) > min_cmt)):
                stat["quality"] += 1
                continue
        if max_price > 0 and d["price"] > max_price:
            stat["price"] += 1
            continue
        if exclude and (set(d["conds"]) & exclude):
            stat["excluded"] += 1
            continue
        # 近期推过只做标记，不再直接剔除——
        # 报表要展示完整榜单（哪怕之前推过），推送时才按这个标记过滤，
        # 这样「榜单为什么缺条」和「今天该推什么」两件事互不干扰。
        decorate(d, catalog, cutoff, drop_pct, keep_days)
        if d.get("price_dropped"):
            stat["price_drop"] += 1
        elif d.get("pushed_before"):
            stat["dedup"] += 1
        if not d.get("discount_pct"):
            stat["no_discount"] += 1
        d["watched"] = any(w in title for w in words) if words else False
        cand.append(d)
        pool.put(d, now_str)   # 合格的才入池，供后续 24 小时内的日报使用

    # 折扣榜：从 24 小时池子里筛，不是只看本次抓的。
    # 只看折扣力度，不掺「立省金额」——立省金额和原价正相关，
    # 255 元的商品打 8.6 折就省 43 元，但那压根不算力度大。
    pool_items = pool.recent()
    for d in pool_items:
        decorate(d, catalog, cutoff, drop_pct, keep_days)
        d["_from_pool"] = True
    disc = [d for d in pool_items if d.get("discount_pct")]
    hot = [d for d in disc if d["discount_pct"] <= min_disc]
    stat["pool_size"] = len(pool_items)
    hot.sort(key=lambda d: (d["discount_pct"], -(d.get("save") or 0)))

    # 好价榜：去掉折扣榜里已有的（同一商品不重复占位），
    # 保持数据源原始顺序，取前 N 名。序号仍是原榜名次，会有跳号。
    passed = sorted(cand, key=lambda d: d.get("rank_no", 0))
    hot_ids = {d.get("article_id") for d in hot}
    feed_list = [d for d in passed if d.get("article_id") not in hot_ids]
    feed_list = feed_list[:cfg.getint("crawl", "top_n", fallback=50)]

    # 池子里取出的商品也要标一次「是否在愿望单里」，供折扣榜打标签
    for d in hot:
        d["watched"] = any(w in (d.get("title") or "") for w in words) if words else False
    stat["watch_words"] = len(words)
    stat["watch_hit"] = sum(1 for d in hot if d.get("watched"))
    return hot[:max_items], stat, feed_list


# ---------------------------------------------------------------- 商品身份
# 关键事实：/p/{id}/ 里的 id 是「爆料文章」的 id，不是商品 id。
# 同一件商品换个人爆料、隔几天再爆一次，id 就变了。拿 id 当主键，7 天前那条
# 记录就永远接不上。所以这里用「归一化标题 + 模糊相似度」锚定商品身份，
# article_id 只作为别名收进池子——一个商品可以挂多个历史 id。
_MKT_PREFIX = re.compile(
    r"^(今日必买|值友专享|百亿补贴|国家补贴|PLUS会员|88VIP|会员专享|淘金币可用|"
    r"白菜党|手慢无|必领神券|每日可领|绝对值|历史低价|过期|限时)[：:、\s]*"
)


def norm_title(title: str) -> str:
    """剥掉营销前缀和标点，用于生成指纹。"""
    t = (title or "").strip()
    while True:
        new = _MKT_PREFIX.sub("", t)
        if new == t:
            break
        t = new
    return re.sub(r"[^\w\u4e00-\u9fa5]", "", t)


def display_title(title: str) -> str:
    """只剥营销前缀，保留原本的空格和标点，用于展示。

    标题里常带「88VIP、今日必买：」这类前缀，而这些信息已经有标签在标了，
    重复显示反而把商品名挤到后面，看不清到底卖的是什么。
    """
    t = (title or "").strip()
    while True:
        new = _MKT_PREFIX.sub("", t)
        if new == t:
            break
        t = new
    return t.strip() or (title or "").strip()


def fingerprint(d: dict) -> str:
    return "H:" + hashlib.md5(norm_title(d.get("title", "")).encode("utf-8")).hexdigest()[:16]


def _bigrams(s: str) -> set:
    return {s[i:i + 2] for i in range(len(s) - 1)}


# 标题里的价格描述：「13.8元/盒」「到手价99」——纯噪声，
# 同一商品每次活动写法都不同，会把相似度拉低到阈值以下。
_PRICE_NOISE = re.compile(r"\d+(?:\.\d+)?元(?:/[^\s，。、+*]*)?|到手价\d+(?:\.\d+)?")


# 规格锚点：数字 + 单位。规格不同的绝不可能是同一件商品，
# 这一条比相似度更硬——光看相似度，「4层20包」和「4层24包」能到 0.9。
_SPEC = re.compile(
    r"(\d+(?:\.\d+)?)(kg|g|ml|l|片|包|袋|瓶|支|条|卷|只|双|件|抽|枚|盒|桶|罐|杯|mah|gb|tb|克|毫升|升)"
)


def specs(norm: str) -> list:
    return sorted(_SPEC.findall(norm.lower()))


# 件数类单位：写不写、写不写全，常因标题长度而省略，不代表不同商品
_COUNT_UNITS = {"片", "包", "袋", "瓶", "支", "条", "卷", "只", "双",
                "件", "抽", "枚", "盒", "桶", "罐", "杯"}


def spec_compatible(a: list, b: list) -> bool:
    """规格是否可能是同一件商品。

    重量/容量（g、ml 等）必须完全一致——520g 和 260g 是两件商品。
    件数类（盒、袋、卷）允许一边省略，但两边都写了就必须相同：
    「224g*2」和「224g*2盒」算一致，「27卷」和「10卷」不算。
    """
    if not a or not b:
        return True
    if a == b:
        return True
    sa, sb = {tuple(x) for x in a}, {tuple(x) for x in b}
    core_a = {x for x in sa if x[1] not in _COUNT_UNITS}
    core_b = {x for x in sb if x[1] not in _COUNT_UNITS}
    if core_a != core_b:
        return False
    cnt_a = {x for x in sa if x[1] in _COUNT_UNITS}
    cnt_b = {x for x in sb if x[1] in _COUNT_UNITS}
    if cnt_a and cnt_b and cnt_a != cnt_b:
        return False
    return True


def similarity(a: str, b: str) -> float:
    """字符二元组 Jaccard，用来容忍标题的轻微改写（加「家庭装」、去掉符号等）。"""
    A, B = _bigrams(a), _bigrams(b)
    if not A or not B:
        return 0.0
    return len(A & B) / len(A | B)


class Catalog:
    """本地商品目录：一条记录 = 一个商品身份。

    记录里同时存别名 id 池、历史底价、上次推送时间与价格，
    所以「去重」和「历史低价」共用同一份数据，不会出现两边判断不一致。
    """

    def __init__(self, path: Path = CATALOG):
        self.path = path
        self.records: dict[str, dict] = {}
        self._id_index: dict[str, str] = {}
        self._load()

    # ---------- 读写
    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
        for fp, rec in raw.items():
            # 早期版本的结构没有 norm 字段，直接丢弃重来
            if isinstance(rec, dict) and "norm" in rec:
                rec.setdefault("specs", specs(rec["norm"]))
                self.records[fp] = rec
        self._rebuild()

    def _rebuild(self) -> None:
        self._id_index = {}
        for fp, rec in self.records.items():
            for aid in rec.get("ids", []):
                self._id_index[aid] = fp

    def save(self, keep_days: int = 90) -> None:
        cutoff = (datetime.now() - timedelta(days=keep_days)).strftime("%Y-%m-%d")
        self.records = {fp: rec for fp, rec in self.records.items()
                        if (rec.get("last") or "") >= cutoff}
        self._rebuild()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.records, ensure_ascii=False, indent=1),
                             encoding="utf-8")

    # ---------- 查找
    def find(self, d: dict, threshold: float = 0.55):
        """三级查找：article_id → 标题指纹 → 模糊相似度 + 规格校验。

        返回 (指纹, 记录)，找不到返回 (None, None)。
        """
        aid = d.get("article_id")
        if aid and aid in self._id_index:
            fp = self._id_index[aid]
            return fp, self.records[fp]

        fp = fingerprint(d)
        if fp in self.records:
            return fp, self.records[fp]

        nt = norm_title(d.get("title", ""))
        if len(nt) < 6:
            return None, None
        ns = specs(nt)
        nt_clean = _PRICE_NOISE.sub("", nt)
        best_fp, best = None, 0.0
        for f, rec in self.records.items():
            old = rec.get("norm", "")
            # 长度差太多不可能是同一件，先剪掉，省下大部分比较
            if not old or abs(len(old) - len(nt)) > max(8, len(nt) * 0.4):
                continue
            # 规格对不上直接排除，不看相似度
            if not spec_compatible(ns, rec.get("specs") or []):
                continue
            s = similarity(nt_clean, _PRICE_NOISE.sub("", old))
            if s > best:
                best, best_fp = s, f
        if best >= threshold:
            return best_fp, self.records[best_fp]
        return None, None

    # ---------- 写入
    def upsert(self, d: dict, today: str | None = None) -> dict:
        """把这次看到的商品并进目录。命中老记录时只补 id 别名和价格。"""
        today = today or datetime.now().strftime("%Y-%m-%d")
        fp, rec = self.find(d)
        if rec is None:
            fp = fingerprint(d)
            nt = norm_title(d.get("title", ""))
            rec = {"norm": nt, "specs": specs(nt),
                   "title": d.get("title", ""), "ids": [],
                   "low": None, "first": today, "last": today, "hits": 0,
                   "push_date": None, "push_price": None,
                   # 下面这几个是给「数据库」页面展示用的，随时更新成最近一次见到的样子
                   "url": None, "mall": None, "category": None,
                   "last_price": None, "last_origin": None, "low_disc": None}
            self.records[fp] = rec
        # 见过的 id 全收进池子，下次这个 id 就能直接命中
        aid = d.get("article_id")
        if aid and aid not in rec["ids"]:
            rec["ids"].append(aid)
            self._id_index[aid] = fp
        price = d.get("price")
        if price:
            lo = rec.get("low")
            rec["low"] = price if lo is None else min(lo, price)
        rec["last"] = today
        rec["hits"] = rec.get("hits", 0) + 1

        # 展示字段：始终保留最近一次见到的链接、商城、分类
        for k, v in (("url", d.get("url")), ("mall", d.get("mall")),
                     ("category", d.get("category"))):
            if v:
                rec[k] = v
        if price:
            rec["last_price"] = price
        if d.get("origin_price"):
            rec["last_origin"] = d["origin_price"]
        # 历史最低折扣：每次出现都算一次，取最小的那个
        disc = d.get("discount_pct")
        if disc and disc > 0:
            prev = rec.get("low_disc")
            rec["low_disc"] = disc if prev is None else min(prev, disc)
        return rec

    def set_pushed(self, d: dict, today: str | None = None) -> None:
        fp, rec = self.find(d)
        if rec is None:
            rec = self.upsert(d, today)
        rec["push_date"] = today or datetime.now().strftime("%Y-%m-%d")
        rec["push_price"] = d.get("price")


class Pool:
    """最近 24 小时的合格商品池。

    折扣榜看的是「一天内出现过的所有好价」，而不是单次抓取的结果——
    上午 10 点抓到的 2 折好货，傍晚 6 点那份日报里依然在，
    不会因为数据源换了一批就消失。
    """

    FIELDS = ("article_id", "title", "price", "origin_price", "discount_pct",
              "save", "url", "mall", "conds", "category", "zhi", "comments",
              "source", "time", "rank_no")

    def __init__(self, path: Path = POOL, hours: int = 24):
        self.path = path
        self.hours = hours
        self.items: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
        if isinstance(raw, dict):
            self.items = {k: v for k, v in raw.items() if isinstance(v, dict)}
        self._prune()

    def _prune(self) -> None:
        cutoff = (datetime.now() - timedelta(hours=self.hours)).strftime("%Y-%m-%d %H:%M")
        self.items = {k: v for k, v in self.items.items()
                      if (v.get("last_seen") or "") >= cutoff}

    def put(self, d: dict, now_str: str) -> None:
        # 用标题指纹做 key，same商品换个 article_id 也不会在池子里占两条
        key = fingerprint(d)
        rec = self.items.get(key, {})
        for f in self.FIELDS:
            if d.get(f) is not None:
                rec[f] = d.get(f)
        rec["last_seen"] = now_str
        rec.setdefault("first_seen", now_str)
        self.items[key] = rec

    def recent(self) -> list[dict]:
        self._prune()
        return list(self.items.values())

    def save(self) -> None:
        self._prune()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.items, ensure_ascii=False, indent=1),
                                 encoding="utf-8")
        except OSError:
            pass


# ---------------------------------------------------------------- 渲染
def zhe(pct: float) -> str:
    """折扣百分比转中文折数：18% → 1.8（折）。"""
    return f"{pct / 10:.1f}"


def render_html(hot: list[dict], passed: list[dict], meta: dict) -> str:
    def meta_line(d):
        parts = [d.get("category") or "其他", d.get("mall") or "",
                 d.get("source") or "", d.get("time") or ""]
        if d.get("zhi") or d.get("comments"):
            parts.append(f"值{d.get('zhi', 0)}/评{d.get('comments', 0)}")
        return " · ".join(H.escape(str(p)) for p in parts if p)

    def row(d, i):
        conds = "".join(
            f'<span class="tag{" warn" if c in WARN_CONDS else ""}">{H.escape(c)}</span>'
            for c in d["conds"])
        if d.get("watched"):
            conds = '<span class="wish">愿望单</span>' + conds
        origin = f'<s>¥{d["origin_price"]:g}</s>' if d.get("origin_price") else ""
        low_badge, low_hint = "", ""
        if d.get("is_low"):
            low_badge = '<span class="newlow">新低</span>'
        elif d.get("first_seen"):
            low_badge = '<span class="first">首次</span>'
        elif d.get("low_price") is not None and d["price"] > d["low_price"] + 1e-9:
            low_hint = f'<div class="lowhint">历史低 ¥{d["low_price"]:g}</div>'
        pct = d.get("discount_pct")
        if pct:
            rate = (f'{zhe(pct)}<small>折</small>'
                    f'<div class="bar"><i style="width:{max(4, pct)}%"></i></div>')
        else:
            rate = '<span class="muted">无原价</span>'
        save = f'省¥{d["save"]:g}' if d.get("save") else '<span class="muted">—</span>'
        return f"""<tr>
  <td class="idx">{i}</td>
  <td class="name" data-t="{H.escape(d['title'])}"><a href="{d.get('url') or '#'}" target="_blank">{H.escape(display_title(d['title']))}</a>{conds}
    <div class="meta">{meta_line(d)}</div></td>
  <td class="num"><b>¥{d['price']:g}</b> {origin}{low_badge}{low_hint}</td>
  <td class="rate">{rate}</td>
</tr>"""

    warn = ""
    if meta.get("stale"):
        warn = ('<div class="warn">本次抓取未成功，下面是最近一次有效数据（'
                f'{H.escape(meta.get("data_date") or "更早")}），价格可能已变动。</div>')
    elif meta.get("blocked"):
        warn = '<div class="warn">部分数据源被风控拦截，本次内容可能不完整。</div>'

    # 筛选漏斗：让人一眼看出为什么只剩这几条，调 config 时好对着看。
    # 「无原价」不是过滤项（好价榜照样收录），所以这里不计入淘汰数。
    st = meta.get("stat") or {}
    funnel = ""
    if st:
        parts = [f'数据源 {st.get("total", 0)} 条']
        for label, key in (("黑词", "block_kw"), ("非白名单", "only_kw"),
                           ("品类不符", "category"), ("热度不足", "quality"),
                           ("价超限", "price"), ("已排除", "excluded")):
            if st.get(key):
                parts.append(f'{label} −{st[key]}')
        if st.get("price_drop"):
            parts.append(f'降价放行 +{st["price_drop"]}')
        # 「近期推过」不是过滤项了（榜单照样显示，只是推送时跳过），
        # 所以单独放在末尾说明，不能混进筛选链条里。
        note = ""
        if st.get("dedup"):
            note = (f'　<span style="color:#8a6410">其中 {st["dedup"]} 条近期推过，'
                    f'榜单照常显示，推送时会跳过</span>')
        funnel = (f'<div class="funnel">{" → ".join(parts)} → '
                  f'好价榜 <b>{len(passed)}</b> 条'
                  f'（无原价 {st.get("no_discount", 0)} 条）　|　'
                  f'24 小时池 <b>{st.get("pool_size", 0)}</b> 条 → '
                  f'折扣榜 <b>{len(hot)}</b> 条{note}</div>')

    empty = "" if hot else '<div class="warn">今天没有符合力度阈值的商品，可以调低 config.ini 里的门槛。</div>'
    feed_top = passed  # pick 已按「去掉折扣榜重合 + 前 N 名」截好



    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>值得买日报 {H.escape(meta['date'])}</title>
<meta name="watch-src" content="{H.escape(meta.get('watch_raw_url') or '')}"
        data-api="{H.escape(meta.get('watch_api_url') or '')}"><style>
*{{box-sizing:border-box}}
body{{margin:0;padding:34px 20px;background:#f5f6f8;color:#16181c;
  font:14px/1.65 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}}
.wrap{{max-width:1000px;margin:0 auto}}
h1{{font-size:21px;margin:0 0 4px}}
.sub{{color:#71767e;font-size:12.5px;margin-bottom:22px}}
.warn{{background:#fff8e6;border:1px solid #f3e2b8;color:#8a6410;border-radius:8px;
  padding:10px 14px;font-size:13px;margin-bottom:18px}}
.funnel{{background:#fff;border:1px solid #e6e8eb;border-radius:8px;padding:9px 14px;
  font-size:12px;color:#71767e;margin-bottom:20px;line-height:1.8}}
.funnel b{{color:#c8102e;font-weight:600}}
.stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:26px}}
.stat{{background:#fff;border:1px solid #e6e8eb;border-radius:10px;padding:13px 16px}}
.stat .k{{font-size:11.5px;color:#71767e}}
.stat .v{{font-size:21px;font-weight:600;margin-top:1px}}
.stat .v em{{font-size:12px;font-style:normal;color:#71767e;font-weight:400;margin-left:2px}}
h2{{font-size:14px;margin:28px 0 10px;display:flex;align-items:center;gap:8px}}
h2 .dot{{width:3px;height:13px;background:#c8102e;border-radius:2px}}
h2 .hint{{font-weight:400;color:#8a8f97;font-size:12px}}
table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e6e8eb;
  border-radius:10px;overflow:hidden}}
th{{text-align:left;font-size:11.5px;color:#71767e;font-weight:500;background:#fafbfc;
  padding:9px 12px;border-bottom:1px solid #e6e8eb;white-space:nowrap}}
td{{padding:11px 12px;border-bottom:1px solid #f2f3f5;vertical-align:middle}}
tr:last-child td{{border-bottom:0}}
tbody tr:hover td{{background:#fcfcfd}}
.idx{{color:#a8adb5;width:32px;font-variant-numeric:tabular-nums;font-size:12.5px}}
.cat{{color:#71767e;font-size:12px;width:78px}}
.name a{{color:#16181c;text-decoration:none}}
.name a:hover{{color:#c8102e;text-decoration:underline}}
.meta{{color:#9aa0a8;font-size:11.5px;margin-top:2px}}
.num{{white-space:nowrap;font-variant-numeric:tabular-nums;text-align:right;width:110px}}
.num b{{color:#c8102e;font-size:14.5px}}
.num s{{color:#b6bac1;font-size:12px;margin-left:4px}}
.save{{color:#71767e;font-size:12px}}
.rate{{width:76px;text-align:right;font-weight:600;color:#c8102e;font-variant-numeric:tabular-nums}}
.rate small{{font-size:11px;font-weight:400}}
.bar{{height:3px;background:#f1f2f4;border-radius:2px;margin-top:4px;overflow:hidden}}
.bar i{{display:block;height:100%;background:#c8102e;border-radius:2px}}
.tag{{display:inline-block;margin-left:5px;padding:0 5px;border-radius:3px;font-size:10.5px;
  background:#fff4e5;color:#a86a12;border:1px solid #f5e0c3;vertical-align:1px}}
.tag.warn{{background:#fdecee;color:#c8102e;border-color:#f3c3c9}}
.newlow{{display:inline-block;margin-left:5px;padding:0 5px;border-radius:3px;font-size:10.5px;
  background:#e9f6ee;color:#1a7f42;border:1px solid #c9e8d4;vertical-align:1px}}
.first{{display:inline-block;margin-left:5px;padding:0 5px;border-radius:3px;font-size:10.5px;
  background:#e8f1fb;color:#1d5fbf;border:1px solid #c8dbf2;vertical-align:1px}}
.wish{{display:inline-block;margin-left:5px;padding:0 6px;border-radius:3px;font-size:10.5px;
  background:#f3e8ff;color:#7c3aed;border:1px solid #e2d0fd;vertical-align:1px;font-weight:600}}
.wishlink{{display:inline-block;margin-left:10px;padding:1px 9px;border-radius:20px;font-size:12px;
  background:#f3e8ff;color:#7c3aed;border:1px solid #e2d0fd;text-decoration:none;font-weight:600}}
.wishlink:hover{{background:#e9d9ff;text-decoration:none}}
.lowhint{{font-size:11px;color:#9aa0a8;margin-top:2px;font-weight:400}}
.foot{{color:#9aa0a8;font-size:11.5px;margin-top:24px;line-height:1.9}}
/* ---------- 手机端：表格拆成卡片，避免窄屏把商品名挤成竖排 ---------- */
@media (max-width:700px){{
  html,body{{overflow-x:hidden;max-width:100%}}
  body{{padding:18px 12px}}
  h1{{font-size:18px}}
  .sub{{font-size:11.5px;margin-bottom:16px;line-height:1.7}}
  .stats{{grid-template-columns:repeat(2,1fr);gap:8px;margin-bottom:16px}}
  .stat{{padding:10px 12px}}
  .stat .k{{font-size:11px}}
  .stat .v{{font-size:18px}}
  .funnel{{font-size:11.5px;padding:8px 10px;line-height:1.8;word-break:break-word}}
  h2{{font-size:13px;margin:20px 0 8px}}
  h2 .hint{{font-size:11px}}
  table,tbody,tr,td{{display:block;width:auto}}
  table{{border:0;background:transparent;border-radius:0}}
  thead{{display:none}}
  tr{{position:relative;background:#fff;border:1px solid #e6e8eb;border-radius:10px;
     padding:12px;margin-bottom:9px}}
  tr:last-child{{margin-bottom:0}}
  tbody tr:hover td{{background:transparent}}
  td{{border:0;padding:0}}
  .idx{{position:absolute;left:12px;top:12px;color:#c3c7cd;font-size:11px;width:auto}}
  .name{{padding-left:19px;margin-bottom:7px;line-height:1.55;word-break:break-word}}
  .name a{{font-size:14px}}
  .meta{{font-size:11px;line-height:1.6;margin-top:3px}}
  .num{{display:inline-block;width:auto;text-align:left;white-space:normal;
        margin-right:10px;font-size:13px}}
  .num b{{font-size:16px}}
  .num s{{font-size:11.5px}}
  .save{{display:inline-block;margin-right:8px;font-size:12px}}
  .rate{{display:inline-block;width:auto;text-align:left;font-size:13px}}
  .bar{{display:none}}
  .tag,.newlow,.first{{font-size:10px;margin-left:4px}}
  .lowhint{{font-size:10.5px}}
  .foot{{font-size:11px;line-height:1.8}}
}}
</style></head><body><div class="wrap">
  <h1>值得买日报 · {H.escape(meta['date'])}</h1>
  <div class="sub">抓取 {H.escape(meta['fetched_at'])}　请求 {meta['requests']} 次　
    来源 smzdm.com（时点快照，价格与库存随时变动）
    <a class="wishlink" href="./wishlist.html">⭐ 愿望单 <span id="wishCount" style="font-weight:400">{meta.get('watch_words', 0)} 个关键词</span></a>
    <a class="wishlink" href="./db.html" style="background:#eef4ff;color:#1d5fbf;border-color:#cfdefb">📚 数据库</a></div>
  {warn}{empty}
  <div class="stats">
    <div class="stat"><div class="k">折扣榜</div><div class="v">{len(hot)}<em> 条</em></div></div>
    <div class="stat"><div class="k">好价榜</div><div class="v">{len(feed_top)}<em> 条</em></div></div>
    <div class="stat"><div class="k">最低折</div><div class="v">{f"{zhe(hot[0]['discount_pct'])}<em>折</em>" if hot else "—"}</div></div>
    <div class="stat"><div class="k">最高立省</div><div class="v">{f"¥{max(d['save'] for d in hot):,.0f}" if hot else "—"}</div></div>
  </div>
  {funnel}
  <h2><span class="dot"></span>折扣榜 <span class="hint">按折扣力度排序 · 只收 {float(meta['min_disc']) / 10:.1f} 折以内</span></h2>
  <table><thead><tr><th>#</th><th>商品</th><th>到手价</th><th>折扣</th></tr></thead>
  <tbody>{''.join(row(d, i + 1) for i, d in enumerate(hot)) or '<tr><td colspan="4" style="color:#9aa0a8;padding:20px">无</td></tr>'}</tbody></table>
  <h2><span class="dot"></span>好价榜 <span class="hint">{H.escape(meta.get('feed_name') or '')} 原始顺序 · 前 {len(feed_top)} 条</span></h2>
  <table><thead><tr><th>#</th><th>商品</th><th>到手价</th><th>折扣</th></tr></thead>
  <tbody>{''.join(row(d, i + 1) for i, d in enumerate(feed_top)) or '<tr><td colspan="4" style="color:#9aa0a8;padding:20px">无</td></tr>'}</tbody></table>
  <div class="foot">页面版本 {H.escape(meta.get('build_at') or '')}<br>由 daily.py 自动生成 · <a href="./overview.html" style="color:#c8102e;text-decoration:none">运行概览</a> ·
    数据源 {H.escape(meta.get('feed_name') or '')}（全部好价排行榜）·
    仅抓列表页，未访问商品详情页 · 折扣按「现价/原价」计算，原价取自好价流描述，仅供参考。</div>
</div>
<script src="./watch.js"></script>
</body></html>"""


def render_push(hot: list[dict], meta: dict) -> tuple[str, str]:
    """Server酱：简短摘要 + 日报网页链接，手机上点开就能看完整榜单。"""
    date = datetime.now().strftime("%m-%d")
    site = (meta.get("site_url") or "").strip()

    if not hot:
        return (f"值得买 {date}｜今日无达标好价",
                f"今天没有达到力度阈值的商品。\n\n[查看日报]({site})")

    title = f"值得买日报 {date}｜最低 {zhe(hot[0]['discount_pct'])} 折"

    lines = [
        f"### 值得买日报 {date}",
        "",
        f"最低 **{zhe(hot[0]['discount_pct'])} 折** · "
        f"折扣榜 {len(hot)} 条 · 好价榜 {meta.get('feed_count', 0)} 条",
        "",
        f"👉 **[点这里查看完整日报]({site})**",
        "",
        "**今日前三**",
        "",
    ]
    for i, d in enumerate(hot[:3], 1):
        lines.append(f"{i}. {display_title(d['title'])}  "
                     f"¥{d['price']:g}（{zhe(d['discount_pct'])}折）")
    lines += ["", f"> {meta['fetched_at']} 抓取 · 价格随时变，下单前请在页面核对"]
    return title, "\n".join(lines)


# ---------------------------------------------------------------- 推送
def push_desktop(title: str, msg: str) -> str:
    if os.name != "nt":
        return "非 Windows 环境，跳过桌面通知"
    if not TOAST.exists():
        return "未找到 tools/toast.ps1"
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(TOAST), "-Title", title, "-Message", msg],
            capture_output=True, text=True, timeout=40,
        )
        return "ok"
    except Exception as e:  # noqa: BLE001
        return f"{type(e).__name__}: {e}"


def push_serverchan(key: str, title: str, body: str) -> str:
    if not key:
        return "未配置 sendkey，跳过"
    try:
        data = urllib.parse.urlencode({"title": title, "desp": body}).encode()
        req = urllib.request.Request(
            f"https://sctapi.ftqq.com/{key}.send", data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=15) as r:
            res = json.loads(r.read().decode("utf-8", "ignore"))
        return "ok" if res.get("code") == 0 else f"失败 code={res.get('code')} {res.get('message')}"
    except Exception as e:  # noqa: BLE001
        return f"{type(e).__name__}: {e}"


# ---------------------------------------------------------------- 主流程
def main() -> int:
    ap = argparse.ArgumentParser(description="值得买每日优惠推送")
    ap.add_argument("--force", action="store_true", help="忽略当天已推送状态")
    ap.add_argument("--dry-run", action="store_true", help="只生成报表，不推送")
    ap.add_argument("--no-crawl", action="store_true", help="不联网，用缓存")
    ap.add_argument("--probe", action="store_true", help="只探测是否被风控")
    ap.add_argument("--reset-dedup", action="store_true", help="清空商品目录（去重与低价历史）后再跑")
    ap.add_argument("--no-notify", action="store_true",
                    help="完整跑一遍（含入库、出报表），但不发通知、不标记已推送")
    args = ap.parse_args()

    if args.reset_dedup:
        CATALOG.unlink(missing_ok=True)
        log("已清空商品目录")

    cfg = load_config()
    log("=" * 60)

    if args.probe:
        f = Fetcher(cfg)
        try:
            f.get(FEED_TPL.format(1))
            log("好价榜可访问，未触发风控")
            return 0
        except probe.BlockedError:
            log("榜单页被风控拦截")
            return 2
        except Exception as e:  # noqa: BLE001
            log(f"探测失败 {type(e).__name__}: {e}")
            return 1

    # --no-notify 是测试模式：本来就不会推送，所以没理由被「今天已推送」挡住。
    # 冷却仍然生效（skip_reason 里冷却不受 force 影响）。
    reason = skip_reason(args.force or args.no_notify)
    if reason:
        log(f"跳过：{reason}")
        record_run("skipped", note=reason)
        return 0

    # 取数据
    if args.no_crawl:
        if not LAST_DATA.exists():
            log("没有缓存数据，无法离线生成")
            return 1
        data = json.loads(LAST_DATA.read_text(encoding="utf-8"))
        data["stale"] = True
        log(f"离线模式，使用 {data.get('fetched_at')} 的缓存")
    else:
        f = Fetcher(cfg)
        data = crawl(f, cfg.getint("crawl", "feed_pages", fallback=2))
        data["fetched_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        if data["deals"]:
            CACHE.mkdir(parents=True, exist_ok=True)
            LAST_DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                 encoding="utf-8")

    if not args.no_crawl:
        if data.get("blocked"):
            set_cooldown(cfg.getfloat("crawl", "cooldown_hours", fallback=6))
        elif data.get("deals"):
            reset_streak()   # 抓到数据了，说明此前的观察状态已解除

    catalog = Catalog()
    pool = Pool()
    deals = clean_deals(data.get("deals") or [])
    hot, stat, passed = pick(deals, cfg, catalog, pool)

    # 完全没有数据时，退到缓存
    if not deals:
        if LAST_DATA.exists() and not args.no_crawl:
            data = json.loads(LAST_DATA.read_text(encoding="utf-8"))
            data["stale"] = True
            deals = clean_deals(data.get("deals") or [])
            hot, stat, passed = pick(deals, cfg, catalog, pool)
            log("本次无有效数据，已回退到缓存")
        else:
            log("本次抓取完全失败且无缓存，不推送")
            record_run("failed", {"blocked": data.get("blocked", False)}, "抓取失败且无缓存")
            return 3

    # 抓到的数据源全部入库（不管有没有过关、有没有进榜）。
    # 样本越全，明天判断「比上次低」越准。
    feed_limit = cfg.getint("crawl", "top_n", fallback=50)
    if not args.dry_run:
        for d in deals:
            catalog.upsert(d)

    now = datetime.now()
    meta = {
        "date": now.strftime("%Y-%m-%d"),
        "fetched_at": data.get("fetched_at") or now.strftime("%Y-%m-%d %H:%M"),
        "data_date": (data.get("fetched_at") or "")[:10],
        "requests": data.get("requests", 0),
        "scanned": len(deals),
        "blocked": data.get("blocked", False),
        "stale": data.get("stale", False),
        "min_disc": cfg.get("filter", "min_discount_pct", fallback="30"),
        "stat": stat,
        "cats": split_list(cfg.get("interest", "categories", fallback="")),
        "dedup_days": cfg.getint("dedup", "days", fallback=7),
        "feed_name": FEED_NAME,
        "site_url": cfg.get("push", "site_url", fallback=""),
        "watch_edit_url": cfg.get("watch", "edit_url", fallback=""),
        "watch_words": stat.get("watch_words", 0),
        "watch_raw_url": cfg.get("watch", "raw_url", fallback=""),
        "watch_api_url": cfg.get("watch", "api_url", fallback=""),
        "build_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "hot_count": len(hot),
        "feed_count": min(len(passed), feed_limit),
        "catalog_count": len(catalog.records),
    }

    # 报表
    REPORTS.mkdir(parents=True, exist_ok=True)
    report = REPORTS / f"{now:%Y-%m-%d}.html"
    report.write_text(render_html(hot, passed, meta), encoding="utf-8")
    log(f"报表已生成 {report}")

    log(f"数据源 {meta['scanned']} 条 → 好价榜 {min(len(passed), feed_limit)} 条，"
        f"折扣榜 {len(hot)} 条")
    for d in hot[:5]:
        log(f"  {zhe(d['discount_pct']):>4}折 ¥{d['price']:<7g} 省{d['save']:<6g} {d['title'][:30]}")

    if args.dry_run:
        log("--dry-run：跳过推送")
        record_run("dry", meta, "只生成报表，未推送")
        return 0

    if args.no_notify:
        # 测试模式：抓取、入库、出报表都照常，只是不发通知，
        # 也不记录「今天已推送」，所以之后正式跑一次仍会正常推送。
        pool.save()
        catalog.save()
        export_db(catalog)
        log(f"--no-notify：跳过所有通知（未记录已推送状态）· 目录共 {len(catalog.records)} 条")
        record_run("test", meta, "静默测试，未发送通知")
        return 0

    if not cfg.getboolean("push", "enabled", fallback=True):
        # 总开关关掉时：照常抓取、入库、出报表，只是不打扰。
        pool.save()
        catalog.save()
        export_db(catalog)
        log("推送已停用（[push] enabled = false），只更新日报")
        # 仍然标记「今天已运行」。GitHub 的定时任务会延迟甚至整点丢失，
        # 有了这个标记才能加备用时间点——先到的那次跑，后来的自动跳过。
        MARK_PUSH.parent.mkdir(parents=True, exist_ok=True)
        MARK_PUSH.write_text(now.strftime("%Y-%m-%d"), encoding="utf-8")
        record_run("disabled", meta, "推送已停用，仅更新日报")
        return 0

    # 推送只发「近期没推过」的，报表则展示完整榜单。
    fresh = [d for d in hot if not d.get("pushed_before")]
    if not fresh:
        log(f"折扣榜 {len(hot)} 条全部近期推过，今天没有新增，跳过推送")
        catalog.save()
        record_run("skipped", meta, "今日无新增好价，未推送")
        return 0

    title, body = render_push(fresh, meta)
    # 云端把 key 放 GitHub Secrets 里注入，避免明文进仓库
    key = (os.environ.get("SERVERCHAN_SENDKEY", "").strip()
           or cfg.get("push", "serverchan_sendkey", fallback="").strip())

    if cfg.getboolean("push", "desktop_notify", fallback=True):
        summary = f"{len(fresh)} 条 · " + fresh[0]["title"][:24]
        log(f"桌面通知：{push_desktop(title, summary)}")

    if key:
        log(f"微信推送：{push_serverchan(key, title, body)}")
    else:
        log("未配置 serverchan_sendkey，仅桌面通知")

    for d in fresh:
        catalog.set_pushed(d)
    pool.save()
    catalog.save()
    export_db(catalog)
    MARK_PUSH.parent.mkdir(parents=True, exist_ok=True)
    MARK_PUSH.write_text(now.strftime("%Y-%m-%d"), encoding="utf-8")
    log(f"已记录今日状态，商品目录共 {len(catalog.records)} 条记录")
    record_run("ok", meta, "已推送", pushed=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
