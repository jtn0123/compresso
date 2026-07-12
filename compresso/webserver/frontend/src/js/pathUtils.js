export function displayBasename(path) {
  if (!path) return ''
  return String(path).split(/[\\/]/).pop()
}
