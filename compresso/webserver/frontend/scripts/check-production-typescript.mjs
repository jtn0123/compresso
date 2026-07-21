import { readdir } from 'node:fs/promises'
import { extname, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const frontendRoot = resolve(fileURLToPath(new URL('..', import.meta.url)))
const sourceRoot = resolve(frontendRoot, 'src')

async function findProductionJavaScript(directory) {
  const entries = await readdir(directory, { withFileTypes: true })
  const matches = []

  for (const entry of entries) {
    const path = resolve(directory, entry.name)
    if (entry.isDirectory()) {
      if (entry.name !== '__tests__') {
        matches.push(...(await findProductionJavaScript(path)))
      }
      continue
    }
    if (extname(entry.name) === '.js' && !entry.name.endsWith('.test.js') && !entry.name.endsWith('.spec.js')) {
      matches.push(relative(frontendRoot, path))
    }
  }

  return matches
}

const productionJavaScript = await findProductionJavaScript(sourceRoot)
if (productionJavaScript.length > 0) {
  console.error('Production JavaScript remains under src:')
  for (const path of productionJavaScript) {
    console.error(`  - ${path}`)
  }
  process.exitCode = 1
} else {
  console.log('Production frontend source is fully TypeScript.')
}
