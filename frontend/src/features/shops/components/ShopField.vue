<template>
  <div class="column q-gutter-y-md" data-testid="shop-field">
    <q-toggle :model-value="!!shop" :disable="readonly" :label="t('shops.isKeeper')" data-testid="shop-toggle" @update:model-value="toggle" />
    <q-banner v-if="legacyShopId && !shop" dense rounded class="bg-warning text-black" data-testid="shop-legacy">
      {{ t('shops.legacy', { id: legacyShopId }) }}
    </q-banner>

    <template v-if="shop">
      <q-select
        v-model="shop.produces"
        multiple
        use-chips
        use-input
        outlined
        dense
        stack-label
        emit-value
        map-options
        input-debounce="0"
        :options="goodOptions"
        :label="t('shops.produces')"
        :hint="t('shops.producesHint')"
        :readonly="readonly"
        data-testid="shop-produces"
        @filter="filterGoods"
        @update:model-value="changed"
      />
      <q-select
        v-model="shop.trades"
        multiple
        use-chips
        outlined
        dense
        stack-label
        :options="options.objectTypes"
        :label="t('shops.trades')"
        :hint="t('shops.tradesHint')"
        :readonly="readonly"
        data-testid="shop-trades"
        @update:model-value="changed"
      />
      <div class="row q-col-gutter-md">
        <q-input
          v-model.number="shop.profit_buy"
          class="col-12 col-sm-6"
          type="number"
          step="0.05"
          min="0"
          outlined
          dense
          stack-label
          :label="t('shops.profitBuy')"
          :hint="t('shops.profitBuyHint', { pct: pct(shop.profit_buy) })"
          :readonly="readonly"
          data-testid="shop-profit-buy"
          @update:model-value="changed"
        />
        <q-input
          v-model.number="shop.profit_sell"
          class="col-12 col-sm-6"
          type="number"
          step="0.05"
          min="0"
          outlined
          dense
          stack-label
          :label="t('shops.profitSell')"
          :hint="t('shops.profitSellHint', { pct: pct(shop.profit_sell) })"
          :readonly="readonly"
          data-testid="shop-profit-sell"
          @update:model-value="changed"
        />
      </div>
      <q-input
        :model-value="shop.room"
        type="number"
        outlined
        dense
        stack-label
        clearable
        :label="t('shops.room')"
        :hint="t('shops.roomHint')"
        :readonly="readonly"
        data-testid="shop-room"
        @update:model-value="setRoom"
      />
      <div class="row q-col-gutter-md">
        <q-input v-model.number="shop.open1" class="col-6 col-sm-3" type="number" min="0" max="23" outlined dense stack-label :label="t('shops.open1')" :readonly="readonly" data-testid="shop-open1" @update:model-value="changed" />
        <q-input v-model.number="shop.close1" class="col-6 col-sm-3" type="number" min="0" max="28" outlined dense stack-label :label="t('shops.close1')" :hint="t('shops.closeHint')" :readonly="readonly" data-testid="shop-close1" @update:model-value="changed" />
        <q-input v-model.number="shop.open2" class="col-6 col-sm-3" type="number" min="0" max="23" outlined dense stack-label :label="t('shops.open2')" :readonly="readonly" data-testid="shop-open2" @update:model-value="changed" />
        <q-input v-model.number="shop.close2" class="col-6 col-sm-3" type="number" min="0" max="28" outlined dense stack-label :label="t('shops.close2')" :readonly="readonly" data-testid="shop-close2" @update:model-value="changed" />
      </div>
      <div class="row q-col-gutter-md items-center">
        <q-input
          :model-value="shop.hours.join(', ')"
          class="col-12 col-sm-8"
          outlined
          dense
          stack-label
          :label="t('shops.hoursSpans')"
          :hint="t('shops.hoursSpansHint')"
          :readonly="readonly"
          data-testid="shop-hours"
          @update:model-value="setHours"
        />
        <q-toggle v-model="shop.inventory_closed" class="col-12 col-sm-4" dense :label="t('shops.inventoryClosed')" :disable="readonly" data-testid="shop-inventory-closed" @update:model-value="changed" />
      </div>
      <div class="row q-col-gutter-md">
        <q-select
          v-model="shop.no_money_reaction"
          class="col-12 col-sm-6"
          outlined
          dense
          stack-label
          emit-value
          map-options
          :options="reactionOptions('noMoney', ['puke', 'grin', 'none'])"
          :label="t('shops.noMoneyReaction')"
          :readonly="readonly"
          data-testid="shop-no-money"
          @update:model-value="changed"
        />
        <q-select
          v-model="shop.attacked_reaction"
          class="col-12 col-sm-6"
          outlined
          dense
          stack-label
          emit-value
          map-options
          :options="reactionOptions('attacked', ['warn', 'insult', 'none'])"
          :label="t('shops.attackedReaction')"
          :readonly="readonly"
          data-testid="shop-attacked"
          @update:model-value="changed"
        />
      </div>
      <q-input
        :model-value="shop.handler ?? ''"
        outlined
        dense
        stack-label
        clearable
        :label="t('shops.handler')"
        :hint="t('shops.handlerHint')"
        :readonly="readonly"
        data-testid="shop-handler"
        @update:model-value="setHandler"
      />
      <q-expansion-item dense dense-toggle :label="t('shops.messages')" :caption="t('shops.messagesHint')" header-class="text-subtitle2" data-testid="shop-messages">
        <div class="column q-gutter-y-sm q-pa-sm">
          <div v-for="key in options.messageKeys" :key="key" class="row q-col-gutter-sm">
            <q-input
              v-for="lang in SHOP_LANGS"
              :key="lang"
              class="col-12 col-md-6"
              :model-value="shop.messages[key]?.[lang] ?? ''"
              outlined
              dense
              stack-label
              :label="`${t(`shops.messageKeys.${key}`, key)} (${lang})`"
              :readonly="readonly"
              :data-testid="`shop-message-${key}-${lang}`"
              @update:model-value="setMessage(key, lang, $event)"
            />
          </div>
        </div>
      </q-expansion-item>
      <div v-if="error" class="text-negative text-caption" data-testid="shop-error">{{ error }}</div>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * Scheda del negoziante: il campo `shop:` di un mob pachimud (merci, tipi comprati, margini, orari, reazioni, messaggi, hook).
 * Componente custom di `FieldsSection` (`v-model` = valore di `extra.shop`, `null` se il mob non è un negoziante).
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { newShop, normalizeShop, SHOP_LANGS, shopProblems } from '../helpers/shop-defaults'
import { getShopOptions, listObjectRefs } from '../services/shops-api'
import type { IObjectRef, IShopData, IShopOptions } from '../types/shops'

const props = withDefaults(
  defineProps<{
    modelValue?: unknown
    readonly?: boolean
    /** `shop_id` dei vecchi file del mob (ignorato dal gioco): si segnala se manca il negozio. */
    legacyShopId?: string | null
  }>(),
  { readonly: false, legacyShopId: null },
)
const emit = defineEmits<{ 'update:modelValue': [value: IShopData | null] }>()

const { t } = useI18n()
const shop = ref<IShopData | null>(normalizeShop(props.modelValue))
const options = ref<IShopOptions>({ objectTypes: [], messageKeys: [] })
const objects = ref<IObjectRef[]>([])
const filter = ref('')
const error = ref('')

// Reset / ricarica del record: riallinea la scheda se il valore esterno non coincide con quello corrente.
watch(
  () => props.modelValue,
  (value) => {
    if (JSON.stringify(normalizeShop(value)) !== JSON.stringify(shop.value)) shop.value = normalizeShop(value)
    error.value = ''
  },
)

onMounted(async () => {
  try {
    ;[options.value, objects.value] = await Promise.all([getShopOptions(), listObjectRefs()])
  } catch {
    // senza elenchi i select restano vuoti: i valori già presenti si vedono comunque
  }
})

/** Opzioni delle merci: gli oggetti noti più i vnum già nel negozio che non esistono. */
const goodOptions = computed(() => {
  const known = new Map(objects.value.map((o) => [o.vnum, o.shortDescription]))
  const all = [...known].map(([value, name]) => ({ value, label: `#${value} — ${name}` }))
  for (const vnum of shop.value?.produces ?? []) if (!known.has(vnum)) all.push({ value: vnum, label: `#${vnum} — ${t('shops.missingObject')}` })
  const needle = filter.value.trim().toLowerCase()
  return needle ? all.filter((o) => o.label.toLowerCase().includes(needle)) : all
})

/** Filtra le merci mentre si digita. */
function filterGoods(value: string, update: (fn: () => void) => void): void {
  update(() => {
    filter.value = value
  })
}

/** Percentuale leggibile di un moltiplicatore. */
function pct(value: number): number {
  return Math.round((Number(value) || 0) * 100)
}

/** Opzioni di una reazione (`kind` = `noMoney` o `attacked`). */
function reactionOptions(kind: string, values: string[]): { value: string; label: string }[] {
  return values.map((value) => ({ value, label: t(`shops.reactions.${kind}.${value}`) }))
}

/** Comunica al form il valore corrente. */
function changed(): void {
  error.value = ''
  emit('update:modelValue', shop.value === null ? null : JSON.parse(JSON.stringify(shop.value)))
}

/** Rende il mob un negoziante (valori di `pachimud new shop`) o gli toglie il negozio. */
function toggle(on: boolean): void {
  shop.value = on ? newShop() : null
  changed()
}

/** Stanza del negozio: vuoto = ovunque. */
function setRoom(value: string | number | null): void {
  if (shop.value) shop.value.room = value === null || value === '' ? null : Number(value)
  changed()
}

/** Hook Python: vuoto = nessuno. */
function setHours(value: string | number | null): void {
  if (shop.value) shop.value.hours = String(value ?? '').split(',').map((h) => h.trim()).filter(Boolean)
  changed()
}

function setHandler(value: string | number | null): void {
  if (shop.value) shop.value.handler = value ? String(value) : null
  changed()
}

/** Imposta (o toglie, se vuoto) il testo di un messaggio in una lingua. */
function setMessage(key: string, lang: string, value: string | number | null): void {
  if (!shop.value) return
  const text = String(value ?? '')
  const forKey = { ...(shop.value.messages[key] ?? {}) }
  if (text) forKey[lang] = text
  else delete forKey[lang]
  if (Object.keys(forKey).length) shop.value.messages[key] = forKey
  else delete shop.value.messages[key]
  changed()
}

/** Valida la scheda (usato dal form prima del salvataggio). */
function validate(): boolean {
  if (!shop.value) return true
  const problems = shopProblems(shop.value)
  error.value = problems.map((p) => t(`shops.errors.${p}`)).join(' ')
  return problems.length === 0
}

defineExpose({ validate })
</script>
