<template>
  <q-banner v-if="warnings.length" dense rounded class="bg-amber-2 text-dark q-mb-md" data-testid="spell-hints">
    <div class="text-weight-medium">{{ t('objects.spellHints.title') }}</div>
    <ul class="q-my-xs q-pl-md">
      <li v-for="w in warnings" :key="w" data-testid="spell-hint">{{ w }}</li>
    </ul>
  </q-banner>
</template>

<script setup lang="ts">
/**
 * Avvisi sugli incantesimi di pozioni, pergamene, bacchette e bastoni: l'incantesimo non esiste, oppure la skill dice (`item_types`) che non
 * può stare in quel tipo di oggetto. Come `item-spell-not-allowed` e `skill-unknown` del gioco, ma subito, senza canale live.
 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { listSkills } from '../../content/services/content-files-api'
import type { ISkill } from '../../content/types/content-files'
import type { IObjects } from '../types/objects'

const props = defineProps<{
  object: IObjects | null
  /** Nome del tipo dell'oggetto (`POTION`, `SCROLL`, `WAND`, `STAFF`...), maiuscole o minuscole. */
  typeName: string
}>()

const { t, locale } = useI18n()
const skills = ref<ISkill[] | null>(null)

/** Tipo di contenitore di incantesimi (`potion|scroll|wand|staff`), `null` per ogni altro oggetto. */
const kind = computed(() => {
  const name = props.typeName.toLowerCase()
  return ['potion', 'scroll', 'wand', 'staff'].includes(name) ? name : null
})

/** Gli incantesimi citati dall'oggetto (`extra.typeFields.spells` per pozioni e pergamene, `extra.typeFields.spell` per bacchette e bastoni). */
const cited = computed(() => {
  const fields = (props.object?.extra?.typeFields ?? {}) as Record<string, unknown>
  const list = Array.isArray(fields.spells) ? (fields.spells as unknown[]) : []
  return [...list, ...(typeof fields.spell === 'string' ? [fields.spell] : [])].map(String).filter(Boolean)
})

/** La skill per id (o nome con gli spazi al posto degli underscore) o per nome inglese, come la cerca il gioco. */
function find(name: string): ISkill | undefined {
  const id = name.replace(/ /g, '_')
  return skills.value?.find((s) => s.skillId === name || s.skillId === id || s.name === name)
}

const warnings = computed(() => {
  if (!kind.value || !skills.value) return []
  const out: string[] = []
  for (const name of cited.value) {
    const skill = find(name)
    if (!skill) out.push(t('objects.spellHints.unknown', { name }))
    else if (skill.itemTypes != null && !skill.itemTypes.includes(kind.value)) {
      const shown = skill.names?.[String(locale.value).slice(0, 2)] ?? skill.names?.en ?? skill.name ?? skill.skillId
      out.push(t('objects.spellHints.notAllowed', { name: shown, type: kind.value, allowed: skill.itemTypes.join(', ') || t('objects.spellHints.nowhere') }))
    }
  }
  return out
})

onMounted(async () => {
  try {
    skills.value = await listSkills()
  } catch {
    skills.value = null // mondo senza skill: nessun avviso
  }
})
</script>
