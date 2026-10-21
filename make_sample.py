# -*- coding: utf-8 -*-
"""用已抓取的数据生成一份榜单样例页面（纯静态 HTML，可直接打开）"""
import json, re, html, time, os

import probe

# 输出统一落在脚本所在目录，从任何位置运行都能正确落盘
BASE = os.path.dirname(os.path.abspath(__file__))

code, h = probe.get("https://www.smzdm.com/top/")
from smzdm import parse_rank
items = parse_rank(h)

# 用上一轮成功补全的折扣数据做样本
try:
    old = {x["article_id"]: x for x in json.load(open(os.path.join(BASE, "ranking.json"), encoding="utf-8"))["items"]}
except Exception:
    old = {}

for it in items:
    o = old.get(it["article_id"], {})
    it["price"] = o.get("price")
    it["origin_price"] = o.get("origin_price")
    it["save"] = o.get("save")
    it["discount_pct"] = o.get("discount_pct")
    it["mall"] = o.get("mall")

# 合并：去掉重复 article_id，按 rank
seen, uniq = set(), []
for it in sorted(items, key=lambda x: x["rank"]):
    if it["article_id"] in seen:
        continue
    seen.add(it["article_id"])
    uniq.append(it)

discounted = [x for x in uniq if x["discount_pct"]]
discounted.sort(key=lambda x: x["discount_pct"])

rows = []
for it in uniq:
    if it["discount_pct"]:
        badge = f'<span class="rate">{it["discount_pct"]:.0f}%</span>'
        price = f'<b>¥{it["price"]:g}</b> <s>¥{it["origin_price"]:g}</s>'
        save = f'省 ¥{it["save"]:g}'
    else:
        badge = '<span class="rate none">—</span>'
        price = f'<b>{html.escape(it["price_text"])}</b>'
        save = "待补全"
    rows.append(f"""<tr>
      <td class="rank">{it['rank']}</td>
      <td class="cat">{html.escape(it['tab'])}</td>
      <td class="name"><a href="{it['url']}" target="_blank">{html.escape(it['title'])}</a></td>
      <td class="price">{price}</td>
      <td class="save">{save}</td>
      <td>{badge}</td>
    </tr>""")

page = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>什么值得买 · 排行榜抓取样例</title>
<style>
  *{{box-sizing:border-box}}
  body{{margin:0;padding:32px 20px;background:#f6f7f9;color:#1a1a1a;
       font:14px/1.6 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}}
  .wrap{{max-width:1080px;margin:0 auto}}
  h1{{font-size:22px;margin:0 0 6px}}
  .sub{{color:#6b7280;font-size:13px;margin-bottom:20px}}
  .cards{{display:flex;gap:12px;margin-bottom:22px;flex-wrap:wrap}}
  .card{{background:#fff;border:1px solid #e8eaed;border-radius:10px;padding:14px 18px;min-width:150px}}
  .card .k{{font-size:12px;color:#6b7280}}
  .card .v{{font-size:22px;font-weight:600;margin-top:2px}}
  .card .v em{{font-size:13px;font-style:normal;color:#6b7280;font-weight:400}}
  table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e8eaed;
         border-radius:10px;overflow:hidden}}
  th{{text-align:left;font-size:12px;color:#6b7280;font-weight:500;background:#fafbfc;
      padding:10px 12px;border-bottom:1px solid #e8eaed}}
  td{{padding:11px 12px;border-bottom:1px solid #f1f3f5;vertical-align:middle}}
  tr:last-child td{{border-bottom:0}}
  tr:hover td{{background:#fcfcfd}}
  .rank{{color:#9ca3af;font-variant-numeric:tabular-nums;width:38px}}
  .cat{{font-size:12px;color:#6b7280;width:80px}}
  .name a{{color:#1a1a1a;text-decoration:none}}
  .name a:hover{{color:#c8102e;text-decoration:underline}}
  .price{{white-space:nowrap;font-variant-numeric:tabular-nums}}
  .price b{{color:#c8102e;font-size:15px}}
  .price s{{color:#b0b5bd;font-size:12px;margin-left:5px}}
  .save{{font-size:12px;color:#6b7280;white-space:nowrap}}
  .rate{{display:inline-block;min-width:48px;text-align:center;padding:2px 8px;border-radius:5px;
        background:#fdecee;color:#c8102e;font-weight:600;font-size:12px}}
  .rate.none{{background:#f1f3f5;color:#a0a6ae;font-weight:400}}
</style></head><body><div class="wrap">
  <h1>什么值得买 · 排行榜抓取样例</h1>
  <div class="sub">抓取时间 {time.strftime('%Y-%m-%d %H:%M')}　来源 www.smzdm.com/top/（时点快照，价格随时变动）</div>
  <div class="cards">
    <div class="card"><div class="k">榜单条目</div><div class="v">{len(uniq)}<em> 条</em></div></div>
    <div class="card"><div class="k">已补全原价</div><div class="v">{len(discounted)}<em> 条</em></div></div>
    <div class="card"><div class="k">最大力度</div><div class="v">{discounted[0]['discount_pct']:.0f}%<em> 折扣</em></div></div>
    <div class="card"><div class="k">最高立省</div><div class="v">¥{max(x['save'] for x in discounted):,.0f}</div></div>
  </div>
  <table>
    <thead><tr><th>#</th><th>分类</th><th>商品</th><th>价格</th><th>优惠</th><th>折扣</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</div></body></html>"""

open(os.path.join(BASE, "sample.html"), "w", encoding="utf-8").write(page)
print("已生成 sample.html  条目", len(uniq), " 已补全", len(discounted))
