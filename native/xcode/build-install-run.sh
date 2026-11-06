#!/bin/sh
# Same start command. Kept so older instructions still work.
cd "$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)"
exec sh ./startup.sh
