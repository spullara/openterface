#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
swift build -c release
app='build/KVM Viewer.app'
mkdir -p "$app/Contents/MacOS"
cp "$(swift build -c release --show-bin-path)/KVMViewer" "$app/Contents/MacOS/KVMViewer"
cat > "$app/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleIdentifier</key><string>dev.kvmuse.viewer</string>
<key>CFBundleName</key><string>KVM Viewer</string>
<key>CFBundleExecutable</key><string>KVMViewer</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleVersion</key><string>1</string>
<key>LSMinimumSystemVersion</key><string>14.0</string>
<key>NSCameraUsageDescription</key><string>Show the screen connected to your Openterface KVM.</string>
<key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST
codesign --force --sign - "$app"
