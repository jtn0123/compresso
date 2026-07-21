import type { ApiSchema } from './contracts'

export type WorkerGroupConfig = ApiSchema<'SettingsWorkerGroupConfig'>
export type WorkerEventSchedule = ApiSchema<'WorkerEventScheduleResults'>

export interface WorkerScheduleEvent {
  repetition: string
  scheduleTime: string
  scheduleTask: string
  scheduleWorkerCount: number
}

export interface WorkerScheduleDisplay extends WorkerScheduleEvent {
  repetitionLabel: string
  scheduleTaskLabel: string
}

export interface WorkerGroupListItem {
  id: number
  name: string
  workerType: 'cpu' | 'gpu'
  workerCount: number
  tags: string[]
  locked: boolean
}

export interface WorkerRunnerInfo {
  status?: string
  name?: string
}

export interface WorkerSubprocessInfo {
  percent?: string | number
  elapsed?: string | number
  eta_seconds?: string | number
  encoding_fps?: string | number
  encoding_speed?: string | number
  cpu_percent?: string | number
  mem_percent?: string | number
  [key: string]: unknown
}

export interface WorkerInfoMessage {
  id: string | number
  name: string
  idle: boolean
  paused: boolean
  worker_type: string
  workerType: string
  current_file: string
  current_task: number | null
  runners_info: Record<string, WorkerRunnerInfo>
  subprocess: WorkerSubprocessInfo
  start_time: number | null
  current_command: string
  worker_log_tail: string[]
}

export interface WorkerProgressEntry {
  id: string
  label: string
  name: string
  progress: number
  progressText: string
  elapsed: string
  etc: string
  color: string
  workerGroupColour: string
  state: string
  currentRunner: string
  startTime: string
  timeSinceStart: string
  indeterminate: boolean
  currentCommand: string
  currentFile: string
  currentTask: number | null
  runnersInfo: Record<string, WorkerRunnerInfo>
  subprocess: WorkerSubprocessInfo
  workerLog: string[]
  idle: boolean
  paused: boolean
  workerType: string
  encodingFps: string | null
  encodingSpeed: string | null
}

export interface WorkerGroupView {
  name: string
  active: number
  idle: number
  paused: number
  color: string
  workerType: string
  workerCount: number | null
  groupId: number | null
  saving: boolean
  workers: WorkerProgressEntry[]
}

export type WorkerDetailsProps = Omit<WorkerProgressEntry, 'workerType' | 'encodingFps' | 'encodingSpeed'>

export interface DetectedGpu {
  name: string
  memory_total_mb?: number
}
