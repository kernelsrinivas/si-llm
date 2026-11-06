#!/bin/sh
# Build the native macOS CLI once and install it as the `si` command.
# After this finishes, call `si` directly. Do not pass CLI sentences to this script.
#
#   sh native/xcode/create-build-run.sh
#   sh native/xcode/create-build-run.sh x86_64
#   si --help
#   si mcp add pcb --url http://127.0.0.1:8766/mcp
set -eu
cd "$(dirname "$0")"

if ! command -v xcodebuild >/dev/null 2>&1; then
  echo "This installer needs Xcode. Run it on a Mac, then use the si command." >&2
  exit 1
fi
if [ ! -d si.xcodeproj ] || [ ! -f si/main.cpp ]; then
  echo "The Xcode project is missing next to this script." >&2
  exit 1
fi

arch="arm64"
if [ "${1:-}" = "arm64" ] || [ "${1:-}" = "x86_64" ]; then
  arch="$1"
  shift
fi
if [ "$#" -ne 0 ]; then
  echo "This script only installs the native CLI. Run commands with si, not with this script." >&2
  echo "Example: si --help" >&2
  exit 1
fi

echo "building the ${arch} si binary"
xcodebuild \
  -project si.xcodeproj \
  -scheme si \
  -configuration Release \
  -destination "platform=macOS,arch=${arch}" \
  -derivedDataPath build \
  ARCHS="${arch}" \
  ONLY_ACTIVE_ARCH=YES \
  build

built="build/Build/Products/Release/si"
if [ ! -x "$built" ]; then
  echo "Xcode did not produce ${built}" >&2
  exit 1
fi

if [ -w /usr/local/bin ] || [ -w /usr/local ]; then
  dest="/usr/local/bin/si"
  cp "$built" "$dest"
  chmod 755 "$dest"
elif mkdir -p "$HOME/.local/bin" 2>/dev/null && [ -w "$HOME/.local/bin" ]; then
  dest="$HOME/.local/bin/si"
  cp "$built" "$dest"
  chmod 755 "$dest"
  echo "Add this to your shell profile if si is not found:"
  echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
else
  dest="$(pwd)/dist/si"
  mkdir -p "$(dirname "$dest")"
  cp "$built" "$dest"
  chmod 755 "$dest"
fi

echo "installed ${dest}"
echo "use it directly:"
echo "  si --help"
