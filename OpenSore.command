#!/usr/bin/env bash
# OpenSore.command — double-click this in Finder to launch OpenSore.
# macOS opens .command files in a new Terminal window automatically.
cd "$(dirname "$0")"
exec bash start.sh
