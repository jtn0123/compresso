import type { components } from './generated/api'

export type ApiSchema<Name extends keyof components['schemas']> = components['schemas'][Name]
export type SystemStatus = ApiSchema<'SystemStatusSuccess'>
export type SystemGpu = ApiSchema<'SystemStatusGpu'>

export interface LiveGpuMetrics extends Partial<SystemGpu> {
  index: number
  name: string
  utilization_percent?: number
  memory_used_mb?: number
  temperature_c?: number | null
}

export interface GpuHistoryPoint {
  timestamp: number
  gpu_name?: string
  utilization_percent?: number | null
  memory_used_mb?: number
  memory_total_mb?: number
  temperature_c?: number | null
}

export type GpuHistory = Record<string, GpuHistoryPoint[]>

export interface LiveSystemMetrics {
  cpu_percent: number
  memory_percent: number
  memory_used_gb: number
  disk_percent: number
  disk_used_gb: number
  gpus: LiveGpuMetrics[]
}

export interface LiveSystemMetricsMessage extends Partial<LiveSystemMetrics> {
  gpu_history?: GpuHistory
}

export interface RemoteInstallationLink {
  uuid: string
  name: string
  address?: string
  available: boolean
}
