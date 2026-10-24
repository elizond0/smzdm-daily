# 在 WorkBuddy 项目中启动本工具

这份文件写给「刚克隆完仓库、准备在云端项目里跑起来」的场景。

## 一、先确认三件事

| 项 | 说明 |
|---|---|
| Python | 需要 3.10+，**无需 pip install**（全标准库） |
| 网络 | 需要能访问 `faxian.smzdm.com` 抓取 |
| 定时 | 由 GitHub Actions 负责，**项目里不需要跑定时** |

## 二、生成配置

仓库只有模板，真正的配置不入库：

```bash
cp config.example.ini config.ini
```

按需改这几项（其余保持默认）：

```ini
[filter]
min_discount_pct = 35    ; 折扣榜阈值，35 = 3.5 折以内

[crawl]
top_n = 50               ; 好价榜展示条数
feed_pages = 5           ; 抓取页数，调小可降低风控风险

[push]
enabled = false          ; 微信推送开关
```

## 三、验证能跑

全新检出的目录**没有缓存文件**，`--no-crawl` 会因为缺 `build/cache/latest.json` 直接报
「没有缓存数据，无法离线生成」。所以离线只能验证到「代码与模板完整」这一层：

```bash
python -m py_compile daily.py faxian.py probe.py
python -c "import daily; print('模板', len(daily.TEMPLATE.read_text(encoding='utf-8')), '字符')"
```

预期：

```
（py_compile 无输出即通过）
模板 7759 字符
```

`py_compile` 无输出 + 模块能导入，说明依赖、语法、模板路径都对。

要验证完整链路（抓取 → 筛选 → 出报表），需要能访问 `faxian.smzdm.com`：

```bash
python daily.py --no-notify
```

预期输出：

```
数据源 N 条 → 好价榜 20 条，折扣榜 X 条
报表已生成 .../build/reports/YYYY-MM-DD.html
```

若报 `读不到 template.html`，说明工作副本不完整，重新 `git clone` 一次。

## 四、要推 GitHub 时才需要的 Token

**Actions 推送数据不需要你配任何 Token**：workflow 用仓库内置的 `GITHUB_TOKEN`（`permissions: contents: write`）自动提交。

只有**人**推代码时才需要凭据，两种方式：

1. 有 git 凭据的环境：直接 `git pull --rebase && git push`
2. 网页端：仓库页按 `.` 进 github.dev，改完 commit（无需凭据）

若用 GitHub Contents API（本机 `git push` 走代理失败时用这个），Token 自行放在环境变量或 `.deploy.token`（已 gitignore，**不要提交**）：

```
GET  /repos/elizond0/smzdm-daily/contents/{path}   → 取 sha
PUT  /repos/elizond0/smzdm-daily/contents/{path}   → base64 内容 + sha
```

## 五、目录职责

| 目录 | 作用 | 是否入库 | 谁写 |
|---|---|---|---|
| `docs/` | Pages 发布目录，生成的页面 + 静态文件 | ✅ | **机器人**（`smzdm-bot`） |
| `data/` | 跨运行持久化：catalog / pool / run_history / state | ✅ | **机器人**（`smzdm-bot`） |
| `build/` | 本地运行产物、日志、缓存、虚拟环境 | ❌ 已忽略 | 人 |
| `config.ini` | 本机配置（含 SendKey） | ❌ 已忽略 | 人 |
| `.deploy.token` | 可选，Contents API 用的 Token | ❌ 已忽略 | 人 |

`data/` 和 `docs/` 每次 Actions 跑完都会被自动提交，**不要手改**。完整纪律见 [`WORKING_RULES.md`](WORKING_RULES.md)。

## 六、不要做的事

- **不要在项目里跑定时任务**：GitHub Actions 已经在跑（每天 7/12/17/22 点），重复跑会触发 smzdm 风控
- **不要提交 `build/` 和 `config.ini`**：前者体积大且随时变，后者含密钥
- **不要手改 `docs/index.html`**：它由 `daily.py` + `template.html` 生成，下次运行会覆盖。改样式请改 `template.html`
- **不要手改 `data/`**：catalog 靠 `low` 字段记历史最低价，手改会污染或丢失历史

## 七、改代码后的验证顺序

```bash
python -m py_compile daily.py faxian.py probe.py     # 语法
python daily.py --no-crawl --dry-run --force          # 用缓存数据演练
python daily.py --no-crawl --no-notify                # 静默跑，更新数据库
```

前端改动（`template.html` / `docs/*.html`）额外检查：

```bash
node --check <提取出的 script 内容>    # 没有 py_compile 兜底，必须单独查
```
