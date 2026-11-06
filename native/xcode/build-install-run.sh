#!/bin/sh
# Build the native client, install it on PATH as `si`, then start the model server.
# On a Mac this uses Xcode. Elsewhere it compiles the same C++ file.
# After it finishes, talk to the model with si. Do not pass sentences to this script.
#
#   sh native/xcode/build-install-run.sh
#   si "what is a buck converter"
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
cd "$root"

arch="arm64"
if [ "${1:-}" = "arm64" ] || [ "${1:-}" = "x86_64" ]; then
  arch="$1"
  shift
fi
if [ "$#" -ne 0 ]; then
  echo "This script builds si, installs it into bin, and starts the server." >&2
  echo "Then run: si \"what is a buck converter\"" >&2
  exit 1
fi

if command -v xcodebuild >/dev/null 2>&1; then
  echo "building the macOS ${arch} client"
  (
    cd native/xcode
    xcodebuild \
      -project si.xcodeproj \
      -scheme si \
      -configuration Release \
      -destination "platform=macOS,arch=${arch}" \
      -derivedDataPath build \
      ARCHS="${arch}" \
      ONLY_ACTIVE_ARCH=YES \
      build
  )
  built="native/xcode/build/Build/Products/Release/si"
else
  echo "Xcode is not here. Building the same C++ client."
  mkdir -p native/xcode/build
  g++ -std=c++17 -O2 -o native/xcode/build/si native/xcode/si/main.cpp
  built="native/xcode/build/si"
fi
if [ ! -x "$built" ]; then
  echo "The client build did not produce ${built}" >&2
  exit 1
fi

if [ -w /usr/local/bin ] || [ -w /usr/local ]; then
  dest="/usr/local/bin/si"
elif mkdir -p "${HOME}/.local/bin" && [ -w "${HOME}/.local/bin" ]; then
  dest="${HOME}/.local/bin/si"
else
  mkdir -p native/xcode/dist
  dest="${root}/native/xcode/dist/si"
fi
cp "$built" "$dest"
chmod 755 "$dest"
echo "installed ${dest}"

export SI_MODEL="${root}/model"
if ! curl -sf -o /dev/null --max-time 2 http://127.0.0.1:8766/health; then
  python3 -m py.si.tool_server pcb >>/tmp/si-pcb.log 2>&1 &
fi
if ! curl -sf -o /dev/null --max-time 2 http://127.0.0.1:8767/health; then
  python3 -m py.si.tool_server cad >>/tmp/si-cad.log 2>&1 &
fi
if ! curl -sf -o /dev/null --max-time 2 http://127.0.0.1:8765/health; then
  python3 -m py.si.server >>/tmp/si-llm.log 2>&1 &
fi

ready=0
i=0
while [ "$i" -lt 40 ]; do
  if curl -sf -o /dev/null --max-time 2 http://127.0.0.1:8765/health; then
    ready=1
    break
  fi
  i=$((i + 1))
  sleep 0.5
done
if [ "$ready" -ne 1 ]; then
  echo "The model server did not start. See /tmp/si-llm.log" >&2
  exit 1
fi

echo "model server is running at http://127.0.0.1:8765"
echo "use the installed client directly:"
echo "  si \"what is a buck converter\""
