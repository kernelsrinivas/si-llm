#!/bin/sh
# One start command.
#   sh startup.sh
#   si "what is a buck converter"
set -eu
if [ -d /workspace ]; then
  cd /workspace
  sandbox=1
else
  cd "$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
  sandbox=0
fi

export SI_MODEL="${PWD}/model"
case ":${PYTHONPATH:-}:" in
  *":${PWD}:"*) ;;
  *) PYTHONPATH="${PWD}${PYTHONPATH:+:$PYTHONPATH}" ;;
esac
export PYTHONPATH

if [ "$sandbox" -eq 1 ]; then
  node scripts/preview.mjs stop || true
fi

install_si() {
  if command -v si >/dev/null 2>&1; then
    return 0
  fi
  mkdir -p native/xcode/build
  if command -v xcodebuild >/dev/null 2>&1; then
    (
      cd native/xcode
      xcodebuild -project si.xcodeproj -scheme si -configuration Release \
        -destination "platform=macOS,arch=arm64" -derivedDataPath build \
        ARCHS=arm64 ONLY_ACTIVE_ARCH=YES build
    )
    built="native/xcode/build/Build/Products/Release/si"
  elif command -v g++ >/dev/null 2>&1; then
    g++ -std=c++17 -O2 -o native/xcode/build/si native/xcode/si/main.cpp
    built="native/xcode/build/si"
  else
    echo "Need Xcode or g++ to build si." >&2
    return 1
  fi
  if [ -w /usr/local/bin ] || [ -w /usr/local ]; then
    dest="/usr/local/bin/si"
  else
    mkdir -p "${HOME}/.local/bin"
    dest="${HOME}/.local/bin/si"
  fi
  cp "$built" "$dest"
  chmod 755 "$dest"
  echo "installed ${dest}"
}

install_si

if ! curl -sf -o /dev/null --max-time 2 http://127.0.0.1:8765/health; then
  if ! command -v python3 >/dev/null 2>&1 || ! python3 -c "import py.si.server" >>/tmp/si-llm.log 2>&1; then
    echo "The model server did not start. Python with PyTorch is required." >&2
    tail -20 /tmp/si-llm.log >&2 || true
    exit 1
  fi
  if ! curl -sf -o /dev/null --max-time 2 http://127.0.0.1:8766/health; then
    python3 -m py.si.tool_server pcb >>/tmp/si-pcb.log 2>&1 &
  fi
  if ! curl -sf -o /dev/null --max-time 2 http://127.0.0.1:8767/health; then
    python3 -m py.si.tool_server cad >>/tmp/si-cad.log 2>&1 &
  fi
  python3 -m py.si.server >>/tmp/si-llm.log 2>&1 &
  i=0
  while [ "$i" -lt 40 ]; do
    if curl -sf -o /dev/null --max-time 2 http://127.0.0.1:8765/health; then
      break
    fi
    i=$((i + 1))
    sleep 0.5
  done
  if ! curl -sf -o /dev/null --max-time 2 http://127.0.0.1:8765/health; then
    echo "The model server did not stay up." >&2
    tail -20 /tmp/si-llm.log >&2 || true
    exit 1
  fi
fi

if [ "$sandbox" -eq 1 ]; then
  if curl -sf -o /dev/null --max-time 2 http://127.0.0.1:8080/; then
    exit 0
  fi
  npm run dev >>/tmp/app-startup.log 2>&1 &
fi
