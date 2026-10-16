"""Testi dei file generati da `pachimudeditor init` nella cartella di lavoro."""

PROJECT_MODULES_SOURCE = '''"""Generato da `pachimudeditor init`: i moduli pachifast di base (usato da `pachifast users/migrations`).

Solo i moduli senza dipendenza da `pachimud`: utenti e migration dell'auth non dipendono dai mondi configurati.
"""

from pachimudeditor.modules import build_modules

MODULES = build_modules()
'''

CONFIG_TEMPLATE = """\
# Configurazione di pachimudeditor (formato pachifast: sezioni server/app/auth/events).
# Priorita': variabili d'ambiente (PACHIFAST_*, anche da .env) > questo file > default.
# I segreti (secret_key, URL con password) stanno in .env, non qui.

server:
  host: 127.0.0.1 # solo locale: per l'accesso da altre macchine usare un reverse proxy con TLS
  port: 8123
  envelope_enabled: true # ogni 2xx JSON e' {success, message, data}

app:
  project_name: Pachimud Webeditor
  default_locale: it # messaggi di errore in italiano (ogni errore ha comunque un `code` stabile)
  use_accept_language: true

auth:
  password_min_length: 12
  registration_enabled: false # niente auto-registrazione: gli utenti si creano con `pachimudeditor users create`
  login_max_attempts: 5
  login_lockout_minutes: 15
events:
  broadcast_enabled: true

# MONDI. Nessun mondo e' implicito: l'editor mostra solo quelli configurati qui (alternativa: WEBEDITOR_WORLDS /
# PACHIMUDEDITOR_WORLDS, JSON). Senza mondi il server parte lo stesso e la UI spiega come configurarli.
# Proprieta' comuni: id, kind, name, path, mapping, params, read_only.
{worlds_block}
# --- esempi per gli adapter installati (decommentare e adattare) ---
# I `kind` sono pacchetti a parte: `pachimudeditor adapters list` mostra quelli installati e come aggiungere gli altri.
{examples_block}

# Giornale delle conversioni tra mondi (disattivato se assente; env WEBEDITOR_CONVERT_JOURNAL_DIR):
# webeditor_convert_journal_dir: ./conversioni
"""


def render_config() -> str:
    """Il `pachimudeditor.yaml` iniziale: nessun mondo attivo, esempi commentati per ogni kind."""
    from pachimudeditor.common.adapters.plugins import examples_block

    return CONFIG_TEMPLATE.replace("{worlds_block}", "webeditor_worlds: []").replace("{examples_block}", examples_block())
