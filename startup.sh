#!/bin/sh
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

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required to run the model server." >&2
  exit 1
fi
if ! python3 -c "import py.si.server" >>/tmp/si-llm.log 2>&1; then
  echo "The model server cannot start outside a prepared Python environment." >&2
  tail -20 /tmp/si-llm.log >&2 || true
  exit 1
fi

if ! curl -sf -o /dev/null --max-time 2 http://127.0.0.1:8766/health; then
  python3 -m py.si.tool_server pcb >>/tmp/si-pcb.log 2>&1 &
fi
if ! curl -sf -o /dev/null --max-time 2 http://127.0.0.1:8767/health; then
  python3 -m py.si.tool_server cad >>/tmp/si-cad.log 2>&1 &
fi
if ! curl -sf -o /dev/null --max-time 2 http://127.0.0.1:8765/health; then
  python3 -m py.si.server >>/tmp/si-llm.log 2>&1 &
fi

if [ "$sandbox" -eq 1 ]; then
  if curl -sf -o /dev/null --max-time 2 http://127.0.0.1:8080/; then
    exit 0
  fi
  npm run dev >>/tmp/app-startup.log 2>&1 &
  exit 0
fi

i=0
while [ "$i" -lt 40 ]; do
  if curl -sf -o /dev/null --max-time 2 http://127.0.0.1:8765/health; then
    exit 0
  fi
  i=$((i + 1))
  sleep 0.5
done
echo "The model server did not stay up. See /tmp/si-llm.log" >&2
tail -20 /tmp/si-llm.log >&2 || true
exit 1
