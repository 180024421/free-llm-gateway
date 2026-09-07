#!/bin/bash
# 大帅网关 Mac 便携启动（务必整夹保留：app / runtime / wheels / 大帅网关.app）
# 兼容：bash / 被 zsh 误执行 / Rosetta / 解压丢执行位
#
# 用法：
#   双击「启动大帅网关.command」→ 准备环境后 open「大帅网关.app」（正规 GUI 会话）
#   双击「大帅网关.app」→ 同样走本脚本 --run
#   DASHUAI_FOREGROUND=1 → 前台挂在终端里跑（排障）

if [ -z "${BASH_VERSION-}" ]; then
  exec /bin/bash "$0" "$@"
  exit 1
fi

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT" || exit 1
MODE="${1-}"

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
MAC_APP="$ROOT/大帅网关.app"

port_alive() {
  P=8010
  if [ -f "$ROOT/data/config.json" ] && [ -x "$VENV/bin/python" ]; then
    P="$("$VENV/bin/python" -c "import json;print(json.load(open(r'''$ROOT/data/config.json''',encoding='utf-8-sig')).get('port') or 8010)" 2>/dev/null || echo 8010)"
  fi
  /usr/bin/curl -fsS --max-time 1 "http://127.0.0.1:${P}/api/overview" >/dev/null 2>&1
}

/usr/bin/xattr -dr com.apple.quarantine "$ROOT" >/dev/null 2>&1 || true

if [ -f "$PY" ] && [ ! -x "$PY" ]; then
  chmod +x "$PY" 2>/dev/null || true
  chmod +x "$PY_HOME/bin/python" 2>/dev/null || true
fi
if [ -d "$PY_HOME/bin" ]; then
  chmod +x "$PY_HOME/bin/"* 2>/dev/null || true
fi
if [ -f "$MAC_APP/Contents/MacOS/大帅网关" ]; then
  chmod +x "$MAC_APP/Contents/MacOS/大帅网关" 2>/dev/null || true
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
if [ -n "${PYTHONPATH-}" ]; then
  export PYTHONPATH="$APP:$PYTHONPATH"
else
  export PYTHONPATH="$APP"
fi

mkdir -p "$ROOT/data"
for name in config providers routers; do
  if [ ! -f "$ROOT/data/${name}.json" ] && [ -f "$APP/data/${name}.example.json" ]; then
    cp "$APP/data/${name}.example.json" "$ROOT/data/${name}.json"
  fi
done

cd "$APP"

# --run：由 .app 或前台模式真正执行桌面壳（必须前台，才能出窗口）
if [ "$MODE" = "--run" ] || [ "${DASHUAI_FROM_APP-}" = "1" ] || [ "${DASHUAI_FOREGROUND-}" = "1" ]; then
  echo "[大帅网关] 正在打开独立窗口…"
  echo "[大帅网关] 日志：$LOG"
  : >>"$LOG"
  echo "[大帅网关] ---- run $(/bin/date '+%Y-%m-%d %H:%M:%S') ----" >>"$LOG"
  exec "$VENV/bin/python" "$DESKTOP_PY"
fi

# 已在跑
if [ -f "$PIDFILE" ]; then
  OLD_PID="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [ -n "${OLD_PID-}" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    if port_alive; then
      info "大帅网关似乎已在运行（PID $OLD_PID）。\n\n请看 Dock / 菜单栏「大帅」→「显示窗口」。\n或浏览器打开 http://127.0.0.1:8010/ui/"
      # 再激活一次 .app
      if [ -d "$MAC_APP" ]; then
        /usr/bin/open "$MAC_APP" >/dev/null 2>&1 || true
      fi
      exit 0
    fi
    echo "[大帅网关] 发现僵死进程 PID $OLD_PID，正在清理…"
    kill "$OLD_PID" 2>/dev/null || true
    sleep 0.5
    kill -9 "$OLD_PID" 2>/dev/null || true
    rm -f "$PIDFILE"
  fi
fi

# 优先用 .app（LaunchServices），解决「终端说已启动但没有界面」
if [ -d "$MAC_APP/Contents/MacOS" ]; then
  echo "[大帅网关] 正在通过「大帅网关.app」启动独立窗口…"
  echo "[大帅网关] 日志：$LOG"
  /usr/bin/open "$MAC_APP"
  ok=0
  i=0
  while [ "$i" -lt 40 ]; do
    i=$((i + 1))
    if port_alive; then
      ok=1
      break
    fi
    sleep 0.4
  done
  if [ "$ok" -eq 1 ]; then
    echo "[大帅网关] 服务已就绪。主窗口应已出现在 Dock / 前台。"
    echo "[大帅网关] 若仍没有窗口：点 Dock 里的「大帅网关」或「Python」，或打开 http://127.0.0.1:8010/ui/"
    echo "[大帅网关] 本终端可关掉。"
    exit 0
  fi
  echo "[大帅网关] .app 启动超时，改在本终端前台启动…"
fi

echo "[大帅网关] 前台启动独立窗口（请保持本终端开着）…"
echo "[大帅网关] 日志：$LOG"
exec "$VENV/bin/python" "$DESKTOP_PY"
