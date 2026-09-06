import type { ApiSchema } from './contracts'

export type ComparisonCandidate = ApiSchema<'ComparisonCandidate'>
export type ComparisonBatch = ApiSchema<'ComparisonStatusResponse'>
export type ComparisonProfile = ApiSchema<'ComparisonProfile'>

// Queued UI placeholders intentionally omit fields not returned by the API yet.
export type ComparisonCandidateView = Partial<ComparisonCandidate> &
  Pick<
    ComparisonCandidate,
    'candidate_uuid' | 'profile_key' | 'profile_label' | 'encoder' | 'codec' | 'status' | 'progress'
  >
export type ComparisonBatchView = Partial<Omit<ComparisonBatch, 'candidates'>> &
  Pick<ComparisonBatch, 'status' | 'progress'> & { candidates: ComparisonCandidateView[] }

export interface MediaEntry {
  name: string
  full_path: string
}

export interface LibraryOption {
  label: string
  value: number
  path: string
}
