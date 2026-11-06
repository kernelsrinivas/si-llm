#!/bin/sh
# Installs the native macOS `si` command. It does not run the CLI.
cd "$(dirname "$0")"
exec sh ./create-build-run.sh "$@"
