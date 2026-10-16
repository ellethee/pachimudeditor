/** Avvia lo stack isolato e resta in attesa (utile per provare a mano l'editor sui dati di test). */
import { startStack, credentials } from './support/stack.ts'

const stack = await startStack()
console.log(`Stack su ${stack.baseUrl} (pid ${stack.pid}) utente ${credentials.username}. Ctrl+C per fermare.`)
const bye = (): void => {
  void stack.stop().then(() => process.exit(0))
}
process.on('SIGINT', bye)
process.on('SIGTERM', bye)
setInterval(() => undefined, 1 << 30)
