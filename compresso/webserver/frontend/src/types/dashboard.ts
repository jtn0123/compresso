import type { GpuHistory, GpuHistoryPoint, LiveGpuMetrics, LiveSystemMetricsMessage } from './contracts'
import { parseFiniteNumber } from 'src/js/formatUtils'
import { isRecord, KNOWN_STREAM_TYPES, type RawEnvelope } from './envelope'
import type { WorkerInfoMessage, WorkerRunnerInfo, WorkerSubprocessInfo } from './workers'

export interface PendingTaskMessage {
  id: number
  priority: number
  label: string
  status: string
}

export interface PendingTasksMessage {
  results: PendingTaskMessage[]
  queue_eta?: {
    eta_seconds: number
    confidence?: 'high' | 'medium' | 'low'
  }
}

export interface CompletedTaskMessage {
  id: number
  label: string
  finish_time: number
  human_readable_time: string
  success: boolean
}

export interface CompletedTasksMessage {
  results: CompletedTaskMessage[]
}

export interface PendingTaskSummary {
  id: number
  priority: number
  label: string
  status: string
}

export interface CompletedTaskSummary {
  id: number
  label: string
  dateTimeCompleted: string
  dateTimeSinceCompleted: string
  success: boolean
}

export interface QueueEta {
  formatted: string | null
  seconds: number
  confidence: 'high' | 'medium' | 'low'
}

export type DashboardEnvelope =
  | { success: false }
  | { success: true; server_id: string; type: 'unhandled' }
  | { success: true; server_id: string; type: 'workers_info'; data: WorkerInfoMessage[] }
  | { success: true; server_id: string; type: 'pending_tasks'; data: PendingTasksMessage }
  | { success: true; server_id: string; type: 'completed_tasks'; data: CompletedTasksMessage }
  | { success: true; server_id: string; type: 'system_status'; data: LiveSystemMetricsMessage }

function optionalString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

// The backend serializes worker start times as strings (str(time.time()))
const optionalTimestamp = parseFiniteNumber

function parseRunnerInfo(value: unknown): Record<string, WorkerRunnerInfo> {
  if (!isRecord(value)) return {}
  const result: Record<string, WorkerRunnerInfo> = {}
  for (const [key, runner] of Object.entries(value)) {
    if (!isRecord(runner)) continue
    const parsed: WorkerRunnerInfo = {}
    if (typeof runner.status === 'string') parsed.status = runner.status
    if (typeof runner.name === 'string') parsed.name = runner.name
    result[key] = parsed
  }
  return result
}

function parseSubprocess(value: unknown): WorkerSubprocessInfo {
  if (!isRecord(value)) return {}
  const result: WorkerSubprocessInfo = {}
  const keys = [
    'percent',
    'elapsed',
    'eta_seconds',
    'encoding_fps',
    'encoding_speed',
    'cpu_percent',
    'mem_percent',
  ] as const
  for (const key of keys) {
    const entry = value[key]
    if (typeof entry === 'string' || typeof entry === 'number') result[key] = entry
  }
  return result
}

function parseWorker(value: unknown): WorkerInfoMessage | null {
  if (
    !isRecord(value) ||
    (typeof value.id !== 'string' && typeof value.id !== 'number') ||
    typeof value.name !== 'string' ||
    typeof value.idle !== 'boolean' ||
    typeof value.paused !== 'boolean'
  ) {
    return null
  }
  return {
    id: value.id,
    name: value.name,
    idle: value.idle,
    paused: value.paused,
    worker_type: optionalString(value.worker_type),
    workerType: optionalString(value.workerType),
    current_file: optionalString(value.current_file),
    current_task: typeof value.current_task === 'number' ? value.current_task : null,
    runners_info: parseRunnerInfo(value.runners_info),
    subprocess: parseSubprocess(value.subprocess),
    start_time: optionalTimestamp(value.start_time),
    current_command: optionalString(value.current_command),
    worker_log_tail: Array.isArray(value.worker_log_tail)
      ? value.worker_log_tail.filter((line): line is string => typeof line === 'string')
      : [],
  }
}

function parsePendingTask(value: unknown): PendingTaskMessage | null {
  if (
    !isRecord(value) ||
    typeof value.id !== 'number' ||
    typeof value.priority !== 'number' ||
    typeof value.label !== 'string' ||
    typeof value.status !== 'string'
  )
    return null
  return { id: value.id, priority: value.priority, label: value.label, status: value.status }
}

function parsePendingTasks(value: unknown): PendingTasksMessage | null {
  if (!isRecord(value) || !Array.isArray(value.results)) return null
  const results = value.results.map(parsePendingTask)
  if (results.some((entry) => entry === null)) return null
  const parsed: PendingTasksMessage = {
    results: results.filter((entry): entry is PendingTaskMessage => entry !== null),
  }
  if (isRecord(value.queue_eta) && typeof value.queue_eta.eta_seconds === 'number') {
    const confidence = value.queue_eta.confidence
    parsed.queue_eta = {
      eta_seconds: value.queue_eta.eta_seconds,
      ...(confidence === 'high' || confidence === 'medium' || confidence === 'low' ? { confidence } : {}),
    }
  }
  return parsed
}

function parseCompletedTask(value: unknown): CompletedTaskMessage | null {
  if (
    !isRecord(value) ||
    typeof value.id !== 'number' ||
    typeof value.label !== 'string' ||
    typeof value.finish_time !== 'number' ||
    typeof value.human_readable_time !== 'string' ||
    typeof value.success !== 'boolean'
  )
    return null
  return {
    id: value.id,
    label: value.label,
    finish_time: value.finish_time,
    human_readable_time: value.human_readable_time,
    success: value.success,
  }
}

function parseCompletedTasks(value: unknown): CompletedTasksMessage | null {
  if (!isRecord(value) || !Array.isArray(value.results)) return null
  const results = value.results.map(parseCompletedTask)
  if (results.some((entry) => entry === null)) return null
  return { results: results.filter((entry): entry is CompletedTaskMessage => entry !== null) }
}

function parseGpu(value: unknown): LiveGpuMetrics | null {
  if (!isRecord(value) || typeof value.index !== 'number' || typeof value.name !== 'string') return null
  const gpu: LiveGpuMetrics = { index: value.index, name: value.name }
  if (typeof value.utilization_percent === 'number') gpu.utilization_percent = value.utilization_percent
  if (typeof value.memory_used_mb === 'number') gpu.memory_used_mb = value.memory_used_mb
  if (typeof value.memory_total_mb === 'number') gpu.memory_total_mb = value.memory_total_mb
  if (typeof value.temperature_c === 'number' || value.temperature_c === null) gpu.temperature_c = value.temperature_c
  return gpu
}

function parseGpuHistoryPoint(value: unknown): GpuHistoryPoint | null {
  if (!isRecord(value) || typeof value.timestamp !== 'number') return null
  const point: GpuHistoryPoint = { timestamp: value.timestamp }
  if (typeof value.gpu_name === 'string') point.gpu_name = value.gpu_name
  if (typeof value.utilization_percent === 'number' || value.utilization_percent === null) {
    point.utilization_percent = value.utilization_percent
  }
  if (typeof value.memory_used_mb === 'number') point.memory_used_mb = value.memory_used_mb
  if (typeof value.memory_total_mb === 'number') point.memory_total_mb = value.memory_total_mb
  if (typeof value.temperature_c === 'number' || value.temperature_c === null) {
    point.temperature_c = value.temperature_c
  }
  return point
}

function parseGpuHistory(value: unknown): GpuHistory | null {
  if (!isRecord(value)) return null
  const history: GpuHistory = {}
  for (const [gpuIndex, samples] of Object.entries(value)) {
    if (!Array.isArray(samples)) return null
    const parsedSamples = samples.map(parseGpuHistoryPoint)
    if (parsedSamples.some((sample) => sample === null)) return null
    history[gpuIndex] = parsedSamples.filter((sample): sample is GpuHistoryPoint => sample !== null)
  }
  return history
}

function parseSystemMetrics(value: unknown): LiveSystemMetricsMessage | null {
  if (!isRecord(value)) return null
  const result: LiveSystemMetricsMessage = {}
  const numberKeys = ['cpu_percent', 'memory_percent', 'memory_used_gb', 'disk_percent', 'disk_used_gb'] as const
  for (const key of numberKeys) {
    if (typeof value[key] === 'number') result[key] = value[key]
  }
  if (Array.isArray(value.gpus)) {
    const gpus = value.gpus.map(parseGpu)
    if (gpus.some((gpu) => gpu === null)) return null
    result.gpus = gpus.filter((gpu): gpu is LiveGpuMetrics => gpu !== null)
  }
  if (value.gpu_history !== undefined && value.gpu_history !== null) {
    const gpuHistory = parseGpuHistory(value.gpu_history)
    if (gpuHistory === null) return null
    result.gpu_history = gpuHistory
  }
  return result
}

export function parseDashboardEnvelope(envelope: RawEnvelope): DashboardEnvelope | null {
  if (!envelope.success) return envelope
  const serverId = envelope.server_id
  switch (envelope.type) {
    case 'workers_info': {
      if (!Array.isArray(envelope.data)) return null
      const workers = envelope.data.map(parseWorker)
      if (workers.some((worker) => worker === null)) return null
      return {
        success: true,
        server_id: serverId,
        type: 'workers_info',
        data: workers.filter((worker): worker is WorkerInfoMessage => worker !== null),
      }
    }
    case 'pending_tasks': {
      const data = parsePendingTasks(envelope.data)
      return data ? { success: true, server_id: serverId, type: 'pending_tasks', data } : null
    }
    case 'completed_tasks': {
      const data = parseCompletedTasks(envelope.data)
      return data ? { success: true, server_id: serverId, type: 'completed_tasks', data } : null
    }
    case 'system_status': {
      const data = parseSystemMetrics(envelope.data)
      return data ? { success: true, server_id: serverId, type: 'system_status', data } : null
    }
  }
  // Valid envelope of a stream this page does not model: pass through so the
  // server_id restart check still sees it and no error is logged.
  return KNOWN_STREAM_TYPES.has(envelope.type) ? { success: true, server_id: serverId, type: 'unhandled' } : null
}
