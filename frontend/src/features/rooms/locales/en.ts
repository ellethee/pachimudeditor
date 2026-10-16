import type { PachiMessages } from '@ilpachi/pachi-i18n'
import type it from './it'

/** English messages of the feature: same keys as `it.ts`. */
const en: PachiMessages<typeof it> = {
  rooms: {
    title: 'Rooms',
    description: 'Rooms, exits and extra descriptions',
    zone: 'Zone',
    loading: 'Loading rooms...',
    errorTitle: 'Loading error',
    errorDescription: 'The data could not be loaded.',
    retry: 'Retry',
    noZoneTitle: 'No zone',
    noZoneDescription: 'Create a zone first to manage rooms.',
    create: 'New room',
    reload: 'Reload',
    openMap: 'Map',
    fields: {
      vnum: 'Vnum',
      name: 'Name',
      sectorType: 'Terrain',
      description: 'Description',
      healRate: 'HP recovery %',
      manaRate: 'Mana recovery %',
      flags: 'Flags (type and press enter)',
      flagsHint: 'E.g. DARK, PEACEFUL, INDOORS',
      sectorRomHint: 'The own sector of the world (specific fields) takes precedence',
    },
    validation: {
      integer: 'must be an integer',
    },
    dialog: {
      create: 'New room',
      edit: 'Edit room',
      general: 'General',
    },
    exits: {
      title: 'Exits',
      direction: 'Direction',
      present: 'Present',
      target: 'Destination',
      door: 'Door',
      open: 'Open',
      locked: 'Locked',
      keywords: "Door keywords",
      keywordsHint: "E.g. door gate",
      description: "Description (looking that way)",
      descriptionHint: "Text shown when looking in this direction",
      keyVnum: 'Key vnum',
    },
    extras: {
      title: 'Extra descriptions',
      keywords: 'Keywords',
      text: 'Text',
      add: 'Add extra description',
      remove: 'Remove',
    },
    clone: {
      action: 'Clone',
      title: 'Clone room',
      vnum: 'New vnum',
      name: 'New name (optional)',
      hint: 'Exits are not copied; extra descriptions are.',
      defaultName: '{name} (copy)',
    },
    delete: {
      message: '"{name}" (vnum {vnum}) will be deleted.',
      usageWarning:
        'Warning: it is referenced by {count} reset commands ({zones}): deletion will be refused until you update them.',
    },
    notify: {
      saved: 'Room saved.',
      cloned: 'Room cloned.',
    },
    map: {
      title: 'Room map',
      description: 'Graph of the rooms of a zone',
      fit: 'Fit',
      reload: 'Reload',
      openList: 'List',
      hint: 'Click a room to edit it.',
      empty: 'No rooms in this zone.',
      dangling: '⚠ {count} without destination',
      dir: {
        0: 'N',
        1: 'E',
        2: 'S',
        3: 'W',
        4: 'Up',
        5: 'Down',
      },
    },
  },
}

export default en
