import axios from "axios";
import { Notify, setCssVar } from 'quasar'

let $compresso = {};

export const getCompressoServerUrl = function () {
  if (typeof $compresso.serverUrl === 'undefined') {
    let parser = document.createElement('a');
    parser.href = window.location.href;

    $compresso.serverUrl = parser.protocol + '//' + parser.host;
  }
  return $compresso.serverUrl;
}

export const getCompressoApiUrl = function (api_version, api_endpoint) {
  if (typeof $compresso.apiUrl === 'undefined') {
    let serverUrl = getCompressoServerUrl();

    $compresso.apiUrl = serverUrl + '/compresso/api';
  }
  return $compresso.apiUrl + '/' + api_version + '/' + api_endpoint;
}

export const setTheme = function (mode) {
  if (mode === 'dark') {
    setCssVar('primary', '#22916a');
    setCssVar('secondary', '#d4952a');
    setCssVar('warning', '#d4952a');
    document.body.style.setProperty('--q-card-head', '#1e1e22');
  } else {
    setCssVar('primary', '#1a6b4a');
    setCssVar('secondary', '#e8a525');
    setCssVar('warning', '#e8a525');
    document.body.style.setProperty('--q-card-head', '#f4f6f5');
  }
}

export default {
  $compresso,
  getCompressoVersion() {
    return new Promise((resolve, reject) => {
      if (typeof $compresso.version === 'undefined') {
        axios({
          method: 'get',
          url: getCompressoApiUrl('v2', 'version/read')
        }).then((response) => {
          $compresso.version = response.data.version;
          resolve($compresso.version)
        })
      } else {
        resolve($compresso.version);
      }
    })
  },
  getCompressoSession(options = {}) {
    return new Promise((resolve, reject) => {
      let cacheKey = 'session';
      if (options.skipProxy) {
        cacheKey = 'localSession';
      }

      if (typeof $compresso[cacheKey] === 'undefined') {
        axios({
          method: 'get',
          url: getCompressoApiUrl('v2', 'session/state'),
          ...options
        }).then((response) => {
          $compresso[cacheKey] = {
            created: response.data.created,
            email: response.data.email,
            level: response.data.level,
            name: response.data.name,
            picture_uri: response.data.picture_uri,
            uuid: response.data.uuid,
          }
          resolve($compresso[cacheKey])
        }).catch(() => {
          reject()
        })
      } else {
        resolve($compresso[cacheKey]);
      }
    })
  },
  getCompressoPrivacyPolicy() {
    return new Promise((resolve, reject) => {
      $compresso.docs = (typeof $compresso.docs === 'undefined') ? {} : $compresso.docs
      if (typeof $compresso.docs.privacypolicy === 'undefined') {
        axios({
          method: 'get',
          url: getCompressoApiUrl('v2', 'docs/privacypolicy')
        }).then((response) => {
          $compresso.docs.privacypolicy = response.data.content.join('')
          resolve($compresso.docs.privacypolicy)
        }).catch(() => {
          reject()
        })
      } else {
        resolve($compresso.docs.privacypolicy);
      }
    })
  },
  getCompressoNotifications() {
    if (typeof $compresso.notificationsList === 'undefined') {
      $compresso.notificationsList = [];
    }
    return $compresso.notificationsList;
  },
  updateCompressoNotifications($t) {
    return new Promise((resolve, reject) => {
      $compresso.notificationsList = (typeof $compresso.notificationsList === 'undefined') ? [] : $compresso.notificationsList
      axios({
        method: 'get',
        url: getCompressoApiUrl('v2', 'notifications/read'),
      }).then((response) => {
        // Update success
        let notifications = []
        for (let i = 0; i < response.data.notifications.length; i++) {
          let notification = response.data.notifications[i];
          // Fetch label string from i18n
          let labelStringId = 'notifications.serverNotificationLabels.' + notification.label
          let labelString = $t(labelStringId)
          // If i18n doesn't have this string ID, then revert to just displaying the provided label
          if (labelString === labelStringId) {
            labelString = notification.label;
          }
          // Fetch message string from i18n
          let messageStringId = 'notifications.serverNotificationLabels.' + notification.message
          let messageString = $t(messageStringId)
          // If i18n doesn't have this string ID, then revert to just displaying the provided label
          if (messageString === messageStringId) {
            messageString = notification.message;
          }
          // Set the color of the notification
          let color = 'info';
          if (notification.type === 'error') {
            color = 'negative';
          } else if (notification.type === 'warning') {
            color = 'warning';
          } else if (notification.type === 'success') {
            color = 'positive';
          }
          // Add notification to list
          notifications[notifications.length] = {
            uuid: notification.uuid,
            icon: notification.icon,
            navigation: notification.navigation,
            label: labelString,
            message: messageString,
            color: color,
          }
        }
        $compresso.notificationsList = notifications;
        resolve($compresso.notificationsList)
      }).catch(() => {
        console.error("Failed to retrieve server notifications")
        resolve($compresso.notificationsList)
      });
    })
  },
  dismissNotifications($t, uuidList) {
    let queryData = {
      uuid_list: uuidList
    }
    return new Promise((resolve, reject) => {
      $compresso.notificationsList = (typeof $compresso.notificationsList === 'undefined') ? [] : $compresso.notificationsList
      axios({
        method: 'delete',
        url: getCompressoApiUrl('v2', 'notifications/remove'),
        data: queryData,
      }).then((response) => {
        resolve()
      }).catch(() => {
        console.error("Failed to dismiss server notifications")
        resolve()
      });
    })
  },
}
