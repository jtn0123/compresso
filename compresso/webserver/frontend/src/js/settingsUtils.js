/**
 * Check if the cache path has been modified from its original value.
 *
 * @param {string|null} originalCachePath - The cache path when last fetched from server
 * @param {string|null} cachePath - The current cache path value
 * @returns {boolean} True if there are unsaved changes
 */
export function checkUnsavedChanges(originalCachePath, cachePath) {
  return originalCachePath !== null && cachePath !== originalCachePath
}
