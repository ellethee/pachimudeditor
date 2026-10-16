import type { PachiMessages } from '@ilpachi/pachi-i18n'
import type it from './it'

/** English messages of the feature: same keys as `it.ts`. */
const en: PachiMessages<typeof it> = {
  mobs: {
    title: 'Mobs',
    description: 'Prototype mobs: stats, flags and descriptions',
    zone: 'Zone',
    new: 'New mob',
    reload: 'Reload',
    createTitle: 'New mob',
    editTitle: 'Edit mob',
    errorTitle: 'Loading error',
    errorDescription: 'The data could not be loaded.',
    retry: 'Retry',
    noZonesTitle: 'No zones',
    noZonesDescription: 'Create a zone first to be able to define mobs.',
    vnumSuggest: 'Suggest the next free vnum',
    columns: {
      vnum: 'Vnum',
      shortDescription: 'Description',
      level: 'Level',
      race: 'Race',
      class: 'Class',
    },
    sections: {
      identity: 'Identity',
      roles: "Roles and services",
      combat: 'Combat and attributes',
    },
    fields: {
      vnum: 'Vnum',
      keywords: 'Keywords',
      shortDescription: 'Short description',
      longDescription: 'Long description (on the ground)',
      detailedDescription: 'Detailed description (look)',
      level: 'Level',
      thac0: 'THAC0',
      armorClass: 'Armor class',
      hpDiceCount: 'HP dice (count)',
      hpDieSize: 'HP dice (sides)',
      hpBonus: 'HP dice (bonus)',
      damageDiceCount: 'Damage dice (count)',
      damageDieSize: 'Damage dice (sides)',
      damageBonus: 'Damage dice (bonus)',
      gold: 'Gold',
      experience: 'Experience',
      alignment: 'Alignment (-1000..1000)',
      sex: 'Sex',
      raceId: 'Race',
      classId: 'Class',
      flags: 'Flags (type and press enter)',
      flagsHint: 'E.g. SENTINEL, AGGRESSIVE, SCAVENGER',
      isBanker: "Banker",
      shopId: "Shop ID (optional)",
      shopIdHint: "Identifier of the shop run by the mob",
      debuffSkillId: "Debuff skill (optional)",
      debuffSkillIdHint: "ID of the skill used as a debuff in combat",
      questIds: "Quests (type and press enter)",
      questIdsHint: "IDs of the quests the mob offers",
      teachesClassIds: "Taught classes",
      teachesSkillIds: "Taught skills (type and press enter)",
      teachesSkillIdsHint: "IDs of the skills the mob teaches",
    },
    validation: {
      alignmentRange: 'Alignment must be between -1000 and 1000',
    },
    delete: {
      title: 'Delete the mob?',
      message: '"{name}" (vnum {vnum}) will be deleted.',
      usageWarning:
        'Warning: it is referenced by {count} reset commands ({zones}): deletion will be refused until you update them.',
    },
  },
}

export default en
