# -*- coding: utf-8 -*-
"""
什么值得买 - 排行榜 + 优惠力度 抓取 Demo
用法:
    python smzdm.py            # 抓榜单前 20 条并补全原价
    python smzdm.py 40         # 前 40 条
输出:
    ranking.json  /  控制台表格
"""
import re, json, sys, time, urllib.request, urllib.error, os

from concurrent.futures import ThreadPoolExecutor

# 输出统一落在脚本所在目录，从任何位置运行都能正确落盘
BASE = os.path.dirname(os.path.abspath(__file__))

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

RANK_URL = "https://www.smzdm.com/top/"
DETAIL_URL = "https://www.smzdm.com/p/{}/"

HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://www.smzdm.com/",
}

class BlockedError(RuntimeError):
    """被站点风控拦截（腾讯验证码），重试无用，直接放弃"""

def fetch(url, retry=2):
    for i in range(retry + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=25) as r:
                html = r.read().decode("utf-8", "ignore")
            if len(html) < 4000 and ("tcaptcha" in html.lower() or "captcha" in html.lower()):
                raise BlockedError("触发反爬验证码")
            return r.status, html
        except BlockedError:
            raise
        except Exception:
            if i == retry:
                raise
            time.sleep(1.5 * (i + 1))

# ---------- 1. 榜单解析 ----------
CARD = re.compile(
    r'<div class="feed-hot-card"[^>]*articleid="(\d+)"[^>]*'
    r'data-position="(\d+)"[^>]*data-type="([^"]*)"[^>]*data-tab="([^"]*)"'
    r'[\s\S]*?href="(https://www\.smzdm\.com/p/\d+/)"'
    r'[\s\S]*?<div class="feed-hot-title">([^<]*)</div>\s*'
    r'<span class="z-highlight">([^<]*)</span>'
)

def parse_rank(html):
    items, seen = [], set()
    for m in CARD.finditer(html):
        aid, pos, typ, tab, url, title, price = m.groups()
        if aid in seen:
            continue
        seen.add(aid)
        items.append({
            "article_id": aid,
            "rank": int(pos),
            "label": typ,
            "tab": tab,
            "title": title.strip(),
            "price_text": price.strip(),
            "url": url,
        })
    return items

# ---------- 2. 详情页解析 ----------
RE_NOW = re.compile(r'class="price-large"><span class="num">([\d.]+)</span>')
RE_OLD = re.compile(r'<span class="line-through">([\d.]+)\s*元</span>')
RE_SAVE = re.compile(r'【省([\d.]+)元】')
RE_MALL = re.compile(r"mall_name'\s*:\s*'([^']+)'")
RE_TITLE = re.compile(r'<title>【?省?[\d.]*元?】?([^<_]*)')

def parse_detail(html):
    now = RE_NOW.search(html)
    old = RE_OLD.search(html)
    save = RE_SAVE.search(html)
    mall = RE_MALL.search(html)
    now = float(now.group(1)) if now else None
    old = float(old.group(1)) if old else None
    save = float(save.group(1)) if save else (round(old - now, 2) if old and now else None)
    rate = round(now / old * 100, 1) if now and old and old > 0 else None
    return {
        "price": now,
        "origin_price": old,
        "save": save,
        "discount_pct": rate,   # 现价/原价，越低越划算
        "mall": mall.group(1) if mall else None,
    }

def enrich(item):
    try:
        _, html = fetch(DETAIL_URL.format(item["article_id"]))
        item.update(parse_detail(html))
    except Exception as e:
        item.update({"price": None, "origin_price": None, "save": None,
                     "discount_pct": None, "mall": None, "error": type(e).__name__})
    return item

def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 20

    code, html = fetch(RANK_URL)
    items = parse_rank(html)
    print(f"[榜单] HTTP {code}  抓到 {len(items)} 条")
    if not items:
        print("[中止] 榜单无数据，保留原有 ranking.json 不覆盖")
        return

    targets = sorted(items, key=lambda x: x["rank"])[:limit]
    with ThreadPoolExecutor(max_workers=5) as ex:
        targets = list(ex.map(enrich, targets))

    ok = [x for x in targets if x["discount_pct"]]
    ok.sort(key=lambda x: x["discount_pct"])
    print(f"[详情] 成功补全 {len(ok)}/{len(targets)} 条\n")

    print(f"{'折扣':>6} {'现价':>9} {'原价':>9} {'立省':>7}  商城   商品")
    print("-" * 96)
    for x in ok:
        print(f"{x['discount_pct']:>5.1f}% {x['price']:>8.1f} {x['origin_price']:>8.1f} "
              f"{x['save']:>6.1f}  {str(x['mall'])[:4]:<5} {x['title'][:40]}")

    with open(os.path.join(BASE, "ranking.json"), "w", encoding="utf-8") as f:
        json.dump({"fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                   "total": len(items), "items": targets}, f,
                  ensure_ascii=False, indent=2)
    print("\n已保存 ranking.json")

if __name__ == "__main__":
    main()
