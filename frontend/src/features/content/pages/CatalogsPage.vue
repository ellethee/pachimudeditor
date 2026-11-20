<template>
  <text-files-page :areas="['locales', 'texts']" kind="locales" />
</template>

<script setup lang="ts">
/** Cataloghi dei messaggi (`locales/<lingua>/**.yaml`) e testi lunghi (`texts/*.txt`). */
import TextFilesPage from './TextFilesPage.vue'
</script>
