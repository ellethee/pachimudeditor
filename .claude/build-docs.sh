#!/usr/bin/env bash
# PostToolUse hook: ricompila il sito mkdocs (site/, ignorato da git) quando si modifica un sorgente della documentazione.
# Una sola build alla volta (flock): le modifiche ravvicinate di piu' agenti non lanciano build in parallelo.

LOG=/tmp/pachimudeditor-docs-build.log

build() {
    cd "$CLAUDE_PROJECT_DIR" || return 0
    flock -w 300 9 || return 0
    uv run --group docs mkdocs build --strict -q >"$LOG" 2>&1 || { echo "mkdocs build fallita, vedi $LOG" >&2; return 2; }
}

main() {
    local path
    path=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("file_path",""))')
    case "$path" in
        */docs/*|*/mkdocs.yml|*/CHANGELOG.md|*/overrides/*) ;;
        *) return 0 ;;
    esac
    build 9>/tmp/pachimudeditor-docs-build.lock
}

main
