import type { AxiosInstance } from 'axios'

interface GlobalEventBus {
  $on<Args extends unknown[]>(event: string, callback: (...args: Args) => void): void
  $once<Args extends unknown[]>(event: string, callback: (...args: Args) => void): void
  $off<Args extends unknown[]>(event: string, callback?: (...args: Args) => void): void
  $emit<Args extends unknown[]>(event: string, ...args: Args): void
}

declare module 'vue' {
  interface ComponentCustomProperties {
    $api: AxiosInstance
    $axios: AxiosInstance
    $global: GlobalEventBus
  }
}

declare module 'axios' {
  interface AxiosRequestConfig {
    skipProxy?: boolean
    __compressoAuthRetried?: boolean
  }

  interface InternalAxiosRequestConfig {
    skipProxy?: boolean
    __compressoAuthRetried?: boolean
  }
}

export {}
