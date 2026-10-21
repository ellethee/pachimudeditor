#!/usr/bin/env bash
# Sviluppo contro i sorgenti locali di pachifast e pachifastquasar (senza pubblicare/installare da PyPI/npm).
# Uso: scripts/dev-local.sh on|off|status
#   on  : pyproject.toml (uv source editabile) e frontend/pnpm-workspace.yaml (override link:) + sync/install
#   off : toglie i due blocchi, ripristina uv.lock e pnpm-lock.yaml da git e risincronizza
# I due file modificati NON vanno committati finche' e' "on" (i blocchi sono tra i marker LOCAL-DEV).
# Dopo ogni modifica ai sorgenti di pachifastquasar: pnpm -C "$PFQ/packages/<pacchetto>" build (si consuma dist/).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PF="${PACHIFAST_DIR:-/dati/luca/packages/python/pachifast}"
PFQ="${PACHIFASTQUASAR_DIR:-/dati/luca/packages/vue/pachifastquasar}"
PACKAGES=(pachifastquasar fastquasar-profile fastquasar-settings pachi-i18n pachi-kit)
BEGIN="# >>> LOCAL-DEV (non committare)"
END="# <<< LOCAL-DEV"

is_on() {
    grep -q "LOCAL-DEV" "$ROOT/pyproject.toml"
}

strip_block() {
    sed -i "/^$BEGIN/,/^$END/d" "$1"
}

python_block() {
    printf '%s\n[tool.uv.sources.pachifast]\npath = "%s"\neditable = true\n%s\n' "$BEGIN" "$PF" "$END"
}

frontend_block() {
    local p
    printf '%s\noverrides:\n' "$BEGIN"
    for p in "${PACKAGES[@]}"; do printf "  '@ilpachi/%s': link:%s/packages/%s\n" "$p" "$PFQ" "$p"; done
    printf '%s\n' "$END"
}

turn_on() {
    is_on && { echo "gia' attivo"; return; }
    python_block >>"$ROOT/pyproject.toml"
    frontend_block >>"$ROOT/frontend/pnpm-workspace.yaml"
    (cd "$ROOT" && uv sync --all-packages)
    (cd "$ROOT/frontend" && pnpm install --no-frozen-lockfile)
}

turn_off() {
    strip_block "$ROOT/pyproject.toml"
    strip_block "$ROOT/frontend/pnpm-workspace.yaml"
    (cd "$ROOT" && git checkout -- uv.lock frontend/pnpm-lock.yaml)
    (cd "$ROOT" && uv sync --all-packages)
    (cd "$ROOT/frontend" && pnpm install --frozen-lockfile)
}

main() {
    case "${1:-status}" in
        on) turn_on ;;
        off) turn_off ;;
        status) if is_on; then echo "locale (pachifast=$PF, pachifastquasar=$PFQ)"; else echo "pubblicato (PyPI/npm)"; fi ;;
        *) echo "uso: $0 on|off|status" >&2; exit 2 ;;
    esac
}

main "$@"
