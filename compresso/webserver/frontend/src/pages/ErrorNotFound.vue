<template>
  <div class="fullscreen bg-blue text-white text-center q-pa-md flex flex-center">
    <div>
      <div style="font-size: 30vh">
        404
      </div>

      <div class="text-h2" style="opacity:.4">
        Oops. Nothing here...
      </div>

      <div class="text-subtitle1 q-mt-md" style="opacity:.7">
        {{ $t('pages.errorNotFound.message') }}
      </div>

      <div class="q-mt-xl q-gutter-sm">
        <q-btn
          color="white"
          text-color="blue"
          unelevated
          to="/ui/dashboard"
          :label="$t('navigation.backToDashboard')"
          no-caps
        />
        <q-btn
          outline
          color="white"
          icon="help_outline"
          :label="$t('pages.errorNotFound.helpLink')"
          no-caps
          @click="showHelp"
        />
      </div>
    </div>
  </div>
</template>

<script>
import { defineComponent } from 'vue'

export default defineComponent({
  name: 'ErrorNotFound',
  methods: {
    showHelp() {
      // Navigate to dashboard where help dialog can be accessed
      this.$router.push('/ui/dashboard');
    }
  }
})
</script>
