<template>
  <div class="q-pa-md">
    <h1 class="text-h5 q-mt-none q-mb-md">{{ t('players.title') }}</h1>
    <q-tabs v-model="tab" dense align="left" class="text-primary" active-color="primary" indicator-color="primary">
      <q-tab name="accounts" :label="t('players.tabs.accounts')" :icon="mdiAccount" />
      <q-tab name="characters" :label="t('players.tabs.characters')" :icon="mdiAccountGroup" />
    </q-tabs>
    <q-separator />
    <q-tab-panels v-model="tab" animated keep-alive>
      <q-tab-panel name="accounts" class="q-px-none">
        <accounts-panel @show-characters="showCharacters" />
      </q-tab-panel>
      <q-tab-panel name="characters" class="q-px-none">
        <characters-panel :account-id="accountId" />
      </q-tab-panel>
    </q-tab-panels>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { mdiAccount, mdiAccountGroup } from '@quasar/extras/mdi-v7'
import AccountsPanel from '../components/AccountsPanel.vue'
import CharactersPanel from '../components/CharactersPanel.vue'
import type { IAccount } from '../types/players'

const { t } = useI18n()
const tab = ref<'accounts' | 'characters'>('accounts')
const accountId = ref<number>()

/**
 * Passa al tab dei personaggi filtrato sull'account scelto.
 *
 * @param account - account selezionato
 */
function showCharacters(account: IAccount): void {
  accountId.value = account.id
  tab.value = 'characters'
}
</script>
