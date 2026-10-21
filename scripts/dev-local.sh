#!/usr/bin/env bash
# Sviluppo contro i sorgenti locali di pachifast e pachifastquasar (senza pubblicare/installare da PyPI/npm).
# Uso: scripts/dev-local.sh on|off|status
#   on  : pyproject.toml (uv source editabile), frontend/pnpm-workspace.yaml (override link:) e frontend/tsconfig.json (paths) + sync/install
#   off : toglie i due blocchi, ripristina uv.lock e pnpm-lock.yaml da git e risincronizza
# I file modificati (e uv.lock/pnpm-lock.yaml) NON vanno committati finche' e' "on" (blocchi tra i marker LOCAL-DEV; ripristina con `off`).
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

typescript_paths() {
    # Un'unica copia di vue/pinia/vue-router/quasar/vue-i18n per i tipi: i pacchetti linkati hanno le loro in node_modules.
    (cd "$ROOT/frontend" && node -e '
const fs = require("fs"), path = require("path");
const base = JSON.parse(fs.readFileSync(".quasar/tsconfig.json", "utf8")).compilerOptions.paths;
const paths = {};
for (const [k, v] of Object.entries(base)) paths[k] = v.map((x) => path.resolve(".quasar", x));
for (const m of ["vue", "pinia", "vue-router", "quasar", "vue-i18n"]) {
  const dir = path.resolve("node_modules", m);
  paths[m] = [dir];
  paths[m + "/*"] = [dir + "/*"];
}
fs.writeFileSync("tsconfig.json", JSON.stringify({ extends: "./.quasar/tsconfig.json", compilerOptions: { paths } }, null, 2) + "\n");
')
}

turn_on() {
    is_on && { echo "gia' attivo"; return; }
    python_block >>"$ROOT/pyproject.toml"
    frontend_block >>"$ROOT/frontend/pnpm-workspace.yaml"
    (cd "$ROOT" && uv sync --all-packages)
    (cd "$ROOT/frontend" && pnpm install --no-frozen-lockfile)
    typescript_paths
}

turn_off() {
    strip_block "$ROOT/pyproject.toml"
    strip_block "$ROOT/frontend/pnpm-workspace.yaml"
    (cd "$ROOT" && git checkout -- uv.lock frontend/pnpm-lock.yaml frontend/tsconfig.json)
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
