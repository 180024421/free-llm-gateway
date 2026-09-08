#!/bin/bash
set -euo pipefail

APP="${1:-大帅网关.app}"
ZIP="${2:-}"
IDENTITY="${DASHUAI_MAC_SIGN_IDENTITY:-}"
PROFILE="${DASHUAI_MAC_NOTARY_PROFILE:-}"

if [ -z "$IDENTITY" ]; then
  echo "未配置 DASHUAI_MAC_SIGN_IDENTITY，跳过签名。"
  exit 0
fi
if [ ! -d "$APP" ]; then
  echo "找不到 App：$APP" >&2
  exit 1
fi

/usr/bin/codesign --force --deep --options runtime --timestamp --sign "$IDENTITY" "$APP"
/usr/bin/codesign --verify --deep --strict --verbose=2 "$APP"

if [ -n "$ZIP" ] && [ -n "$PROFILE" ]; then
  /usr/bin/xcrun notarytool submit "$ZIP" --keychain-profile "$PROFILE" --wait
  /usr/bin/xcrun stapler staple "$APP"
elif [ -n "$ZIP" ]; then
  echo "未配置 DASHUAI_MAC_NOTARY_PROFILE，仅完成签名，未公证。"
fi
