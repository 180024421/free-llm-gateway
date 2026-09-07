#!/bin/bash
# 大帅网关 Mac 便携启动（务必整夹保留：app / runtime / wheels）
# 兼容：bash / 被 zsh 误执行 / Rosetta / 解压丢执行位
# 启动后脱离 Terminal：关掉终端不影响网关（勿再「终止」会话内进程）

# 若不是 bash，强制用系统 bash 重跑（避免 zsh+nounset 报 ARCH?）
if [ -z "${BASH_VERSION-}" ]; then
  exec /bin/bash "$0" "$@"
  exit 1
fi

set -e
# 故意不用 set -u / pipefail：旧 Bash / 杂项环境容易误伤

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT" || exit 1

alert() {
  MSG=$1
  /usr/bin/osascript <<EOF >/dev/null 2>&1 || true
display alert "大帅网关" message "$MSG" as critical
EOF
}

info() {
  MSG=$1
  /usr/bin/osascript <<EOF >/dev/null 2>&1 || true
display alert "大帅网关" message "$MSG" as informational
EOF
}

# 优先看包内实际目录，再看 uname（Rosetta 下 uname 可能是 x86_64）
ARCH=""
if [ -d "$ROOT/runtime/arm64" ]; then
  ARCH="arm64"
elif [ -d "$ROOT/runtime/x86_64" ]; then
  ARCH="x86_64"
else
  UNAME_M="$(/usr/bin/uname -m 2>/dev/null || echo unknown)"
  case "$UNAME_M" in
    arm64|aarch64) ARCH="arm64" ;;
    x86_64|i386|i686) ARCH="x86_64" ;;
    *) ARCH="arm64" ;;
  esac
fi

PY_HOME="$ROOT/runtime/$ARCH"
PY="$PY_HOME/bin/python3"
VENV="$ROOT/runtime/venv-$ARCH"
WHEELS="$ROOT/wheels/$ARCH"
APP="$ROOT/app"
DESKTOP_PY="$APP/packaging/run_desktop.py"
LOG="$ROOT/data/desktop.log"
PIDFILE="$ROOT/data/desktop.pid"

port_alive() {
  # 默认 8010；若 data/config.json 有 port 则读它（失败则仍用 8010）
  P=8010
  if [ -f "$ROOT/data/config.json" ]; then
    P="$("$VENV/bin/python" -c "import json;print(json.load(open('$ROOT/data/config.json',encoding='utf-8-sig')).get('port') or 8010)" 2>/dev/null || echo 8010)"
  fi
  /usr/bin/curl -fsS --max-time 1 "http://127.0.0.1:${P}/api/overview" >/dev/null 2>&1
}

# 解除隔离属性（从浏览器下载后常见；失败忽略）
/usr/bin/xattr -dr com.apple.quarantine "$ROOT" >/dev/null 2>&1 || true

# 解压后常见：文件在但丢了 +x
if [ -f "$PY" ] && [ ! -x "$PY" ]; then
  chmod +x "$PY" 2>/dev/null || true
  chmod +x "$PY_HOME/bin/python" 2>/dev/null || true
fi
if [ -d "$PY_HOME/bin" ]; then
  chmod +x "$PY_HOME/bin/"* 2>/dev/null || true
fi

if [ ! -f "$PY" ]; then
  alert "缺少 Python 运行时（runtime/$ARCH）。请重新解压完整安装包，不要只拷贝启动脚本。"
  echo "[大帅网关] 缺少: $PY" >&2
  exit 1
fi
if [ ! -x "$PY" ]; then
  alert "Python 没有执行权限。请在终端执行：chmod +x \"$PY\""
  exit 1
fi
if [ ! -d "$APP" ]; then
  alert "缺少 app 目录，请重新解压完整安装包。"
  exit 1
fi
if [ ! -f "$DESKTOP_PY" ]; then
  alert "缺少 app/packaging/run_desktop.py，请重新解压完整安装包。"
  exit 1
fi

# 首次运行：优先离线 wheels；失败则联网补齐
if [ ! -x "$VENV/bin/python" ]; then
  echo "[大帅网关] 首次启动，正在准备运行环境（只需一次）…"
  "$PY" -m venv "$VENV"
  "$VENV/bin/python" -m pip install --upgrade pip setuptools wheel >/dev/null
  rc=1
  if [ -d "$WHEELS" ]; then
    set +e
    "$VENV/bin/python" -m pip install --no-index --find-links "$WHEELS" -r "$APP/requirements-mac.txt"
    rc=$?
    set -e
  fi
  if [ "$rc" -ne 0 ]; then
    echo "[大帅网关] 离线安装不完整，改为联网补齐依赖…"
    set +e
    "$VENV/bin/python" -m pip install -r "$APP/requirements-mac.txt"
    rc=$?
    set -e
  fi
  if [ "$rc" -ne 0 ]; then
    alert "依赖安装失败。请检查网络后重试，或把文件夹放到无空格路径再开。"
    exit 1
  fi
  echo "[大帅网关] 环境准备完成。"
fi

export DASHUAI_DATA_DIR="$ROOT/data"
export DASHUAI_COMMERCIAL=1
export DASHUAI_BUNDLE_DIR="$ROOT"
# 必须把 app 放在最前；且不要用「import packaging.run_desktop」
# （会与 pip 自带的 packaging 包撞名导致秒退、窗口永不出现）
if [ -n "${PYTHONPATH-}" ]; then
  export PYTHONPATH="$APP:$PYTHONPATH"
else
  export PYTHONPATH="$APP"
fi

mkdir -p "$ROOT/data"
# 只在缺失时从模板复制，绝不覆盖用户已有 config/providers/routers
for name in config providers routers; do
  if [ ! -f "$ROOT/data/${name}.json" ] && [ -f "$APP/data/${name}.example.json" ]; then
    cp "$APP/data/${name}.example.json" "$ROOT/data/${name}.json"
  fi
done
if [ ! -f "$ROOT/data/providers.json" ] && [ ! -f "$ROOT/data/session.json" ]; then
  for cand in "$ROOT/../大帅网关-mac-arm64/data" "$ROOT/../大帅网关-mac-arm64.bak/data" "$ROOT/../大帅网关-mac-arm64-旧/data"; do
    if [ -f "$cand/providers.json" ] || [ -f "$cand/session.json" ]; then
      echo "[大帅网关] 检测到可能的旧配置：$cand"
      echo "[大帅网关] 如需保留 API Key/登录态，请把该目录复制为：$ROOT/data"
      break
    fi
  done
fi

cd "$APP"

# 调试：DASHUAI_FOREGROUND=1 /bin/bash 启动大帅网关.command
if [ "${DASHUAI_FOREGROUND-}" = "1" ]; then
  echo "[大帅网关] 前台模式启动（本窗口需一直开着）…"
  exec "$VENV/bin/python" "$DESKTOP_PY"
fi

# 已在跑：接口通 → 提示菜单栏；进程在但服务挂 → 清掉僵死进程后重开
if [ -f "$PIDFILE" ]; then
  OLD_PID="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [ -n "${OLD_PID-}" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    if port_alive; then
      info "大帅网关似乎已在运行（PID $OLD_PID）。\n\n请看屏幕右上角菜单栏「大帅」→「显示窗口」。\n若没有窗口，浏览器打开 http://127.0.0.1:8010/ui/\n真正退出请点菜单「退出网关」。"
      exit 0
    fi
    echo "[大帅网关] 发现僵死进程 PID $OLD_PID（端口无响应），正在清理后重启…"
    kill "$OLD_PID" 2>/dev/null || true
    sleep 0.6
    kill -9 "$OLD_PID" 2>/dev/null || true
    rm -f "$PIDFILE"
  fi
fi

echo "[大帅网关] 正在后台启动独立窗口…"
echo "[大帅网关] 日志：$LOG"

# 必须从当前 Terminal 会话 nohup 启动（继承 Aqua/GUI）。
# 禁止经 AppleScript 间接拉 GUI：进程常能起来（有 PID），但 pywebview 窗口/菜单栏不出现。
# disown 后关掉终端窗口一般不会带走子进程；若系统弹出「是否终止进程」请点「取消」。
mkdir -p "$ROOT/data"
: >>"$LOG"
LOG_OFF="$(/usr/bin/wc -c <"$LOG" | /usr/bin/tr -d ' ')"
echo "[大帅网关] ---- launch $(/bin/date '+%Y-%m-%d %H:%M:%S') ----" >>"$LOG"

nohup "$VENV/bin/python" "$DESKTOP_PY" >>"$LOG" 2>&1 &
echo $! >"$PIDFILE"
disown >/dev/null 2>&1 || true

new_log() {
  # 只看本次启动之后追加的日志，避免历史「server ready」误判成功
  /usr/bin/tail -c +"$((LOG_OFF + 1))" "$LOG" 2>/dev/null || true
}

# 等待进程 + 服务就绪（不只看 PID）
ok=0
ready=0
i=0
while [ "$i" -lt 45 ]; do
  i=$((i + 1))
  NEW_PID="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [ -n "${NEW_PID-}" ] && kill -0 "$NEW_PID" 2>/dev/null; then
    ok=1
    if port_alive; then
      ready=1
      sleep 0.8
      break
    fi
    # 日志级就绪（port 可能稍慢于 menubar）
    if new_log | /usr/bin/grep -E -q "server ready on|mac menubar ready"; then
      ready=1
      sleep 0.8
      break
    fi
  fi
  if new_log | /usr/bin/grep -E -q "Integrity fail|webview .*failed|uvicorn failed|wait_ready failed|Traceback"; then
    break
  fi
  sleep 0.4
done

if [ "$ok" -ne 1 ]; then
  TAIL=""
  if [ -f "$LOG" ]; then
    TAIL="$(new_log | /usr/bin/tail -n 18 | /usr/bin/tr -d '\r' | /usr/bin/sed 's/\"//g')"
  fi
  alert "独立窗口没有成功起来。\n\n请把下面日志发给客服，或用前台模式排查：\n/bin/bash -lc 'DASHUAI_FOREGROUND=1 \"${ROOT}/启动大帅网关.command\"'\n\n日志尾部：\n${TAIL:-(空)}"
  exit 1
fi

UI_HINT="http://127.0.0.1:8010/ui/"
if [ -f "$ROOT/data/config.json" ]; then
  UI_HINT="$("$VENV/bin/python" -c "import json;p=json.load(open('$ROOT/data/config.json',encoding='utf-8-sig')).get('port') or 8010;print(f'http://127.0.0.1:{p}/ui/')" 2>/dev/null || echo "$UI_HINT")"
fi

if [ "$ready" -ne 1 ]; then
  echo "[大帅网关] 进程已在跑，但窗口/服务尚未确认就绪。请看右上角菜单栏「大帅」，或打开："
  echo "  $UI_HINT"
  echo "[大帅网关] 仍无界面时请查看：$LOG"
  echo "[大帅网关] 或前台模式：DASHUAI_FOREGROUND=1 /bin/bash \"$ROOT/启动大帅网关.command\""
else
  echo "[大帅网关] 已启动（PID $(cat "$PIDFILE" 2>/dev/null)）。"
  echo "[大帅网关] 主窗口应已弹出；若只见菜单栏，点右上角「大帅」→「显示窗口」。"
  echo "[大帅网关] 也可浏览器打开：$UI_HINT"
fi
echo "[大帅网关] 本终端可直接关掉（若弹出「终止进程」请点取消，不要点终止）。"
exit 0
