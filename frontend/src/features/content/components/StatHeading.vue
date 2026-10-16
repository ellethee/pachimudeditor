<template>
  <div class="text-subtitle2 q-mt-sm">{{ text }}</div>
</template>

<script setup lang="ts">
/** Titoletto di gruppo dentro un form field-driven (componente custom di `FieldsSection`). */
defineProps<{ text?: string }>()
</script>
