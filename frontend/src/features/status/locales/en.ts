import type { PachiMessages } from '@ilpachi/pachi-i18n'
import type it from './it'

/** English messages of the feature: same keys as `it.ts`. */
const en: PachiMessages<typeof it> = {
  status: {
    title: 'Status',
    description: 'Backend status and configured worlds',
    reload: 'Reload',
    ok: 'Backend reachable — version {version}',
    down: 'Backend unreachable',
    databaseDown: 'Database unreachable',
    worlds: 'Configured worlds',
    default: 'default',
    readOnly: 'read-only',
  },
}

export default en
