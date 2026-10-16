import { markRaw } from 'vue'
import { useQuasar } from 'quasar'
import { useI18n } from 'vue-i18n'
import { mdiContentCopy, mdiDoor } from '@quasar/extras/mdi-v7'
import { PachiEditDialog } from '@ilpachi/pachi-kit/edit-dialog'
import type { AwaitableData, ISectionDefinition } from '@ilpachi/pachi-kit/edit-dialog'
import { FieldsSection } from '@ilpachi/pachi-kit/fields'
import { applyDescriptors, enumNames } from '../../shared/helpers/descriptor-rows'
import { createExtraEditor } from '../../shared/helpers/extra-fields'
import { LOCKED_DIALOG_CLASS, guardOf, guardSection } from '../../shared/helpers/record-guard'
import { useWorld } from '../../shared/helpers/world-state'
import ExitsSection from '../components/ExitsSection.vue'
import ExtraDescriptionsSection from '../components/ExtraDescriptionsSection.vue'
import {
  cloneRoom,
  createExit,
  createExtra,
  createRoom,
  getRoom,
  listAllRooms,
  nextRoomVnum,
  removeExit,
  removeExtra,
  updateExit,
  updateExtra,
  updateRoom,
} from '../services/rooms-api'
import { useRoomsStore } from '../stores/use-rooms-store'
import type { IEnumOptions, IExitRow, IExtraRow, IRoom, IRoomDetail, IRoomInput, IRoomOption } from '../types/rooms'
import { describeError } from '../utils/error-helper'
import { buildCloneFieldRows, buildRoomFieldRows } from '../utils/room-fields'

/** Valori della sezione "generale" restituiti da `FieldsSection`. */
interface IGeneralValues {
  vnum: number
  sectorType: number
  name: string
  description: string
  healRate: number
  manaRate: number
  flags: string[]
}

/** Contesto di apertura dell'editor stanza. */
interface IEditorContext {
  enums: IEnumOptions
  roomOptions: IRoomOption[]
  zoneId: number
  detail: IRoomDetail | null
  suggestedVnum: number
}

/** Converte il valore di un campo numerico opzionale (`''` dopo la cancellazione) in `number | null`. */
function numberOrNull(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

/**
 * Dialog di creazione/modifica/clonazione stanza (PachiEditDialog con sezioni: generale, uscite,
 * extra description). Da chiamare in `setup()`.
 *
 * @param onSaved - richiamata dopo ogni scrittura riuscita (anche parziale) per ricaricare la lista
 * @returns funzioni di apertura dei dialog
 */
export function useRoomDialogs(onSaved: () => void | Promise<void>) {
  const $q = useQuasar()
  const { t, te } = useI18n()
  const store = useRoomsStore()
  const { readOnly, supports, fieldOf, extraFieldsOf, declaresExtra } = useWorld()

  /** Costruisce le righe (una per direzione) dell'editor delle uscite. */
  function buildExitRows(enums: IEnumOptions, detail: IRoomDetail | null): IExitRow[] {
    return enums.direction.map((option) => {
      const exit = detail?.exits.find((candidate) => candidate.direction === option.value)
      return {
        direction: option.value,
        hasExit: !!exit,
        description: exit?.description ?? null,
        keywords: exit?.keywords ?? null,
        doorFlag: exit?.doorFlag ?? enums.doorFlag[0]?.value ?? 0,
        isOpen: exit?.isOpen ?? true,
        isLocked: exit?.isLocked ?? false,
        keyVnum: exit?.keyVnum ?? null,
        targetRoomId: exit?.targetRoomId ?? null,
        extra: { ...(exit?.extra ?? {}) },
      }
    })
  }

  /** Apre l'editor (creazione se `detail` è nullo). */
  function openEditor(ctx: IEditorContext): void {
    const { enums, detail, zoneId } = ctx
    const exitExtra = extraFieldsOf('exit').filter((field) => field.group !== 'diagnostic')
    const editing = detail !== null
    const general = editing
      ? {
          vnum: detail.vnum,
          sectorType: detail.sectorType,
          name: detail.name,
          description: detail.description,
          healRate: detail.healRate,
          manaRate: detail.manaRate,
          flags: [...detail.flags],
        }
      : {
          vnum: ctx.suggestedVnum,
          sectorType: enums.sectorType[0]?.value ?? 0,
          name: '',
          description: '',
          healRate: 100,
          manaRate: 100,
          flags: [] as string[],
        }
    const extraRows: IExtraRow[] = (detail?.extraDescriptions ?? []).map((extra) => ({
      uid: `x${extra.id}`,
      keywords: extra.keywords,
      text: extra.text,
    }))

    // Stato già scritto sul server (per riprovare dopo un salvataggio parziale senza duplicare).
    let roomId: number | null = detail?.id ?? null
    const exitIds = new Map<number, number>((detail?.exits ?? []).map((exit) => [exit.direction, exit.id]))
    const extraIds = new Map<string, number>((detail?.extraDescriptions ?? []).map((extra) => [`x${extra.id}`, extra.id]))

    const rawEnums = enums as unknown as Record<string, unknown>
    /** Chiavi di `extra` delle uscite che il mondo permette di modificare. */
    const exitEditable = exitExtra.filter((field) => !field.readOnly).map((field) => field.name)
    const guard = guardOf(detail?.extra)
    const locked = readOnly.value || guard.corrupted
    const extraEditor = createExtraEditor({
      t,
      te,
      descriptors: extraFieldsOf('room'),
      declared: declaresExtra('room'),
      readonly: locked,
      extra: detail?.extra,
      enums: rawEnums,
      order: 40,
    })
    // se il mondo dichiara un settore proprio in `extra` (ROM, Diku Modificato), `sectorType` è solo un'approssimazione: sola lettura
    const romSector = extraFieldsOf('room').some((field) => field.name === 'sector')
    const generalRows = applyDescriptors(
      buildRoomFieldRows(t, enums.sectorType, editing, enumNames(rawEnums, fieldOf('room', 'flags'))),
      'room',
      fieldOf,
      t,
    ).map((row) =>
      row.map((def) =>
        romSector && def.field === 'sectorType' ? { ...def, disable: true, hint: t('rooms.fields.sectorRomHint') } : def,
      ),
    )
    const sections: ISectionDefinition[] = [
      {
        key: 'general',
        title: t('rooms.dialog.general'),
        component: markRaw(FieldsSection),
        props: { rows: generalRows },
        initialValue: general,
        order: 10,
        container: { type: 'card', flat: true, bordered: true, class: 'q-pa-md q-mb-md' },
      },
      {
        key: 'exits',
        title: t('rooms.exits.title'),
        component: markRaw(ExitsSection),
        props: {
          directionOptions: enums.direction,
          doorOptions: enums.doorFlag,
          roomOptions: ctx.roomOptions,
          extraFields: exitExtra,
        },
        initialValue: { rows: buildExitRows(enums, detail) },
        order: 20,
        container: { type: 'card', flat: true, bordered: true, class: 'q-pa-md q-mb-md' },
      },
      {
        key: 'extras',
        title: t('rooms.extras.title'),
        component: markRaw(ExtraDescriptionsSection),
        initialValue: { rows: extraRows },
        order: 30,
        enabled: supports('supportsExtraDescriptions'),
        container: { type: 'card', flat: true, bordered: true, class: 'q-pa-md' },
      },
    ]
    if (extraEditor) sections.push(extraEditor.section)
    const banner = guardSection(guard)
    if (banner) sections.unshift(banner)

    $q.dialog({
      component: PachiEditDialog,
      componentProps: {
        title: editing ? t('rooms.dialog.edit') : t('rooms.dialog.create'),
        icon: mdiDoor,
        sections,
        avoidHideWithChanges: true,
        commonProps: locked ? { readonly: true } : {},
        cardClass: guard.corrupted ? LOCKED_DIALOG_CLASS : '',
        width: '1000px',
        maxWidth: '95vw',
      },
    }).onOk(async ({ data, onSuccess, onError }: AwaitableData) => {
      if (locked) {
        onError(new Error(t('worlds.readOnlyHint')))
        return
      }
      const values = data.sections.general as IGeneralValues
      const exits = (data.sections.exits as { rows: IExitRow[] }).rows
      const extras = (data.sections.extras as { rows: IExtraRow[] } | undefined)?.rows ?? []
      const quiet = { autoError: false }
      let written = false
      try {
        const body: IRoomInput = {
          vnum: values.vnum,
          zoneId,
          name: values.name,
          description: values.description ?? '',
          sectorType: values.sectorType,
          flags: values.flags ?? [],
          healRate: numberOrNull(values.healRate) ?? 100,
          manaRate: numberOrNull(values.manaRate) ?? 100,
          clanId: detail?.clanId ?? null,
          owner: detail?.owner ?? null,
        }
        // `extra` (campi specifici del mondo) solo con le chiavi cambiate
        const extra = extraEditor?.collect(data.sections.extra)
        if (extra) body.extra = extra
        if (roomId === null) {
          roomId = (await createRoom(body, quiet)).id
        } else {
          await updateRoom(roomId, body, quiet)
        }
        written = true
        const id = roomId

        for (const row of exits) {
          const serverId = exitIds.get(row.direction)
          const original = detail?.exits.find((candidate) => candidate.id === serverId)?.extra ?? {}
          const changedExtra = Object.fromEntries(
            exitEditable.filter((key) => JSON.stringify(row.extra?.[key]) !== JSON.stringify(original[key]) && row.extra?.[key] !== undefined).map((key) => [key, row.extra![key]]),
          )
          const payload = {
            ...(Object.keys(changedExtra).length ? { extra: changedExtra } : {}),
            description: row.description,
            keywords: row.keywords,
            doorFlag: row.doorFlag,
            isOpen: row.isOpen,
            isLocked: row.isLocked,
            keyVnum: numberOrNull(row.keyVnum),
            targetRoomId: row.targetRoomId,
          }
          if (row.hasExit && serverId === undefined) {
            exitIds.set(row.direction, (await createExit(id, { direction: row.direction, ...payload }, quiet)).id)
          } else if (row.hasExit && serverId !== undefined) {
            await updateExit(id, serverId, payload, quiet)
          } else if (!row.hasExit && serverId !== undefined) {
            await removeExit(id, serverId, quiet)
            exitIds.delete(row.direction)
          }
        }

        const currentUids = new Set(extras.map((extra) => extra.uid))
        for (const [uid, serverId] of supports('supportsExtraDescriptions') ? [...extraIds] : []) {
          if (!currentUids.has(uid)) {
            await removeExtra(id, serverId, quiet)
            extraIds.delete(uid)
          }
        }
        for (const extra of extras) {
          const payload = { keywords: extra.keywords, text: extra.text }
          const serverId = extraIds.get(extra.uid)
          if (serverId === undefined) {
            extraIds.set(extra.uid, (await createExtra(id, payload, quiet)).id)
          } else {
            await updateExtra(id, serverId, payload, quiet)
          }
        }

        onSuccess()
        $q.notify({ type: 'positive', message: t('rooms.notify.saved') })
      } catch (error) {
        onError(new Error(await describeError(error, t, te)))
      } finally {
        if (written) await onSaved()
      }
    })
  }

  /** Elenco stanze (tutte le zone) come opzioni per le select di destinazione. */
  async function loadRoomOptions(): Promise<IRoomOption[]> {
    const rooms = await listAllRooms()
    return rooms.map((room) => ({ id: room.id, label: `${room.vnum} - ${room.name}` }))
  }

  /**
   * Apre l'editor per creare una stanza nella zona indicata (vnum libero suggerito).
   *
   * @param zoneId - zona della nuova stanza
   */
  async function openCreate(zoneId: number): Promise<void> {
    const [enums, roomOptions, suggestedVnum] = await Promise.all([
      store.ensureEnums(),
      loadRoomOptions(),
      nextRoomVnum(zoneId),
    ])
    openEditor({ enums, roomOptions, zoneId, detail: null, suggestedVnum })
  }

  /**
   * Apre l'editor su una stanza esistente.
   *
   * @param roomId - id della stanza
   */
  async function openEdit(roomId: number): Promise<void> {
    const [enums, roomOptions, detail] = await Promise.all([store.ensureEnums(), loadRoomOptions(), getRoom(roomId)])
    openEditor({ enums, roomOptions, zoneId: detail.zoneId, detail, suggestedVnum: detail.vnum })
  }

  /**
   * Apre il dialog di clonazione (nuovo vnum + nome opzionale; le uscite non si copiano).
   *
   * @param room - stanza da clonare
   */
  async function openClone(room: IRoom): Promise<void> {
    const suggested = await nextRoomVnum(room.zoneId)
    $q.dialog({
      component: PachiEditDialog,
      componentProps: {
        title: t('rooms.clone.title'),
        icon: mdiContentCopy,
        sections: [
          {
            key: 'clone',
            title: t('rooms.clone.title'),
            component: markRaw(FieldsSection),
            props: { rows: buildCloneFieldRows(t) },
            initialValue: { vnum: suggested, name: t('rooms.clone.defaultName', { name: room.name }) },
          },
        ] as ISectionDefinition[],
        width: '460px',
        maxWidth: '95vw',
      },
    }).onOk(async ({ data, onSuccess, onError }: AwaitableData) => {
      const values = data.sections.clone as { vnum: number; name: string }
      try {
        await cloneRoom(room.id, { vnum: values.vnum, name: values.name || undefined }, { autoError: false })
        onSuccess()
        $q.notify({ type: 'positive', message: t('rooms.notify.cloned') })
        await onSaved()
      } catch (error) {
        onError(new Error(await describeError(error, t, te)))
      }
    })
  }

  return { openCreate, openEdit, openClone }
}
