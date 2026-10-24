# 工作纪律

本文件固定本项目（smzdm-daily）的日常协作纪律。规则来自实测的仓库行为，不是建议，是约束。
新增规则请追加并注明日期，不要删改历史条目。

---

## 一、谁写哪些文件（最高优先级）

GitHub Actions 每天北京 7/12/17/22 点各跑一次，**每次跑完都会自动 `git add -A data docs` 并提交推送**。

| 目录 | 归属 | 人能不能手改 |
|---|---|---|
| `data/` | **机器人**（`smzdm-bot`）独占 | ❌ 不要改 |
| `docs/` | **机器人**独占（`docs/index.html` 由 `template.html` 生成） | ❌ 不要改 |
| `*.py`、`template.html`、`*.md`、`config.example.ini`、`watchlist.txt` | 人 | ✅ 只有这些是你的 |
| `build/` | 本地产物，已 gitignore | 随意，不入库 |

**改样式 → 改 `template.html`。** 手改 `docs/index.html` 会在下次运行时被整份覆盖，白改。

**改数据 → 不要改 `data/`。** catalog 靠 `low` 字段记历史最低价，手改会污染或丢失历史。
若确实需要修数据，先开 issue 说明原因，用一次性脚本 + 单独提交，并在提交信息里写明 `data-fix:` 前缀。

---

## 二、每次开工的标准动作

```bash
git pull --rebase           # 必须先拉，机器人可能刚推过
python -m py_compile daily.py faxian.py probe.py
python -c "import daily; print(len(daily.TEMPLATE.read_text(encoding='utf-8')))"
```

- 第一条：语法
- 第二条：模板路径与完整性，预期 `7759`（模板改动后这个数字会变，属正常）

前端改动（`template.html` 内的 `<script>`）额外检查：

```bash
node --check <提取出的 script 内容>
```

> 没有 py_compile 兜底的地方，必须单独查，不能靠"看起来没报错"。

---

## 三、提交窗口要短

机器人一天推 4 次，数据文件每次几十 KB 增长。你持有工作副本的时间越久，`push` 时撞上"远端已更新"的概率越高。

- **改完尽快推**，不要攒一整天
- 推送失败先 `git pull --rebase --autostash origin main`，再重推
- **不要 `--force`**，除非确认远端没有机器人的新提交

---

## 四、绝对不做的事

| 禁止 | 原因 |
|---|---|
| 在项目里跑定时任务 | Actions 已在跑，重复抓取会触发 smzdm 风控 |
| `pip install` 任何东西 | 全项目纯标准库，加依赖会让 Actions 失败 |
| 提交 `config.ini` | 含 SendKey，已 gitignore，密钥走 Secrets |
| 提交 `build/` | 体积大且每次都变 |
| 手改 `docs/index.html` | 生成物，下次运行被覆盖 |
| 裸跑 `python daily.py`（不加 `--no-crawl`） | 对 smzdm 产生真实抓取请求 |

---

## 五、验证的真实边界

全新克隆的目录**没有** `build/cache/latest.json`，所以：

```bash
python daily.py --no-crawl --dry-run     # ❌ 会报「没有缓存数据，无法离线生成」
```

这是**预期行为**，不是故障。离线只能验证到"代码与模板完整"这一层。
完整链路验证需要能访问 `faxian.smzdm.com`，属于线上行为，**需要单独征得同意后再做**。

---

## 六、仓库体积需要盯住

`data/catalog.json` 只增不减：

| 日期 | 条目数 | 体积 |
|---|---|---|
| 2026-10-19（起点） | 105 | — |
| 2026-10-24 | 533 | 288 KB |

每天新增约 90–130 条。JSON 明文全文提交意味着**每次提交都存一份完整快照**，仓库体积呈平方级增长。
按当前速率，一年后约 3.6 万条 / 20 MB 量级，`git clone` 会明显变慢。

**触发条件**：当 `catalog.json` 超过 2 MB 或 clone 超过 30 秒时，启动归档方案评估。
在此之前不用处理，但不要往 catalog 里塞额外字段。

---

## 七、变更记录

| 日期 | 变更 |
|---|---|
| 2026-10-24 | 建立本文件。依据：`daily.yml` 第 122–141 行自动提交逻辑、10-24 当日 4 次 `smzdm-bot` 提交、catalog 体积实测序列 |
