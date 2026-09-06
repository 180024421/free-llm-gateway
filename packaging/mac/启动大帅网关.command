#!/bin/bash
# 大帅网关 Mac 便携启动（务必整夹保留：app / runtime / wheels）
# 兼容：bash / 被 zsh 误执行 / Rosetta / 解压丢执行位
# 启动后会脱离 Terminal：终端窗口可关掉，网关继续在菜单栏运行

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
# 若 data 几乎是空的但旁边有旧版备份，提示用户（不自动覆盖，避免误伤）
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

# 默认后台启动并脱离 Terminal：关掉终端窗口不影响网关
# 调试可：DASHUAI_FOREGROUND=1 /bin/bash 启动大帅网关.command
if [ "${DASHUAI_FOREGROUND-}" != "1" ]; then
  echo "[大帅网关] 正在后台启动独立窗口（可关掉本终端）…"
  nohup "$VENV/bin/python" -c "from packaging.run_desktop import main; main()" \
    >>"$ROOT/data/desktop.log" 2>&1 &
  disown >/dev/null 2>&1 || true
  # 稍等窗口起来；失败时用户可看 data/desktop.log
  sleep 1
  # 关闭本次 .command 打开的 Terminal 窗口（不影响用户其它终端）
  /usr/bin/osascript >/dev/null 2>&1 <<'APPLESCRIPT' || true
tell application "Terminal"
  try
    if (count of windows) > 0 then
      close front window
    end if
  end try
end tell
APPLESCRIPT
  exit 0
fi

exec "$VENV/bin/python" -c "from packaging.run_desktop import main; main()"
