import type { PachiMessages } from '@ilpachi/pachi-i18n'
import type it from './it'

/** English messages of the feature: same keys as `it.ts`. */
const en: PachiMessages<typeof it> = {
  transfer: {
    title: 'Zone transfer',
    description: 'Export and import zones in the game server YAML format',
    export: {
      title: 'Export zone',
      description: 'Download a zip with zone.yaml, rooms.yaml, mobs.yaml, objects.yaml and resets.yaml, ready for definitions/zones/.',
      zone: 'Zone',
      download: 'Download zip',
      done: 'Downloaded {name}.',
    },
    import: {
      title: 'Import zone',
      description: 'Upload a zip (or the single YAML files) of a zone. You see a preview first, then confirm the import.',
      files: 'Files to import',
      filesHint: 'A zip, or zone.yaml (required) with rooms/mobs/objects/resets.yaml',
      preview: 'Preview (no changes)',
      noDeletes: 'The import creates or updates by vnum and never deletes anything; resets and room extra descriptions are replaced entirely.',
      confirm: 'I confirm: apply the import to the database',
      apply: 'Import',
      applied: 'Import done.',
      done: 'Zone "{name}" (vnum {vnum}) imported.',
    },
    actions: { create: 'New', update: 'To update', unchanged: 'Unchanged' },
    preview: {
      kind: 'Content',
      create: 'New',
      update: 'Updated',
      unchanged: 'Unchanged',
      kept: 'In DB, not in file',
      replaced: 'Replaced',
      resetsSummary: '{inFile} in file, {inDb} in DB',
      kinds: { rooms: 'Rooms', mobs: 'Mobs', objects: 'Objects', resets: 'Resets' },
    },
    kind: { room: 'room', mob: 'mob', object: 'object' },
    conflicts: {
      title: 'Import blocked: some vnums belong to other zones',
      item: '{kind} {vnum} belongs to zone "{zone}" (vnum {zoneVnum})',
    },
    warnings: {
      title: '{count} warnings (non blocking)',
      codes: {
        out_of_range: 'The {kind} {vnum} is outside the zone vnum range.',
        invalid_range: 'Inconsistent vnum range: {bottom} > {top}.',
        dangling_exit: 'Room {room}: the {direction} exit points to a missing room ({target}).',
        unknown_reset_ref: 'Reset {index}: {kind} with vnum {vnum} does not exist.',
        unknown_key: 'Room {room}: the key of the {direction} exit (object {vnum}) does not exist.',
        unknown_race: 'Mob {mob}: unknown race "{id}".',
        unknown_class: 'Mob {mob}: unknown class "{id}".',
        range_overlap: 'The range overlaps zone "{zone}" (vnum {zone_vnum}).',
      },
    },
  },
  errors: {
    codes: {
      transfer: {
        zone_not_found: 'Zone not found',
        no_files: 'No file uploaded.',
        unsupported_file: 'File "{file}" not recognised: expected a zip or zone.yaml, rooms.yaml, mobs.yaml, objects.yaml, resets.yaml.',
        invalid_archive: '"{file}" is not a valid zip.',
        file_too_large: '"{file}" exceeds the {max_mb} MB limit.',
        zone_missing: 'The upload has no zone.yaml.',
        multiple_zones: 'The upload contains {count} zones: import one at a time.',
        invalid_file: 'Invalid file "{file}": {detail}',
        confirm_required: 'A real import needs dryRun=false and confirm=true.',
        vnum_conflict: 'Import blocked: {count} vnums belong to other zones ({vnums}).',
      },
    },
  },
}

export default en
