#!/bin/bash
# 大帅网关 Mac 便携启动：自带 Python + 独立窗口（pywebview / WKWebView）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

ARCH_RAW="$(uname -m)"
case "$ARCH_RAW" in
  arm64|aarch64) ARCH="arm64" ;;
  x86_64|i386) ARCH="x86_64" ;;
  *)
    osascript -e 'display alert "大帅网关" message "暂不支持的芯片架构，请使用 Apple Silicon 或 Intel 版安装包。" as critical' || true
    exit 1
    ;;
esac

PY_HOME="$ROOT/runtime/$ARCH"
PY="$PY_HOME/bin/python3"
VENV="$ROOT/runtime/venv-$ARCH"
WHEELS="$ROOT/wheels/$ARCH"
APP="$ROOT/app"

if [[ ! -x "$PY" ]]; then
  osascript -e "display alert \"大帅网关\" message \"缺少 runtime/$ARCH，请重新解压完整安装包（不要只拷贝启动脚本）。\" as critical" || true
  exit 1
fi

# 首次运行：优先离线 wheels；失败则联网补齐（用户仍不用装系统 Python）
if [[ ! -x "$VENV/bin/python" ]]; then
  echo "[大帅网关] 首次启动，正在准备运行环境（只需一次）…"
  "$PY" -m venv "$VENV"
  "$VENV/bin/python" -m pip install --upgrade pip setuptools wheel >/dev/null
  set +e
  if [[ -d "$WHEELS" ]]; then
    "$VENV/bin/python" -m pip install --no-index --find-links "$WHEELS" -r "$APP/requirements-mac.txt"
    rc=$?
  else
    rc=1
  fi
  if [[ "$rc" -ne 0 ]]; then
    echo "[大帅网关] 离线安装不完整，改为联网补齐依赖…"
    "$VENV/bin/python" -m pip install -r "$APP/requirements-mac.txt"
    rc=$?
  fi
  set -e
  if [[ "$rc" -ne 0 ]]; then
    osascript -e 'display alert "大帅网关" message "依赖安装失败。请检查网络后重试，或把整个文件夹放到无中文空格路径再开。" as critical' || true
    exit 1
  fi
  echo "[大帅网关] 环境准备完成。"
fi

export DASHUAI_DATA_DIR="$ROOT/data"
export DASHUAI_COMMERCIAL=1
export DASHUAI_BUNDLE_DIR="$ROOT"
export PYTHONPATH="$APP${PYTHONPATH:+:$PYTHONPATH}"

mkdir -p "$ROOT/data"
for name in config providers routers; do
  if [[ ! -f "$ROOT/data/${name}.json" && -f "$APP/data/${name}.example.json" ]]; then
    cp "$APP/data/${name}.example.json" "$ROOT/data/${name}.json"
  fi
done

cd "$APP"
exec "$VENV/bin/python" -c "from packaging.run_desktop import main; main()"
