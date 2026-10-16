import type { PachiMessages } from '@ilpachi/pachi-i18n'
import type it from './it'

/** English messages of the feature: same keys as `it.ts`. */
const en: PachiMessages<typeof it> = {
  instances: {
    title: 'Instances',
    description: 'Live mobs and objects in the world: fix, move, spawn and despawn',
    save: 'Save',
    cancel: 'Cancel',
    reload: 'Reload',
    loadError: 'The data could not be loaded.',
    tabs: { mobs: 'Mobs', objects: 'Objects' },
    mob: {
      new: 'New live mob',
      createTitle: 'Spawn mob',
      editTitle: 'Live mob #{id}',
      items: 'Carried objects ({count})',
    },
    object: {
      new: 'New live object',
      createTitle: 'Spawn object',
      editTitle: 'Live object #{id}',
      contents: 'Contents ({count})',
    },
    filters: {
      zone: 'Zone',
      prototypeVnum: 'Prototype vnum',
      room: 'Room',
    },
    columns: {
      id: 'Id',
      prototype: 'Prototype',
      room: 'Room',
      zone: 'Zone',
      hitPoints: 'HP',
      gold: 'Gold',
      items: 'Objects',
      type: 'Type',
      location: 'Location',
      charges: 'Charges',
      contents: 'Contents',
    },
    locationKinds: {
      room: 'Room',
      container: 'Container',
      mob: 'Mob',
      character: 'Character',
    },
    fields: {
      prototype: 'Prototype',
      room: 'Room',
      hitPoints: 'Hit points',
      hitPointsHint: 'Empty: rolled from the prototype dice',
      hitPointsCurrent: 'Current HP',
      hitPointsMax: 'Maximum HP',
      gold: 'Gold',
      goldHint: 'Shop till; empty: none',
      location: 'Location',
      locationKind: 'Where it is',
      target: {
        room: 'Room',
        container: 'Container id',
        mob: 'Live mob id',
        character: 'Character id',
      },
      targetHint: {
        room: '',
        container: 'Id of the container object instance',
        mob: 'Id of the mob instance (see the Mobs tab)',
        character: 'Character id',
      },
      equippedSlot: 'Worn slot',
      slotHint: 'Empty: in the inventory, not worn',
      noSlots: 'This object cannot be worn',
      charges: 'Charges',
      liquidAmount: 'Liquid amount',
      liquidType: 'Liquid type',
      liquidPoisoned: 'Poisoned',
      prototypeDefaultHint: 'Empty: prototype value',
    },
    picker: { noResults: 'No results' },
    validation: {
      required: 'Required field',
      minOne: 'Must be at least 1',
      nonNegative: 'Cannot be negative',
    },
    delete: {
      title: 'Delete instance',
      message: 'Delete instance #{id} ({name})?',
      mob: {
        destroy: 'Also destroy the objects it carries',
        drop: 'Drop the objects in the room',
      },
      object: {
        destroy: 'Also destroy the contents',
        drop: 'Leave the contents where the container was',
      },
    },
  },
}

export default en
