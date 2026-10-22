# 什么值得买优惠推送

每天定时抓取什么值得买「全部好价排行榜」，筛出折扣力度大的商品，生成静态日报页，并可推到微信。

线上日报：https://elizond0.github.io/smzdm-daily/
运行概览：https://elizond0.github.io/smzdm-daily/overview.html
数据库：https://elizond0.github.io/smzdm-daily/db.html
愿望单：https://elizond0.github.io/smzdm-daily/wishlist.html

## 架构

```
GitHub Actions（每天 4 次：北京 7/12/17/22 点）
   │
   ├─ 抓取 faxian.smzdm.com 前 5 页（约 90 条）
   ├─ 入库 data/catalog.json（历史最低价 / 最低折扣）
   ├─ 入池 data/pool.json（24 小时滚动窗口）
   ├─ 生成 docs/index.html + docs/db.json + docs/history.json
   └─ 提交回仓库 → GitHub Pages 自动发布
```

**单一真源是 GitHub 仓库**。本地目录只是工作副本，Pages 上的页面是产出的静态站。

## 零依赖

整个项目只用 Python 标准库，不需要 `pip install`。要求 Python 3.10+（用到 `X | None` 类型语法）。

## 两种迭代方式

### 方式一：本机（可跑测试）

```bash
cd 什么值得买优惠推送
./build/venv/Scripts/python.exe daily.py --no-crawl --dry-run --force   # 用缓存数据演练
./build/venv/Scripts/python.exe daily.py --no-crawl --no-notify         # 静默跑，不推送
```

- `--no-crawl` 用 `build/cache/latest.json` 的缓存数据，不打网络
- `--dry-run` 只生成报表，不写状态
- `--no-notify` 跳推送
- `--force` 绕过「今天已推送」判断

### 方式二：云端（改代码最快）

在 GitHub 仓库页按 `.` 打开 **github.dev**（浏览器内 VS Code），或新建 **Codespaces**。

两者都是真云端执行，Python 3.12 预装，改完直接 commit，Actions 自动跑。

> 注意：资料库里存的是文档和文件，不能执行 Python，也没法跑测试。要"云上跑代码"，用 github.dev 或 Codespaces。

## 从对话同步到 GitHub

本机 `git push` 常因网络代理失败（`CONNECT tunnel failed`）。可改用 GitHub Contents API 直接写文件：

```
GET  /repos/{owner}/{repo}/contents/{path}        → 取 sha
PUT  /repos/{owner}/{repo}/contents/{path}        → base64 内容 + sha
```

Token 放在 `.deploy.token`（已 gitignore），Actions 里用 `GITHUB_TOKEN`。

## 文件说明

| 文件 | 作用 |
|---|---|
| `daily.py` | 主程序：抓取、筛选、去重、渲染、推送 |
| `faxian.py` | 列表页抓取与解析 |
| `probe.py` | 访问前的站点可用性探测 |
| `template.html` | 日报页面模板（`{{key}}` 占位符，改样式只动这个） |
| `watchlist.txt` | 愿望单关键词，一行一个 |
| `docs/` | Pages 发布目录（生成的页面 + watch.js / db.html / wishlist.html / overview.html） |
| `data/` | 跨运行持久化：catalog.json、pool.json、run_history.json、state/ |
| `.github/workflows/daily.yml` | 定时任务定义 |

## 配置

`config.example.ini` 是模板，Actions 每次用它生成 `config.ini`；本机用自己的 `config.ini`（已 gitignore）。

关键项：

| 项 | 说明 |
|---|---|
| `filter.min_discount_pct` | 折扣榜阈值，35 = 3.5 折以内 |
| `filter.max_items` | 折扣榜上限 |
| `crawl.top_n` | 好价榜展示条数 |
| `crawl.feed_pages` | 抓取页数，调小可降低风控风险 |
| `push.enabled` | 微信推送总开关，当前 `false` |
| `dedup.days` | 同一商品几天内不重复推送 |

密钥走 GitHub Secrets（`SERVERCHAN_SENDKEY`），不进仓库。

## 数据模型

`data/catalog.json` 一条记录 = 一个商品身份：

```json
{
  "norm": "规范化标题（去营销词、标点）",
  "specs": [["500","g"]],
  "title": "原始标题",
  "ids": ["183696862"],
  "low": 14.9,              // 历史最低价
  "low_disc": 20.0,         // 历史最低折扣（百分数，20 = 2 折）
  "first": "2026-10-19",
  "last": "2026-10-21",
  "hits": 9,
  "url": "...", "mall": "...", "category": "...",
  "last_price": 16.9, "last_origin": 84.5
}
```

去重三级：`article_id` → 标题指纹 → 模糊相似度（阈值 0.55）+ 规格兼容 + 价格噪声清洗。
