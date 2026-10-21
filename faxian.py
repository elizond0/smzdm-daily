# -*- coding: utf-8 -*-
"""
faxian.smzdm.com 好价流 / 白菜榜 解析器
列表页自带：标题、到手价、商城、优惠描述（含活动售价与满减规则）—— 无需访问详情页。
"""
import re, json, time, sys, urllib.request, os

from urllib.parse import urljoin

# 输出统一落在脚本所在目录，从任何位置运行都能正确落盘
BASE = os.path.dirname(os.path.abspath(__file__))

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9",
           "Referer": "https://www.smzdm.com/"}

class BlockedError(RuntimeError):
    """被站点风控拦截（腾讯验证码 / JS 挑战）"""

def check_blocked(html):
    if len(html) < 4000:
        low = html.lower()
        if "tcaptcha" in low or "captcha" in low or "probev" in low:
            raise BlockedError("触发站点反爬验证码（TCaptcha），本页无数据")

def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=25) as r:
        html = r.read().decode("utf-8", "ignore")
    check_blocked(html)
    return r.status, html

ITEM = re.compile(r'<li class="J_feed_za"([\s\S]*?)</li>')
AID = re.compile(r'articleid="\d+_(\d+)"')
TS = re.compile(r'timesort="(\d+)"')
H5 = re.compile(r'<h5 class="feed-ver-title">([\s\S]*?)</h5>')
H5_URL = re.compile(r'href="([^"]+)"')
PRICE = re.compile(r'class="z-highlight z-ellipsis">([^<]+)<')
DESC = re.compile(r'class="feed-ver-descripe">([\s\S]*?)</div>')
TIME_ = re.compile(r'feed-ver-date">\s*([^<]+?)\s*<')
MALL = re.compile(r'class="tag-bottom-right">([^<]+)<')
TOPLEFT = re.compile(r'class="tag-top-left[^"]*">([^<]+)<')
# 点「值」的数量。未点过是 unvoted-wrap，点过是 voted-wrap，两者都要认。
ZHI = re.compile(r'class="(?:un)?voted-wrap">\s*<i class="z-icon-zhi"></i><span>(\d+)</span>')
# 评论数
COMMENT = re.compile(r'z-icon-comment"></i>\s*(\d+)')

def txt(s):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', s)).strip()

def parse_price(s):
    m = re.search(r'(\d+(?:\.\d+)?)', s.replace(',', ''))
    return float(m.group(1)) if m else None

def parse_origin(desc):
    """从描述抽取原价/活动售价"""
    for p in (r'活动售价(\d+(?:\.\d+)?)元', r'原价(\d+(?:\.\d+)?)元',
              r'售价(\d+(?:\.\d+)?)元', r'专柜价(\d+(?:\.\d+)?)元',
              r'日常价(\d+(?:\.\d+)?)元', r'标价(\d+(?:\.\d+)?)元'):
        m = re.search(p, desc)
        if m:
            return float(m.group(1))
    return None

def parse_feed(html):
    out = []
    for m in ITEM.finditer(html):
        b = m.group(1)
        h5 = H5.search(b)
        if not h5:
            continue
        # 标题去掉内嵌 <object> 标签块
        h5_inner = re.sub(r'<object>[\s\S]*?</object>', ' ', h5.group(1))
        title = txt(h5_inner)
        u = H5_URL.search(h5.group(1))
        url = u.group(1) if u else None
        p = PRICE.search(b)
        d = DESC.search(b)
        tm = TIME_.search(b)
        mall = MALL.search(b)
        zhi = ZHI.search(b)
        cmt = COMMENT.search(b)

        price_text = txt(p.group(1)) if p else ''
        desc = txt(d.group(1)) if d else ''
        price = parse_price(price_text)
        origin = parse_origin(desc)
        rate = round(price / origin * 100, 1) if price and origin and origin > price else None
        if not title:
            continue
        out.append({
            "article_id": AID.search(b).group(1) if AID.search(b) else None,
            "title": title,
            "url": url.replace("http://", "https://") if url else None,
            "price": price,
            "price_text": price_text,
            "origin_price": origin,
            "save": round(origin - price, 2) if price and origin else None,
            "discount_pct": rate,
            "mall": mall.group(1).strip() if mall else None,
            "zhi": int(zhi.group(1)) if zhi else 0,
            "comments": int(cmt.group(1)) if cmt else 0,
            "label": TOPLEFT.search(b).group(1).strip() if TOPLEFT.search(b) else None,
            "desc": desc[:180],
            "time": txt(tm.group(1)) if tm else None,
        })
    return out

SOURCES = {
    "白菜榜(9.9专区)": "https://faxian.smzdm.com/9kuai9/h3s0t0f0p1/",
    "好价精选": "https://faxian.smzdm.com/h4s0t0f0c0p1/",
}

if __name__ == "__main__":
    allrows = []
    for name, url in SOURCES.items():
        try:
            code, html = fetch(url)
            items = parse_feed(html)
            for it in items:
                it["source"] = name
            print(f"[{name}] HTTP {code} 解析 {len(items)} 条  "
                  f"含原价 {sum(1 for x in items if x['origin_price'])} 条")
            for it in items[:3]:
                print(f"   ¥{it['price']} (原 {it['origin_price']}) "
                      f"{it['discount_pct']}%  {it['mall']}  {it['title'][:32]}")
            allrows += items
        except Exception as e:
            print(f"[{name}] ERR {type(e).__name__}: {e}")

    # 抓空时绝不覆盖历史数据（封禁期跑定时任务会白清空，这是必须的护栏）
    if not allrows:
        print("\n[中止] 未获取到任何数据，保留原有 faxian.json 不覆盖")
        sys.exit(1)

    rated = sorted([x for x in allrows if x["discount_pct"]], key=lambda x: x["discount_pct"])
    print(f"\n合计 {len(allrows)} 条，可算折扣 {len(rated)} 条\n")
    print(f"{'折扣':>6} {'到手价':>8} {'原价':>8} {'立省':>7} {'商城':<5} 商品")
    print("-" * 92)
    for x in rated[:12]:
        print(f"{x['discount_pct']:>5.1f}% {x['price']:>8.1f} {x['origin_price']:>8.1f} "
              f"{x['save']:>7.1f} {str(x['mall'])[:4]:<5} {x['title'][:34]}")
    json.dump({"fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"), "items": allrows},
              open(os.path.join(BASE, "faxian.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("\n已保存 faxian.json")
