<template>
  <div class="lt-md">
    <p class="text-subtitle1 q-mb-none">
      &copy; 2018-{{ new Date().getFullYear() }} by
      <a class="footer-link" target="_blank" href="https://github.com/Josh5">Josh Sunnex</a>
    </p>
    <p class="text-subtitle1">
      {{ $t('components.footer.version') }}:
      <a class="footer-link"
         target="_blank"
         href="https://github.com/jtn0123/compresso/releases">{{ compressoVersion }}</a>
    </p>
  </div>
  <div class="gt-sm">
    <div class="row q-mt-lg">
      <div class="col q-ml-lg">
        <p class="text-subtitle1">
          &copy; 2018-{{ new Date().getFullYear() }} by
          <a class="footer-link" target="_blank" href="https://github.com/Josh5">Josh Sunnex</a>
        </p>
      </div>
      <div
        class="col-auto q-mr-lg">
        <p class="text-subtitle1">
          {{ $t('components.footer.version') }}:
          <a class="footer-link"
             target="_blank"
             href="https://github.com/jtn0123/compresso/releases">{{ compressoVersion }}</a>
        </p>
      </div>
    </div>
  </div>
</template>

<script>
import compressoGlobals from "src/js/compressoGlobals";
import { onMounted, ref } from "vue";

export default {
  setup() {
    const compressoVersion = ref('UNSET')

    function updateVersion() {
      compressoGlobals.getCompressoVersion().then((version) => {
        compressoVersion.value = version;
      })
    }

    onMounted(() => {
      updateVersion();
    })

    return {
      compressoVersion
    }
  }
}
</script>

<style>
a.footer-link {
  color: inherit;
  text-decoration: inherit;
}
</style>
