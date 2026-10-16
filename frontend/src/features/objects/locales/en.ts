import type { PachiMessages } from '@ilpachi/pachi-i18n'
import type it from './it'

/** English messages of the feature: same keys as `it.ts`. */
const en: PachiMessages<typeof it> = {
  objects: {
    title: 'Objects',
    description: 'Prototype objects: type, flags and values',
    zone: 'Zone',
    new: 'New object',
    reload: 'Reload',
    createTitle: 'New object',
    editTitle: 'Edit object',
    errorTitle: 'Loading error',
    errorDescription: 'The data could not be loaded.',
    retry: 'Retry',
    noZonesTitle: 'No zones',
    noZonesDescription: 'Create a zone first to be able to define objects.',
    vnumSuggest: 'Suggest the next free vnum',
    columns: {
      vnum: 'Vnum',
      shortDescription: 'Description',
      objectType: 'Type',
    },
    sections: {
      general: 'General',
      stats: 'Stats and flags',
    },
    fields: {
      vnum: 'Vnum',
      objectType: 'Type',
      keywords: 'Keywords',
      shortDescription: 'Short description',
      longDescription: 'Long description (on the ground)',
      actionDescription: 'Action description (optional)',
      weight: 'Weight',
      cost: 'Cost',
      rent: 'Rent',
      value0: 'Value 0 (depends on type)',
      value1: 'Value 1',
      value2: 'Value 2',
      value3: 'Value 3',
      valueHint:
        'value0..3: meaning depends on the type (e.g. weapon: damage dice/bonus; armor: AC bonus; container: capacity)',
      extraFlags: 'Extra flags (type and press enter)',
      extraFlagsHint: 'E.g. GLOW, HUM, MAGIC',
      wearFlags: 'Wear flags (type and press enter)',
      wearFlagsHint: 'E.g. WIELD, BODY, HOLD',
      affects: "Affects (active while equipped)",
      affectsHint: "Bonuses applied to the wearer.",
      affectsFreeHint: "Target list not provided by the backend: type the target name (BuffTarget).",
    },
    affects: {
      target: "Target",
      bonus: "Bonus",
      add: "Add affect",
      remove: "Remove affect",
      empty: "No affects.",
      duplicate: "Target already present",
    },
    delete: {
      title: 'Delete the object?',
      message: '"{name}" (vnum {vnum}) will be deleted.',
      usageWarning:
        'Warning: it is referenced by {count} reset commands ({zones}): deletion will be refused until you update them.',
    },
  },
}

export default en
