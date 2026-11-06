#!/bin/sh
# Create the Xcode build, compile the macOS CLI, and run it.
# Preferred machine: a Mac. Apple Silicon is the default slice.
#
#   sh native/xcode/create-build-run.sh
#   sh native/xcode/create-build-run.sh --help
#   sh native/xcode/create-build-run.sh mcp add pcb --url http://127.0.0.1:8766/mcp
#   sh native/xcode/create-build-run.sh x86_64 --help
set -eu
cd "$(dirname "$0")"

if ! command -v xcodebuild >/dev/null 2>&1; then
  echo "create-build-run.sh needs Xcode. Run it on a Mac." >&2
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

echo "creating the ${arch} build"
xcodebuild \
  -project si.xcodeproj \
  -scheme si \
  -configuration Release \
  -destination "platform=macOS,arch=${arch}" \
  -derivedDataPath build \
  ARCHS="${arch}" \
  ONLY_ACTIVE_ARCH=YES \
  build

bin="build/Build/Products/Release/si"
if [ ! -x "$bin" ]; then
  echo "Xcode did not produce ${bin}" >&2
  exit 1
fi

if [ "$#" -eq 0 ]; then
  set -- --help
fi
echo "running ${bin}"
exec "$bin" "$@"
