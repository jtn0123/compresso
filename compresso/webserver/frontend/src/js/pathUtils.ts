export function displayBasename(path: string | null | undefined): string {
  if (!path) return ''
  return String(path).split(/[\\/]/).pop() ?? ''
}
