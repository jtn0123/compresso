import type { ApiSchema } from './contracts'

export interface MetadataPath {
  path: string
  path_type: string
}

export interface MetadataEntryView extends Omit<ApiSchema<'MetadataEntry'>, 'paths'> {
  paths: MetadataPath[]
}

export function normalizeMetadataEntry(entry: ApiSchema<'MetadataEntry'>): MetadataEntryView {
  const paths = (entry.paths ?? []).flatMap((value) => {
    const path = typeof value.path === 'string' ? value.path : null
    if (!path) return []
    return [{
      path,
      path_type: typeof value.path_type === 'string' ? value.path_type : 'path',
    }]
  })
  return { ...entry, paths }
}
