import type { PachiMessages } from '@ilpachi/pachi-i18n'
import type it from './it'

/** English messages of the feature: same keys as `it.ts`. */
const en: PachiMessages<typeof it> = {
  zonefiles: {
    title: 'Raw zone files',
    description: 'Edit the zone files (zone, rooms, mobs, objects, resets) as YAML text',
    empty: 'No files.',
    pick: 'Pick a file from the list.',
    unsavedTitle: 'Unsaved changes',
    unsavedMessage: 'There are unsaved changes: discard them?',
    saved: 'File saved.',
    modified: 'Modified',
    allZones: 'All zones',
    allKinds: 'All kinds',
    filterZone: 'Zone',
    filterKind: 'Kind',
    columns: { zone: 'Zone', file: 'File', kind: 'Kind', size: 'Size' },
    kinds: { zone: 'Zone', rooms: 'Rooms', mobs: 'Mobs', objects: 'Objects', resets: 'Resets' },
    issues: 'Schema violations (first {n})',
    issueLine: 'line {line}',
    changedTitle: 'The file changed on disk',
    changedMessage: 'The file was modified elsewhere after you opened it: your changes were not written.',
    reloadDisk: 'Reload from disk',
    link: 'Raw files',
  },
}

export default en
