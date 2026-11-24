<template>
  <q-card flat bordered :data-testid="testid">
    <q-card-section class="row items-center no-wrap q-py-sm">
      <div class="text-h6 col ellipsis"><slot name="title">{{ title }}</slot></div>
      <q-btn
        flat
        dense
        round
        :icon="open ? mdiChevronUp : mdiChevronDown"
        :aria-label="open ? t('card.collapse') : t('card.expand')"
        :aria-expanded="open"
        data-testid="card-toggle"
        @click="toggle"
      />
    </q-card-section>
    <q-slide-transition>
      <div v-show="open">
        <q-separator />
        <slot />
      </div>
    </q-slide-transition>
  </q-card>
</template>

<script setup lang="ts">
/**
 * Scheda con titolo e icona per ridurla a solo intestazione. Lo stato aperto/chiuso e' ricordato nel browser per `storageKey`
 * (comodita' per utente: se il localStorage non e' disponibile resta aperta).
 */
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { mdiChevronDown, mdiChevronUp } from '@quasar/extras/mdi-v7'

const props = withDefaults(defineProps<{ title?: string; storageKey?: string | undefined; defaultOpen?: boolean; testid?: string | undefined }>(), {
  title: '',
  storageKey: undefined,
  defaultOpen: true,
  testid: undefined,
})
const { t } = useI18n()

/** Legge lo stato salvato; senza chiave o senza storage vale `defaultOpen`. */
function initial(): boolean {
  if (!props.storageKey) return props.defaultOpen
  try {
    const saved = localStorage.getItem(`card:${props.storageKey}`)
    return saved === null ? props.defaultOpen : saved === '1'
  } catch {
    return props.defaultOpen
  }
}

const open = ref(initial())

/** Apre/chiude e ricorda la scelta. */
function toggle(): void {
  open.value = !open.value
  if (!props.storageKey) return
  try {
    localStorage.setItem(`card:${props.storageKey}`, open.value ? '1' : '0')
  } catch {
    /* storage non disponibile: la scelta vale solo per questa visita */
  }
}
</script>
