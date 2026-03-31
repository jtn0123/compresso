<template>
  <div class="lt-md">
    <p class="text-subtitle2 q-mb-none footer-text">
      Compresso v{{ compressoVersion }}
    </p>
  </div>
  <div class="gt-sm">
    <div class="row q-mt-lg items-center">
      <div class="col q-ml-lg">
        <p class="text-subtitle2 footer-text">
          <a class="footer-link" target="_blank"
             href="https://github.com/jtn0123/compresso">Compresso</a>
          &mdash; Media Library Optimizer
        </p>
      </div>
      <div class="col-auto q-mr-lg">
        <p class="text-subtitle2 footer-text">
          <a class="footer-link"
             target="_blank"
             href="https://github.com/jtn0123/compresso/releases">v{{ compressoVersion }}</a>
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
  text-decoration: none;
  opacity: 0.85;
  transition: opacity 0.2s ease;
}
a.footer-link:hover {
  opacity: 1;
  text-decoration: underline;
}
.footer-text {
  opacity: 0.75;
  font-weight: 400;
}
</style>
