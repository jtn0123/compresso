export interface ComparisonCandidate {
  id?: number
  candidate_uuid: string
  profile_key: string
  profile_label: string
  encoder: string
  codec: string
  status: string
  progress: number
  output_url?: string
  output_size?: number
  size_saved_percent?: number
  vmaf_score?: number | null
  ssim_score?: number | null
  error?: string | null
}

export interface ComparisonBatch {
  status: string
  progress: number
  candidates: ComparisonCandidate[]
  source_path?: string
  winner_candidate_id?: number | null
  full_encode_task_id?: number | null
  error?: string | null
}

export interface ComparisonProfile {
  key: string
  label: string
  description: string
  encoder: string
  codec: string
  hardware: boolean
  available: boolean
}

export interface MediaEntry {
  name: string
  full_path: string
}

export interface LibraryOption {
  label: string
  value: number
  path: string
}
