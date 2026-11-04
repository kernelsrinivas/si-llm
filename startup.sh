#!/bin/sh
set -eu
cd /workspace
node scripts/preview.mjs stop || true
if ! curl -sf -o /dev/null --max-time 2 http://127.0.0.1:8766/health; then
  python3 -m py.si.tool_server pcb >>/tmp/si-pcb.log 2>&1 &
fi
if ! curl -sf -o /dev/null --max-time 2 http://127.0.0.1:8767/health; then
  python3 -m py.si.tool_server cad >>/tmp/si-cad.log 2>&1 &
fi
if ! curl -sf -o /dev/null --max-time 2 http://127.0.0.1:8765/health; then
  python3 -m py.si.server >>/tmp/si-llm.log 2>&1 &
fi
if curl -sf -o /dev/null --max-time 2 http://127.0.0.1:8080/; then
  exit 0
fi
npm run dev >>/tmp/app-startup.log 2>&1 &
