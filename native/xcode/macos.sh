#!/bin/sh
# Preferred build. Run this on a Mac. Apple Silicon is the default slice.
set -eu
cd "$(dirname "$0")"
arch="${1:-arm64}"
xcodebuild \
  -project si.xcodeproj \
  -scheme si \
  -configuration Release \
  -destination "platform=macOS,arch=${arch}" \
  -derivedDataPath build \
  ARCHS="${arch}" \
  ONLY_ACTIVE_ARCH=YES \
  build
echo "built build/Build/Products/Release/si"
