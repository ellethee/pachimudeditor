#!/usr/bin/env bash
# Costruisce wheel e sdist del core (con la SPA inclusa) e di ogni adapter del monorepo. Non pubblica nulla.
# Uso: scripts/build_package.sh [cartella-di-output]   (default: dist/, ignorata da git)
#      scripts/build_package.sh --only core|pachimud|basedmud|dikumod|mapping [cartella]   (un solo pacchetto)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

build_frontend() {
    # Frontend -> src/pachimudeditor/static (git-ignored, incluso nel wheel/sdist da hatch `artifacts`).
    (cd "$ROOT" && uv run pachimudeditor build-frontend)
}

build_core() {
    local out="$1"
    build_frontend
    (cd "$ROOT" && uv build --package pachimudeditor --out-dir "$out")
}

build_adapter() {
    local name="$1" out="$2"
    (cd "$ROOT" && uv build --package "pachimudeditor-adapter-$name" --out-dir "$out")
}

adapter_names() {
    local d
    for d in "$ROOT"/adapters/*/; do basename "$d"; done
}

main() {
    local only=""
    if [[ "${1:-}" == "--only" ]]; then
        only="${2:?manca il nome del pacchetto}"
        shift 2
    fi
    local out="${1:-$ROOT/dist}"
    mkdir -p "$out"
    if [[ -z "$only" || "$only" == "core" ]]; then
        build_core "$out"
    fi
    local name
    for name in $(adapter_names); do
        if [[ -z "$only" || "$only" == "$name" ]]; then
            build_adapter "$name" "$out"
        fi
    done
    ls -l "$out"
}

main "$@"
