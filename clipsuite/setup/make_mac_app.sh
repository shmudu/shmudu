#!/usr/bin/env bash
# Builds ClipSuite.app in ~/Applications: double-click (or keep it in the Dock) to open the editor
# in its own window. Run once after install_mac.sh:   cd clipsuite && bash setup/make_mac_app.sh
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
APP="$HOME/Applications/ClipSuite.app"

if [[ "$(uname)" != "Darwin" ]]; then echo "This builds a macOS app; run it on your Mac."; exit 1; fi
if [[ ! -x "$ROOT/.venv/bin/python" ]]; then echo "Run setup/install_mac.sh first."; exit 1; fi

"$ROOT/.venv/bin/pip" install -q pywebview

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

# icon
ICONSET="$(mktemp -d)/ClipSuite.iconset"
mkdir -p "$ICONSET"
"$ROOT/.venv/bin/python" "$ROOT/setup/make_icon.py" "$ICONSET/icon_512x512@2x.png"
for s in 16 32 128 256 512; do
  sips -z $s $s "$ICONSET/icon_512x512@2x.png" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
  d=$((s * 2)); sips -z $d $d "$ICONSET/icon_512x512@2x.png" --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/ClipSuite.icns"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>ClipSuite</string>
  <key>CFBundleDisplayName</key><string>ClipSuite</string>
  <key>CFBundleIdentifier</key><string>local.clipsuite.app</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>ClipSuite</string>
  <key>CFBundleIconFile</key><string>ClipSuite</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST

# launcher: apps opened from Finder don't get your Terminal PATH, so add Homebrew's
cat > "$APP/Contents/MacOS/ClipSuite" <<LAUNCH
#!/bin/bash
export PATH="/opt/homebrew/bin:/usr/local/bin:\$PATH"
[ -f "\$HOME/.config/clipsuite/env" ] && source "\$HOME/.config/clipsuite/env"   # optional API keys
cd "$ROOT"
mkdir -p "\$HOME/Library/Logs"
exec "$ROOT/.venv/bin/python" -m clipsuite.desktop >> "\$HOME/Library/Logs/ClipSuite.log" 2>&1
LAUNCH
chmod +x "$APP/Contents/MacOS/ClipSuite"

echo "Built $APP"
echo "Open it from Finder > Applications (your user Applications folder), or Spotlight: ClipSuite."
echo "Drag it to the Dock to keep it there. Logs: ~/Library/Logs/ClipSuite.log"
open -R "$APP" || true
