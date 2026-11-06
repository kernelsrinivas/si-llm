#!/bin/sh
# Preferred macOS build. Creates the Xcode build and runs the CLI.
cd "$(dirname "$0")"
exec sh ./create-build-run.sh "$@"
