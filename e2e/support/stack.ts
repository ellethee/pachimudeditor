/**
 * Avvio/arresto dello stack isolato per i test e2e: backend pachifast (che serve anche il frontend
 * buildato in src/pachimudeditor/static) su una porta dedicata, contro database temporanei.
 *
 * Non tocca mai il `pachimud.db` reale: l'ambiente (config, DB di gioco, DB auth, utente) lo prepara
 * `tests/support/stack.py` in una cartella temporanea dentro e2e/.tmp.
 * Il processo viene fermato SOLO tramite il suo PID esatto.
 */
import { spawn, execFileSync, type ChildProcess } from 'node:child_process'
import { cpSync, existsSync, mkdirSync, mkdtempSync, rmSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))

/** Radice del repository dell'editor. */
export const ROOT = resolve(HERE, '..', '..')
/** Cartella da cui girano python/uvicorn (contiene `.venv`, `tests/`, `pachimudeditor.example.yaml`). */
export const BACKEND = ROOT
/** Sorgente di basedmud (default: checkout fratello `../basedmud`; override con `E2E_BASEDMUD`) da cui si copia l'area (solo lettura: i test lavorano su una copia temporanea). */
export const BASEDMUD_SRC = process.env.E2E_BASEDMUD ?? resolve(ROOT, '..', 'basedmud')
/** `lib/` del Diku Modificato (solo `E2E_DIKUMOD`, nessun default) da cui si copiano i dati (solo lettura: i test lavorano su copie temporanee). */
export const DIKUMOD_SRC = process.env.E2E_DIKUMOD ?? ''
/** Vero se `E2E_DIKUMOD` e' impostata e punta a una cartella esistente: altrimenti i mondi `dikumod*` non esistono e i loro test si saltano. */
/** Prefisso dei file dati (`E2E_DIKUMOD_PREFIX`, default `dikumoddata`). */
export const DIKUMOD_PREFIX = process.env.E2E_DIKUMOD_PREFIX || 'dikumoddata'
export const HAS_DIKUMOD = DIKUMOD_SRC !== '' && existsSync(DIKUMOD_SRC)
/** Cartella temporanea (ignorata da git) che contiene i DB di test. */
export const TMP_ROOT = join(ROOT, 'e2e', '.tmp')

/** Credenziali dell'utente di test creato da `tests/support/stack.py` (sovrascrivibili via env). */
export const credentials = {
  username: process.env.E2E_USER ?? 'e2e-user',
  password: process.env.E2E_PASSWORD ?? 'Password-di-test-123',
}

/** Stato di uno stack avviato. */
export interface Stack {
  /** URL base (backend + frontend statico). */
  baseUrl: string
  /** PID del processo uvicorn. */
  pid: number
  /** Cartella temporanea dei DB. */
  workdir: string
  /** Ferma lo stack (SIGTERM al PID esatto, poi SIGKILL se non esce) e rimuove la cartella temporanea. */
  stop: () => Promise<void>
}

/**
 * Isola i dati che i test possono modificare oltre al DB di gioco: copia le definizioni di esempio (`tests/fixtures/pachimud_definitions`, razze/classi YAML)
 * nella cartella temporanea e punta la config li', copia l'area di basedmud (+ `src/tables.c` per razze/classi)
 * e configura i mondi del webeditor: `pachimud` (default), `pachimud-ro` (stesso DB, sola lettura), `basedmud` (scrivibile), `basedmud-ro` (stessa copia,
 * sola lettura), e, solo se `E2E_DIKUMOD` e' impostata, `dikumod` (copia di quella `lib/`, sola lettura) e `dikumod-rw` (seconda copia scrivibile).
 * @param workdir cartella temporanea dello stack
 * @param pachimud parametri del mondo pachimud (DB di gioco e definitions temporanei, preparati da `tests/support/stack.py`)
 * @returns variabili d'ambiente aggiuntive per uvicorn
 */
function prepareExtras(workdir: string, pachimud: { databaseUrl: string; definitionsPath: string }): Record<string, string> {

  const based = join(workdir, 'basedmud')
  mkdirSync(join(based, 'src'), { recursive: true })
  cpSync(join(BASEDMUD_SRC, 'area'), join(based, 'area'), { recursive: true })
  cpSync(join(BASEDMUD_SRC, 'src', 'tables.c'), join(based, 'src', 'tables.c'))
  const worlds: Record<string, unknown>[] = [
    { id: 'pachimud', kind: 'pachimud', name: 'Pachimud', params: { database_url: pachimud.databaseUrl, definitions_path: pachimud.definitionsPath } },
    { id: 'basedmud', kind: 'basedmud', name: 'BasedMud', path: based },
    { id: 'basedmud-ro', kind: 'basedmud', name: 'BasedMud (sola lettura)', path: based, read_only: true },
    { id: 'pachimud-ro', kind: 'pachimud', name: 'Pachimud (sola lettura)', read_only: true, params: { database_url: pachimud.databaseUrl, definitions_path: pachimud.definitionsPath } },
  ]
  if (HAS_DIKUMOD) {
    const dikumodRo = join(workdir, 'dikumod', 'lib')
    const dikumodRw = join(workdir, 'dikumod-rw', 'lib')
    cpSync(DIKUMOD_SRC, dikumodRo, { recursive: true })
    cpSync(DIKUMOD_SRC, dikumodRw, { recursive: true })
    worlds.push(
      { id: 'dikumod', kind: 'dikumod', name: 'Diku Modificato (sola lettura)', path: dikumodRo, read_only: true, params: { data_prefix: DIKUMOD_PREFIX } },
      { id: 'dikumod-rw', kind: 'dikumod', name: 'Diku Modificato (scrivibile)', path: dikumodRw, read_only: false, params: { data_prefix: DIKUMOD_PREFIX } },
    )
  }
  return { WEBEDITOR_WORLDS: JSON.stringify(worlds), WEBEDITOR_DEFAULT_WORLD: 'pachimud' }
}

/**
 * Prepara i DB temporanei e avvia uvicorn sulla porta data.
 * @param port porta del backend (default 8124, o E2E_PORT)
 * @param options `noWorlds`: nessun mondo configurato (WEBEDITOR_WORLDS vuoto), per la pagina `/no-worlds`
 * @returns lo stack avviato e pronto a rispondere
 */
export async function startStack(port = Number(process.env.E2E_PORT ?? 8124), options: { noWorlds?: boolean } = {}): Promise<Stack> {
  const python = join(BACKEND, '.venv', 'bin', 'python')
  if (!existsSync(python)) throw new Error('Manca .venv: esegui `uv sync --all-packages`')
  if (!existsSync(join(ROOT, 'src', 'pachimudeditor', 'static', 'index.html'))) {
    throw new Error('Manca src/pachimudeditor/static: esegui `uv run pachimudeditor build-frontend`')
  }
  const busy = await fetch(`http://127.0.0.1:${port}/api/health/`).then(
    () => true,
    () => false,
  )
  if (busy) throw new Error(`La porta ${port} e' gia' occupata: fermare l'altro processo o usare E2E_PORT`)
  mkdirSync(TMP_ROOT, { recursive: true })
  const workdir = mkdtempSync(join(TMP_ROOT, 'run-'))

  const prepared = execFileSync(python, ['-m', 'tests.support.stack', workdir], {
    cwd: BACKEND,
    encoding: 'utf8',
  })
  const env: Record<string, string> = {}
  for (const line of prepared.split('\n')) {
    const match = /^(PACHI[A-Z_]+)=(.*)$/.exec(line.trim())
    if (match) env[match[1]!] = match[2]!
  }
  if (!env.PACHIMUD_DATABASE_URL?.includes(workdir) || !env.PACHIMUD_DEFINITIONS_PATH?.startsWith(workdir)) {
    throw new Error('Ambiente di test non isolato')
  }
  execFileSync(python, [join(ROOT, 'e2e', 'support', 'seed_players.py'), workdir], { cwd: BACKEND, encoding: 'utf8' })
  Object.assign(
    env,
    options.noWorlds ? { WEBEDITOR_WORLDS: '[]' } : prepareExtras(workdir, { databaseUrl: env.PACHIMUD_DATABASE_URL, definitionsPath: env.PACHIMUD_DEFINITIONS_PATH }),
  )

  const child: ChildProcess = spawn(
    python,
    ['-m', 'uvicorn', 'pachimudeditor.app:create_editor_app', '--factory', '--host', '127.0.0.1', '--port', String(port), '--log-level', 'warning'],
    { cwd: BACKEND, env: { ...process.env, ...env }, stdio: ['ignore', 'inherit', 'inherit'] },
  )
  const pid = child.pid
  if (pid === undefined) throw new Error('Avvio uvicorn fallito')
  let exited = false
  child.on('exit', () => {
    exited = true
  })

  const baseUrl = `http://127.0.0.1:${port}`
  const deadline = Date.now() + 60_000
  for (;;) {
    if (exited) throw new Error('uvicorn e\' terminato durante l\'avvio (porta occupata?)')
    try {
      const response = await fetch(`${baseUrl}/api/health/`)
      if (response.ok) break
    } catch {
      /* non ancora pronto */
    }
    if (Date.now() > deadline) {
      child.kill('SIGKILL')
      throw new Error('Timeout in attesa del backend')
    }
    await new Promise((r) => setTimeout(r, 300))
  }

  const stop = async (): Promise<void> => {
    if (!exited) {
      child.kill('SIGTERM')
      await new Promise<void>((done) => {
        const timer = setTimeout(() => {
          child.kill('SIGKILL')
          done()
        }, 5000)
        child.once('exit', () => {
          clearTimeout(timer)
          done()
        })
      })
    }
    rmSync(workdir, { recursive: true, force: true })
  }
  return { baseUrl, pid, workdir, stop }
}
