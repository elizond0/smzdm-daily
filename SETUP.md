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

若报 `读不到 template.html`，说明包不完整，重新解压一遍。

## 四、要推 GitHub 时才需要的 Token

`.deploy.token` **不在仓库里**（已 gitignore）。在项目里推代码有两种方式：

1. 项目环境变量：设 `GITHUB_TOKEN`，脚本读环境变量
2. 或直接 `git push`，用项目的 git 凭据

若用 GitHub Contents API（本机 `git push` 走代理常失败时用这个）：

```
GET  /repos/elizond0/smzdm-daily/contents/{path}   → 取 sha
PUT  /repos/elizond0/smzdm-daily/contents/{path}   → base64 内容 + sha
```

## 五、目录职责

| 目录 | 作用 | 是否入库 |
|---|---|---|
| `docs/` | Pages 发布目录，生成的页面 + 静态文件 | ✅ |
| `data/` | 跨运行持久化：catalog / pool / run_history / state | ✅ |
| `build/` | 本地运行产物、日志、缓存、虚拟环境 | ❌ 已忽略 |
| `config.ini` | 本机配置（含 SendKey） | ❌ 已忽略 |
| `.deploy.token` | 推送用 Token | ❌ 已忽略 |

## 六、不要做的事

- **不要在项目里跑定时任务**：GitHub Actions 已经在跑（每天 7/12/17/22 点），重复跑会触发 smzdm 风控
- **不要提交 `build/` 和 `config.ini`**：前者体积大且随时变，后者含密钥
- **不要手工改 `docs/index.html`**：它由 `daily.py` + `template.html` 生成，下次运行会覆盖。改样式请改 `template.html`

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
