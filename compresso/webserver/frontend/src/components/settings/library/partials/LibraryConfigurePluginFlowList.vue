<template>
  <!-- START PLUGIN TYPES LIST-->
  <div class="q-gutter-sm">
    <q-list style="width: 100%">
      <q-expansion-item
        v-for="pt in pluginTypes"
        :key="pt.type"
        v-bind="pt"
        group="pluginTypes"
        icon="list_alt"
        :label="$t(pt.labelCode).length < 50 ? $t(pt.labelCode) : $t(pt.labelCode).substring(0, 48) + '..'"
        :caption="$t(pt.labelCode + 'Caption') !== pt.labelCode + 'Caption' ? $t(pt.labelCode + 'Caption') : ''"
        caption-lines="4"
        class="text-h8 text-primary"
      >
        <q-card inline style="" class="q-ma-lg-xs q-pa-lg-sm q-pa-sm-none">
          <div class="row">
            <q-card-section class="col justify-center full-height full-width text-center q-px-none">
              <q-list bordered class="rounded-borders q-pl-none" style="">
                <draggable
                  class="library-plugin-flow-group"
                  item-key="order"
                  tag="transition-group"
                  :component-data="{ tag: 'ul', name: 'flip-list', type: 'transition' }"
                  :model-value="pluginFlowByType[pt.type] ?? []"
                  @update:model-value="updatePluginFlow(pt.type, $event)"
                  v-bind="dragOptions"
                  @end="savePluginFlow(pt.type)"
                >
                  <template #item="{ element, index }">
                    <q-item :key="index" class="q-px-none rounded-borders" active-class="library-plugin-flow-item">
                      <q-item-section avatar class="q-px-sm q-mx-sm">
                        <q-avatar rounded>
                          <q-icon name="drag_handle" class="" style="max-width: 30px">
                            <q-tooltip class="bg-white text-primary">{{ $t('tooltips.move') }}</q-tooltip>
                          </q-icon>
                        </q-avatar>
                      </q-item-section>

                      <q-separator inset vertical class="q-mr-sm" />

                      <!--                      <q-item-section avatar class="">
                                              <q-skeleton v-if="!element.icon" width="35px" height="35px"/>
                                              <q-avatar v-else rounded size="35px">
                                                <q-img :src="element.icon" class="" style="max-width: 30px;"/>
                                              </q-avatar>
                                            </q-item-section>-->

                      <q-item-section top class="q-mx-md">
                        <q-item-label lines="1" class="text-left">
                          <q-skeleton v-if="!element.icon" width="35px" height="35px" />
                          <q-avatar v-else rounded size="35px">
                            <q-img :src="element.icon" class="" style="max-width: 30px" />
                          </q-avatar>

                          <span class="text-weight-medium q-ml-sm">{{ element.name }}</span>
                        </q-item-label>
                        <q-item-label caption lines="1" class="text-left q-ml-sm">
                          {{ element.description }}
                        </q-item-label>
                        <q-tooltip anchor="center middle" self="center middle" class="bg-white text-primary lt-sm">
                          {{ element.name }}
                        </q-tooltip>
                      </q-item-section>

                      <q-separator inset vertical class="gt-xs q-mx-sm" />

                      <q-item-section side class="gt-xs q-px-sm">
                        <q-item-label lines="1" class="text-left">
                          <span class="text-weight-medium">{{ index + 1 }}</span>
                          <q-tooltip anchor="center right" self="center left" class="bg-white text-primary"
                            >{{ $t('tooltips.position') }}
                          </q-tooltip>
                        </q-item-label>
                      </q-item-section>
                    </q-item>
                  </template>
                </draggable>
              </q-list>
            </q-card-section>
          </div>
        </q-card>
      </q-expansion-item>
    </q-list>
  </div>
  <!-- END PLUGIN TYPES LIST-->
</template>

<script lang="ts">
import axios from 'axios'
import { getCompressoApiUrl } from 'src/js/compressoGlobals'
import draggable from 'vuedraggable'
import { defineComponent } from 'vue'
import type { PropType } from 'vue'
import { createLogger } from 'src/composables/useLogger'
import type { ApiSchema } from 'src/types/contracts'
import type { PluginFlowEntry, PluginFlowType } from 'src/types/plugins'

// Plugin flow list refreshes when the parent dialog is opened
export default defineComponent({
  name: 'LibraryConfigurePluginFlowList',
  components: {
    draggable,
  },
  props: {
    libraryId: {
      type: Number as PropType<number | null>,
      required: false,
      default: null,
    },
  },
  created() {
    this.fetchPluginTypes()
  },
  methods: {
    fetchPluginTypes: function (): void {
      // Fetch from server
      axios<ApiSchema<'PluginTypesResults'>>({
        method: 'get',
        url: getCompressoApiUrl('v2', 'plugins/flow/types'),
      }).then((response) => {
        const results = response.data.results
        const pluginTypes: PluginFlowType[] = []
        for (let i = 0; i < results.length; i++) {
          const pluginType = results[i]
          if (!pluginType) continue
          const labelCode = pluginType
            .split('_')
            .map((word: string, index: number) => {
              if (index === 0) return word
              return word.slice(0, 1).toUpperCase() + word.slice(1).toLowerCase()
            })
            .join('')
          pluginTypes.push({
            type: pluginType,
            labelCode: 'components.plugins.types.' + labelCode,
          })
          this.pluginFlowByType[pluginType] = []
        }
        this.pluginTypes = pluginTypes

        this.fetchPluginFlow()
      })
    },
    fetchPluginFlow: function (): void {
      for (let i = 0; i < this.pluginTypes.length; i++) {
        const pluginType = this.pluginTypes[i]
        if (!pluginType) continue
        let data = {
          plugin_type: pluginType.type,
          library_id: this.libraryId,
        }
        axios<ApiSchema<'PluginFlowResults'>>({
          method: 'post',
          url: getCompressoApiUrl('v2', 'plugins/flow'),
          data: data,
        }).then((response) => {
          this.pluginFlowByType[pluginType.type] = response.data.results
        })
      }
    },
    updatePluginFlow: function (pluginType: string, flow: PluginFlowEntry[]): void {
      this.pluginFlowByType[pluginType] = flow
    },
    savePluginFlow: function (pluginType: string): void {
      let data = {
        plugin_type: pluginType,
        plugin_flow: this.pluginFlowByType[pluginType],
        library_id: this.libraryId,
      }
      axios({
        method: 'post',
        url: getCompressoApiUrl('v2', 'plugins/flow/save'),
        data: data,
      })
        .then(() => {
          // Notify save
          /*this.$q.notify({
          color: 'positive',
          position: 'top',
          message: this.$t('notifications.saved'),
          icon: 'cloud_done',
          actions: [{ icon: 'close', color: 'white' }]
        })*/
        })
        .catch(() => {
          // Notify failure
          this.$q.notify({
            color: 'negative',
            position: 'top',
            message: this.$t('components.plugins.errorSavingFlow'),
            icon: 'report_problem',
            actions: [{ icon: 'close', color: 'white' }],
          })
        })
    },
    movePluginInFlow: function (
      pluginType: string,
      currentIndex: number,
      _pluginId: string,
      direction: 'up' | 'down',
    ): void {
      const currentFlow = this.pluginFlowByType[pluginType]
      if (!currentFlow) return
      const pluginFlow = currentFlow.slice()

      // Generate new index
      if (direction === 'up') {
        // Dont move up if already at the top
        if (currentIndex === 0) {
          this.log.debug('Cannot move up - already at the top')
          return
        }
      }
      if (direction === 'down') {
        // Dont move down if already at the bottom
        if (currentIndex + 1 === pluginFlow.length) {
          this.log.debug('Cannot move down - already at the bottom')
          return
        }
      }

      // Extract item data to insert below
      const pluginData = pluginFlow[currentIndex]
      if (!pluginData) return
      const newIndex = direction === 'up' ? currentIndex - 1 : currentIndex + 1

      // Reorder flow and reorder
      pluginFlow.splice(currentIndex, 1)
      pluginFlow.splice(newIndex, 0, pluginData)

      // Save new order
      this.pluginFlowByType[pluginType] = pluginFlow
      this.savePluginFlow(pluginType)
    },
  },
  data: function () {
    return {
      options: {
        dropzoneSelector: '.q-list',
        draggableSelector: '.q-item',
      },
      pluginTypes: [] as PluginFlowType[],
      pluginFlowByType: {} as Record<string, PluginFlowEntry[]>,
      files: [] as unknown[],
      log: createLogger('PluginFlowList'),
    }
  },
  computed: {
    dragOptions() {
      return {
        animation: 100,
        group: 'pluginFlow',
        disabled: false,
        ghostClass: 'ghost',
        direction: 'vertical',
        delay: 200,
        delayOnTouchOnly: true,
      }
    },
  },
  setup() {
    return {}
  },
})
</script>
<style>
.library-plugin-flow-group {
  padding-left: 0;
  padding-right: 20px;
}

.library-plugin-flow-item {
  background: var(--q-secondary);
}

.ghost {
  opacity: 0;
}
</style>
