# -*- coding: utf-8 -*-
"""构建 demo.html：多页采集好价流 + 人气榜，过滤券类/过期，按优惠力度排序"""
import json, html, re, time, os

import faxian
from smzdm import parse_rank
import probe

# 输出统一落在脚本所在目录，从任何位置运行都能正确落盘
BASE = os.path.dirname(os.path.abspath(__file__))

PAGES = 3
FEEDS = {
    "白菜榜": "https://faxian.smzdm.com/9kuai9/h3s0t0f0p{}/",
    "好价精选": "https://faxian.smzdm.com/h4s0t0f0c0p{}/",
}

JUNK = re.compile(r'每日可领|红包|外卖|满\d+减|神券|领券|话费|流量|积分兑换|抽奖|签到')
# 需要额外门槛才能拿到的价格（88VIP/淘金币/凑单/试用/需用券/秒杀），单独标注
COND = re.compile(r'88VIP|淘金币|凑单|试用价|需用券|秒杀|学生|会员|专享|返\d+积分|折合')
# 组合条件（叠加多项门槛）的极端低价，可信度低，不进主榜
MULTI = re.compile(r'凑单|淘金币|返\d+积分|折合')

def collect():
    rows, seen = [], set()
    for name, tpl in FEEDS.items():
        for p in range(1, PAGES + 1):
            try:
                _, h = faxian.fetch(tpl.format(p))
            except Exception:
                break
            for it in faxian.parse_feed(h):
                if not it["title"] or it["article_id"] in seen:
                    continue
                if JUNK.search(it["title"]) or it["title"].startswith("过期"):
                    continue
                if not it["price"] or it["price"] > 20000:
                    continue
                seen.add(it["article_id"])
                it["source"] = name
                # 门槛标注
                conds = []
                if re.search(r'88VIP', it["title"] + it["desc"]): conds.append("88VIP")
                if re.search(r'淘金币', it["title"] + it["desc"]): conds.append("淘金币")
                if re.search(r'凑单', it["title"] + it["desc"]): conds.append("凑单")
                if re.search(r'试用价', it["title"] + it["desc"]): conds.append("试用")
                if re.search(r'需用券|需领券', it["price_text"] + it["desc"]): conds.append("需券")
                if re.search(r'秒杀', it["title"] + it["desc"]): conds.append("秒杀")
                if re.search(r'学生|会员', it["title"]): conds.append("会员")
                it["conds"] = conds
                rows.append(it)
    return rows

rows = collect()
rank_code, rank_html = probe.get("https://www.smzdm.com/top/")
rank_items = parse_rank(rank_html)
seen_r, rank_uniq = set(), []
for it in sorted(rank_items, key=lambda x: x["rank"]):
    if it["article_id"] in seen_r:
        continue
    seen_r.add(it["article_id"])
    rank_uniq.append(it)

def clean(x):
    """剔除叠加多重门槛导致的失真低价"""
    return not (set(x["conds"]) & {"凑单", "淘金币", "试用"})

# 抓空/被封时中止，避免覆盖已有的 demo.html 与数据
if not rows or not rank_uniq:
    print(f"[中止] 数据不足（好价 {len(rows)} 条 / 榜单 {len(rank_uniq)} 条），"
          f"保留原有 demo.html 与 demo_data.json 不覆盖")
    raise SystemExit(1)

rated = sorted([x for x in rows if x["discount_pct"] and x["price"] and x["price"] >= 5
                and 20 <= x["discount_pct"] <= 85 and clean(x)],
               key=lambda x: (x["discount_pct"], -(x["save"] or 0)))
cheap = sorted([x for x in rows if x["price"] and 1 <= x["price"] <= 20 and clean(x)],
               key=lambda x: x["price"])[:12]

def deal_row(x, i):
    pct = x["discount_pct"]
    if pct:
        bar = f'<div class="bar"><i style="width:{max(4, pct)}%"></i></div>'
        rate = f'{pct:.0f}<small>%</small>'
    else:
        bar, rate = "", '<span class="muted">—</span>'
    origin = f'<s>¥{x["origin_price"]:g}</s>' if x["origin_price"] else ''
    conds = "".join(f'<span class="tag">{c}</span>' for c in x.get("conds", []))
    return f"""<tr>
  <td class="idx">{i}</td>
  <td class="name"><a href="{x['url']}" target="_blank">{html.escape(x['title'])}</a>{conds}
      <div class="meta">{html.escape(x['mall'] or '—')} · {html.escape(x['source'])} · {html.escape(x['time'] or '')}</div></td>
  <td class="num"><b>¥{x['price']:g}</b> {origin}</td>
  <td class="num save">{'省¥%g' % x['save'] if x['save'] else '<span class="muted">—</span>'}</td>
  <td class="rate">{rate}{bar}</td>
</tr>"""

deal_html = "".join(deal_row(x, i + 1) for i, x in enumerate(rated[:20]))
cheap_html = "".join(deal_row(x, i + 1) for i, x in enumerate(cheap))

rank_rows = "".join(
    f"""<tr><td class="idx">{it['rank']}</td><td class="cat">{html.escape(it['tab'])}</td>
    <td class="name"><a href="{it['url']}" target="_blank">{html.escape(it['title'])}</a></td>
    <td class="num"><b>{html.escape(it['price_text'])}</b></td></tr>"""
    for it in rank_uniq)

page = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>什么值得买 · 数据抓取 Demo</title><style>
*{{box-sizing:border-box}}
body{{margin:0;padding:36px 20px;background:#f5f6f8;color:#16181c;
  font:14px/1.65 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}}
.wrap{{max-width:1060px;margin:0 auto}}
h1{{font-size:21px;margin:0 0 4px;letter-spacing:-.2px}}
.sub{{color:#71767e;font-size:12.5px;margin-bottom:24px}}
.stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:28px}}
.stat{{background:#fff;border:1px solid #e6e8eb;border-radius:10px;padding:13px 16px}}
.stat .k{{font-size:11.5px;color:#71767e}}
.stat .v{{font-size:21px;font-weight:600;margin-top:1px;letter-spacing:-.3px}}
.stat .v em{{font-size:12px;font-style:normal;color:#71767e;font-weight:400;margin-left:2px}}
h2{{font-size:14px;margin:30px 0 10px;display:flex;align-items:center;gap:8px}}
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
.rate{{width:76px;text-align:right;font-weight:600;color:#c8102e;
  font-variant-numeric:tabular-nums}}
.rate small{{font-size:11px;font-weight:400}}
.bar{{height:3px;background:#f1f2f4;border-radius:2px;margin-top:4px;overflow:hidden}}
.bar i{{display:block;height:100%;background:#c8102e;border-radius:2px}}
.muted{{color:#b6bac1}}
.tag{{display:inline-block;margin-left:5px;padding:0 5px;border-radius:3px;font-size:10.5px;
  background:#fff4e5;color:#a86a12;border:1px solid #f5e0c3;vertical-align:1px}}
.foot{{color:#9aa0a8;font-size:11.5px;margin-top:26px;line-height:1.9}}
</style></head><body><div class="wrap">
  <h1>什么值得买 · 数据抓取 Demo</h1>
  <div class="sub">抓取时间 {time.strftime('%Y-%m-%d %H:%M')}　来源 smzdm.com（时点快照，价格与库存随时变动）</div>

  <div class="stats">
    <div class="stat"><div class="k">好价条目</div><div class="v">{len(rows)}<em> 条</em></div></div>
    <div class="stat"><div class="k">可算折扣</div><div class="v">{len(rated)}<em> 条</em></div></div>
    <div class="stat"><div class="k">最大力度</div><div class="v">{rated[0]['discount_pct']:.0f}%<em> 折扣</em></div></div>
    <div class="stat"><div class="k">榜单条目</div><div class="v">{len(rank_uniq)}<em> 条</em></div></div>
  </div>

  <h2><span class="dot"></span>优惠力度榜 <span class="hint">按现价/原价排序，折扣越低越狠</span></h2>
  <table><thead><tr><th>#</th><th>商品</th><th>到手价</th><th>立省</th><th>折扣</th></tr></thead>
  <tbody>{deal_html}</tbody></table>

  <h2><span class="dot"></span>白菜价 <span class="hint">到手价 ≤ 20 元</span></h2>
  <table><thead><tr><th>#</th><th>商品</th><th>到手价</th><th>立省</th><th>折扣</th></tr></thead>
  <tbody>{cheap_html}</tbody></table>

  <h2><span class="dot"></span>人气排行榜 <span class="hint">smzdm.com/top/ 原榜位</span></h2>
  <table><thead><tr><th>#</th><th>分类</th><th>商品</th><th>价格</th></tr></thead>
  <tbody>{rank_rows}</tbody></table>

  <div class="foot">
    说明：排行榜页为 CDN 静态快照，可稳定抓取；商品详情页有腾讯验证码风控，高频请求会被临时封禁。
    上表「原价」全部来自好价流列表页的优惠描述，未访问详情页。
  </div>
</div></body></html>"""

open(os.path.join(BASE, "demo.html"), "w", encoding="utf-8").write(page)
print(f"已生成 demo.html  好价 {len(rows)} 条 / 可算折扣 {len(rated)} 条 / 榜单 {len(rank_uniq)} 条")
json.dump({"fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"), "deals": rows, "rank": rank_uniq},
          open(os.path.join(BASE, "demo_data.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
