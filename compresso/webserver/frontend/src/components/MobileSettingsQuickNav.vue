<template>
  <!--START QUICK NAV-->
  <div v-if="$q.platform.is.mobile" class="mobile-quick-nav">
    <q-separator />
    <div class="row q-pa-sm">
      <div class="col-6 q-pr-xs">
        <CompressoStandardButton
          v-if="prevEnabled"
          icon="navigate_before"
          class="full-width"
          @click="$router.push(prevPath)"
          :label="prevLabel"
        />
      </div>
      <div class="col-6 q-pl-xs">
        <CompressoStandardButton
          v-if="nextEnabled"
          icon-right="navigate_next"
          class="full-width"
          @click="$router.push(nextPath)"
          :label="nextLabel"
        />
      </div>
    </div>
  </div>
  <!--END QUICK NAV-->
</template>

<script>
import CompressoStandardButton from 'components/ui/buttons/CompressoStandardButton.vue'

export default {
  name: 'MobileSettingsQuickNav',
  components: { CompressoStandardButton },
  props: {
    prevEnabled: {
      type: Boolean,
    },
    prevLabel: {
      type: String,
    },
    prevPath: {
      type: String,
    },
    nextEnabled: {
      type: Boolean,
    },
    nextLabel: {
      type: String,
    },
    nextPath: {
      type: String,
    },
  },
  setup() {
    return {}
  },
}
</script>

<style scoped>
.mobile-quick-nav {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 100;
  background: var(--q-card-head);
}
</style>
