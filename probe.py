# -*- coding: utf-8 -*-
import re, json, sys, urllib.request, urllib.error

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"


class BlockedError(RuntimeError):
    """被站点风控拦截（腾讯验证码 / JS 挑战）"""


def check_blocked(html):
    """识别风控页：正常页面不会同时满足『体积很小 + 含验证码特征』"""
    if len(html) < 4000:
        low = html.lower()
        if "tcaptcha" in low or "captcha" in low or "probev" in low:
            raise BlockedError("触发站点反爬验证码（TCaptcha），请降低频率或更换网络后重试")


def get(url, cookie=None):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://www.smzdm.com/",
    })
    if cookie: req.add_header("Cookie", cookie)
    with urllib.request.urlopen(req, timeout=30) as r:
        html = r.read().decode("utf-8", "ignore")
    check_blocked(html)
    return r.status, html

CARD = re.compile(r'<div class="feed-hot-card"[^>]*articleid="(\d+)"[^>]*data-position="(\d+)"[^>]*data-type="([^"]*)"[^>]*data-tab="([^"]*)"[\s\S]*?href="(https://www\.smzdm\.com/p/\d+/)"[\s\S]*?<div class="feed-hot-title">([^<]*)</div>\s*<span class="z-highlight">([^<]*)</span>')
ORDER = re.compile(r'<span class="hot-order">(\d+)</span>')

def parse(html):
    out, seen = [], set()
    for m in CARD.finditer(html):
        aid, pos, typ, tab, url, title, price = m.groups()
        if aid in seen: continue
        seen.add(aid)
        out.append({"article_id": aid, "pos": int(pos), "type": typ, "tab": tab,
                    "title": title.strip(), "price": price.strip(), "url": url})
    return out

if __name__ == "__main__":
    urls = sys.argv[1:]
    for u in urls:
        try:
            code, html = get(u)
            items = parse(html)
            tabs = {}
            for it in items: tabs[it["tab"]] = tabs.get(it["tab"], 0) + 1
            print(f"[{code}] {u}\n  html={len(html)}  items={len(items)}  tabs={tabs}")
            for it in items[:5]:
                print(f"   #{it['pos']:>2} [{it['tab']}] {it['title'][:38]} | {it['price']}")
        except Exception as e:
            print(f"[ERR] {u} -> {type(e).__name__}: {e}")
