<template>
  <q-list padding>
    <q-item>
      <q-space />
      <q-item-section class="on-right" style="padding-right: 0" top side>
        <div class="text-grey-8 q-gutter-xs">
          <q-btn
            dense
            size="sm"
            color="secondary"
            :label="$t('buttons.dismissAll')"
            @click="dismissAllNotifications()"
          />
        </div>
      </q-item-section>
    </q-item>

    <q-item v-for="(notification, index) in notificationsList" :key="index" clickable>
      <q-item-section avatar @click="runNotificationAction(index)">
        <q-icon :color="notification.color" :name="notification.icon" />
      </q-item-section>

      <q-item-section @click="runNotificationAction(index)">
        <q-item-label>
          {{ notification.label }}
        </q-item-label>
        <q-item-label caption lines="1">
          {{ notification.message }}
        </q-item-label>
        <q-tooltip>
          {{ notification.message }}
        </q-tooltip>
      </q-item-section>

      <q-item-section top side>
        <div class="text-grey-8 q-gutter-xs">
          <CompressoListActionButton class="gt-xs" icon="close" color="grey-8" @click="dismissNotification(index)" />
        </div>
      </q-item-section>
    </q-item>
  </q-list>
</template>

<script lang="ts">
import compressoGlobals from 'src/js/compressoGlobals'
import CompressoListActionButton from 'components/ui/buttons/CompressoListActionButton.vue'
import { createLogger } from 'src/composables/useLogger'
import type { DisplayNotification } from 'src/js/compressoGlobals'

const log = createLogger('Notifications')

export default {
  name: 'DrawerNotifications',
  components: { CompressoListActionButton },
  methods: {
    runNotificationAction: function (index: number) {
      if (this.notificationActionsDisabled) {
        log.debug('Notification actions disabled')
        return
      }
      // Disable any other actions being triggered while this one is being run
      this.notificationActionsDisabled = true
      // Get notification by index
      const notification = this.notificationsList[index]
      if (!notification) return
      if (
        typeof notification.navigation === 'object' &&
        notification.navigation !== null &&
        !Array.isArray(notification.navigation)
      ) {
        // Handle full url
        const navigation = notification.navigation
        if (typeof navigation.url === 'string') {
          window.open(navigation.url, '_blank')
        }
        // Handle routing any given 'push' links
        if (typeof navigation.push === 'string') {
          this.$router.push(navigation.push)
        }
        const events = Array.isArray(navigation.events)
          ? navigation.events.filter((event): event is string => typeof event === 'string')
          : []
        if (events.length > 0) {
          let i = 0
          const loopEventsDelayed = function (emitter: (event: string) => void) {
            if (i < events.length) {
              setTimeout(function () {
                const triggerEvent = events[i]
                if (triggerEvent) emitter(triggerEvent)
                i++
                loopEventsDelayed(emitter)
              }, 200)
            }
          }
          loopEventsDelayed(this.$global.$emit)
        }
      }
      // Re-enable notification actions
      this.notificationActionsDisabled = false
    },
    dismissNotification: function (index: number) {
      // Get notification by index
      const notification = this.notificationsList[index]
      if (!notification) return
      // Dismiss the matching notification
      compressoGlobals.dismissNotifications(this.$t, [notification.uuid]).then(() => {
        this.updateNotificationList()
      })
    },
    dismissAllNotifications: function () {
      const uuidList: string[] = []
      for (let i = 0; i < this.notificationsList.length; i++) {
        const notification = this.notificationsList[i]
        if (notification) uuidList.push(notification.uuid)
      }
      // Dismiss the notifications
      compressoGlobals.dismissNotifications(this.$t, uuidList).then(() => {
        this.updateNotificationList()
      })
    },
    updateNotificationList: function () {
      compressoGlobals.updateCompressoNotifications(this.$t).then((notificationsList) => {
        this.notificationsList = notificationsList
      })
    },
    startNotificationReload: function () {
      // Run an initial update
      this.updateNotificationList()
      // Start an interval to reload it every 15 seconds
      this.reloadInterval = setInterval(() => {
        this.updateNotificationList()
      }, 15000)
    },
    stopNotificationReload: function () {
      if (this.reloadInterval) clearInterval(this.reloadInterval)
    },
  },
  mounted() {
    this.startNotificationReload()
  },
  unmounted() {
    this.stopNotificationReload()
  },
  data: function () {
    return {
      reloadInterval: null as ReturnType<typeof setInterval> | null,
      notificationsList: [] as DisplayNotification[],
      notificationActionsDisabled: false,
    }
  },
}
</script>
