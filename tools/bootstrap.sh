#!/usr/bin/env bash
# ============================================================
# 工作区一键引导：下载代码 → 恢复数据目录 → 自检
#
# 用途：新对话 / 新机器上，用一条命令把可工作的目录建起来。
# 用法：
#   bash tools/bootstrap.sh            # 建到当前目录（需为空目录或已在本仓库里）
#   bash tools/bootstrap.sh /tmp/work  # 建到指定目录
#
# 幂等：已经是仓库目录时，只补做「恢复数据 + 自检」，不会重复下载。
# 退出码：0 全部通过 / 1 有检查项失败（详见输出）
# ============================================================
set -uo pipefail

REPO="elizond0/smzdm-daily"
BRANCH="main"
DEST="${1:-.}"
FAIL=0

say()  { printf '%s\n' "$*"; }
ok()   { printf '  \033[32m✅\033[0m %s\n' "$*"; }
bad()  { printf '  \033[31m❌\033[0m %s\n' "$*"; FAIL=1; }
warn() { printf '  \033[33m⚠️\033[0m %s\n' "$*"; }
step() { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }

mkdir -p "$DEST"
cd "$DEST" || { say "进不去目录 $DEST"; exit 1; }

# ---------------------------------------------------------- 1. 取代码
step "1/4 取得代码"
if [ -f daily.py ] && [ -f template.html ]; then
  ok "当前目录已是仓库（daily.py + template.html 都在），跳过下载"
else
  TMPZIP="$(mktemp -t smzdm.XXXXXX.zip)"
  say "  下载 zip 快照（codeload，比 git clone 稳）..."
  if ! curl -sSL --retry 3 --max-time 180 -o "$TMPZIP" \
       "https://codeload.github.com/${REPO}/zip/refs/heads/${BRANCH}"; then
    bad "下载失败，检查网络。可改用 git clone（见部署必读 4.2）"
    rm -f "$TMPZIP"; exit 1
  fi
  SIZE=$(wc -c < "$TMPZIP" | tr -d ' ')
  ok "已下载 ${SIZE} 字节"

  if ! unzip -q "$TMPZIP" -d .; then
    bad "解压失败（zip 可能已损坏），重跑本脚本"; rm -f "$TMPZIP"; exit 1
  fi
  rm -f "$TMPZIP"

  # codeload 的顶层目录名是 <repo>-<branch>，仓库改名会变，用通配符兜住
  INNER=$(find . -maxdepth 1 -type d -name '*-'"${BRANCH}" | head -1)
  if [ -z "$INNER" ]; then
    INNER=$(find . -maxdepth 1 -type d ! -name '.' | head -1)
  fi
  if [ -n "$INNER" ] && [ -d "$INNER" ]; then
    # 连点文件一起搬（.gitignore / .gitattributes 是关键，漏了后来自检会报）
    mv "$INNER"/* . 2>/dev/null
    mv "$INNER"/.[!.]* . 2>/dev/null
    rmdir "$INNER" 2>/dev/null
  fi
  ok "已解压并展平到 $(pwd)"
fi

if [ ! -f daily.py ]; then
  bad "没找到 daily.py，目录不对：$(pwd)"; exit 1
fi

# ---------------------------------------------------------- 2. 恢复数据
step "2/4 恢复数据目录（build/ 不进仓库，必须从 data/ 搬回来）"
python3 - <<'PY' > /tmp/_cnt_before 2>/dev/null
try:
    import sys; sys.path.insert(0, '.')
    import daily
    print(len(daily.Catalog().records))
except Exception:
    print(-1)
PY
BEFORE=$(cat /tmp/_cnt_before 2>/dev/null | tr -d ' \n')

mkdir -p build/cache build/state
[ -f data/catalog.json ]     && cp data/catalog.json     build/cache/catalog.json
[ -f data/pool.json ]        && cp data/pool.json        build/cache/pool.json
[ -f data/run_history.json ] && cp data/run_history.json build/cache/run_history.json
for f in last_push.txt cooldown_until.txt blocked_streak.txt; do
  [ -f "data/state/$f" ] && cp "data/state/$f" build/state/
done
[ -f config.ini ] || { [ -f config.example.ini ] && cp config.example.ini config.ini; }

AFTER=$(python3 - <<'PY' 2>/dev/null | tr -d ' \n'
try:
    import sys; sys.path.insert(0, '.')
    import daily
    print(len(daily.Catalog().records))
except Exception:
    print(-1)
PY
)

if [ "${AFTER:-0}" -gt 0 ] 2>/dev/null; then
  ok "商品目录 ${AFTER} 条（恢复前 ${BEFORE}）"
elif [ -f data/catalog.json ]; then
  bad "商品目录仍为 0 —— data/catalog.json 存在但读不出，检查文件是否损坏"
else
  warn "仓库里没有 data/catalog.json（首次部署的正常情况），目录从空开始"
fi

# ---------------------------------------------------------- 3. 自检
step "3/4 自检"
if python3 -m py_compile daily.py faxian.py probe.py 2>/dev/null; then
  ok "语法：daily.py / faxian.py / probe.py"
else
  bad "语法检查没通过，跑 python3 -m py_compile daily.py 看报错"
fi

TPL=$(python3 -c "import sys;sys.path.insert(0,'.');import daily;print(len(daily.TEMPLATE.read_text(encoding='utf-8')))" 2>/dev/null)
if [ -n "$TPL" ]; then ok "模板可读：${TPL} 字符"; else bad "template.html 读不出来"; fi

MISS=""
for f in .gitattributes .gitignore docs/.nojekyll; do
  [ -f "$f" ] || MISS="$MISS $f"
done
if [ -z "$MISS" ]; then ok "三个点文件齐全"; else bad "缺文件:$MISS"; fi

# 统计口径：只数「仓库里应该有的文件」。以下都排除，否则数字永远对不上：
#   build/      运行时产物（本脚本刚生成）
#   config.ini  本地配置（.gitignore 里，脚本刚复制）
#   __pycache__ 编译缓存
# 预期 37 = 仓库 36 个 + tools/bootstrap.sh 自身。若用内联命令、没下载脚本，则是 36。
N=$(find . -type f -not -path './.git/*' -not -path './build/*' \
        -not -path './config.ini' -not -path '*/__pycache__/*' | wc -l | tr -d ' ')
if [ "$N" = "37" ] || [ "$N" = "36" ]; then
  ok "文件总数 ${N}（预期 37 = 仓库 36 + bootstrap.sh；无脚本时 36 也正常）"
elif [ "$N" = "38" ]; then
  warn "文件总数 38，多了 __pycache__，无妨（rm -rf __pycache__）"
else
  warn "文件总数 ${N}（预期 37）：偏少说明拉取不完整或有文件被过滤，重跑本脚本；先看 4.4 口径说明"
fi

python3 - <<'PY'
import json
bad = 0
for p in ("data/catalog.json", "data/pool.json", "data/run_history.json",
          "docs/db.json", "docs/history.json"):
    try:
        json.load(open(p, encoding="utf-8"))
    except FileNotFoundError:
        print(f"  \033[33m⚠️\033[0m 缺失 {p}"); bad = 1
    except json.JSONDecodeError as e:
        print(f"  \033[31m❌\033[0m 坏了 {p} —— {e}"); bad = 1
if not bad:
    print("  \033[32m✅\033[0m JSON 数据文件均可解析（5 个）")
PY

# ---------------------------------------------------------- 4. 结论
step "4/4 结论"
if [ "$FAIL" = "0" ]; then
  ok "工作区已就绪：$(pwd)"
  say ""
  say "  下一步（可选，想验证能真跑一遍）："
  say "    python3 daily.py --probe                # 只探测是否被风控，约 1 秒"
  say "    python3 daily.py --no-notify            # 完整跑一遍，不发通知，约 90 秒"
  say ""
  say "  注意：--no-crawl 在全新工作区用不了（缺 build/cache/latest.json），第一次必须联网。"
  exit 0
else
  bad "有检查项没通过，先按上面的提示处理，别急着改代码"
  say ""
  say "  详细排错见「部署必读 → 八、常见故障对照」"
  exit 1
fi
