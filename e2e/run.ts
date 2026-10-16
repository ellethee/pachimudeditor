/**
 * Runner e2e: avvia lo stack isolato (setup globale), lancia i test con `node --test` passando
 * l'URL via env, poi ferma lo stack per PID esatto (teardown), anche su Ctrl+C o errore.
 *
 * Con `E2E_SKIP_STACK=1` non avvia nulla e usa lo stack gia' in esecuzione su `E2E_BASE_URL`
 * (comodo in sviluppo con `pnpm run stack`).
 */
import { spawn } from 'node:child_process'
import { startStack, type Stack } from './support/stack.ts'

/** Punto d'ingresso: setup, esecuzione, teardown. */
async function main(): Promise<number> {
  const external = process.env.E2E_SKIP_STACK === '1'
  const stack: Stack | undefined = external ? undefined : await startStack()
  const baseUrl = stack?.baseUrl ?? process.env.E2E_BASE_URL ?? 'http://127.0.0.1:8124'
  if (stack) console.log(`Stack e2e su ${stack.baseUrl} (pid ${stack.pid})`)
  let child: ReturnType<typeof spawn> | undefined
  const shutdown = (): void => {
    child?.kill('SIGTERM')
  }
  process.on('SIGINT', shutdown)
  process.on('SIGTERM', shutdown)
  try {
    const args = process.argv.slice(2)
    const files = args.length ? args : ['tests/*.test.ts']
    child = spawn(
      process.execPath,
      ['--import', 'tsx', '--test', '--test-reporter=spec', '--test-concurrency=1', '--test-timeout=180000', ...files],
      { stdio: 'inherit', env: { ...process.env, E2E_BASE_URL: baseUrl } },
    )
    return await new Promise<number>((done) => child!.on('exit', (code) => done(code ?? 1)))
  } finally {
    await stack?.stop()
    if (stack) console.log('Stack e2e fermato')
  }
}

main().then(
  (code) => process.exit(code),
  (error) => {
    console.error(error)
    process.exit(1)
  },
)
