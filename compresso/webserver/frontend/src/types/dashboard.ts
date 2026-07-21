import type { LiveGpuMetrics, LiveSystemMetricsMessage } from './contracts'
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
  | { success: true; server_id: string; type: 'workers_info'; data: WorkerInfoMessage[] }
  | { success: true; server_id: string; type: 'pending_tasks'; data: PendingTasksMessage }
  | { success: true; server_id: string; type: 'completed_tasks'; data: CompletedTasksMessage }
  | { success: true; server_id: string; type: 'system_status'; data: LiveSystemMetricsMessage }

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function optionalString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

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
    start_time: typeof value.start_time === 'number' ? value.start_time : null,
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
  return result
}

export function parseDashboardEnvelope(raw: string): DashboardEnvelope | null {
  let value: unknown
  try {
    value = JSON.parse(raw) as unknown
  } catch {
    return null
  }
  if (!isRecord(value)) return null
  if (value.success === false) return { success: false }
  if (value.success !== true || typeof value.server_id !== 'string' || typeof value.type !== 'string') return null
  if (value.type === 'workers_info' && Array.isArray(value.data)) {
    const workers = value.data.map(parseWorker)
    if (!workers.some((worker) => worker === null)) {
      return {
        success: true,
        server_id: value.server_id,
        type: value.type,
        data: workers.filter((worker): worker is WorkerInfoMessage => worker !== null),
      }
    }
  }
  if (value.type === 'pending_tasks') {
    const data = parsePendingTasks(value.data)
    if (data) return { success: true, server_id: value.server_id, type: value.type, data }
  }
  if (value.type === 'completed_tasks') {
    const data = parseCompletedTasks(value.data)
    if (data) return { success: true, server_id: value.server_id, type: value.type, data }
  }
  if (value.type === 'system_status') {
    const data = parseSystemMetrics(value.data)
    if (data) return { success: true, server_id: value.server_id, type: value.type, data }
  }
  return null
}
