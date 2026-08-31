<template>
  <q-btn outline color="secondary" class="full-width" :label="t('navigation.submit')" type="submit" />
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>
