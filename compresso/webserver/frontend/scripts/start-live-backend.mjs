import { spawn } from 'node:child_process'
import { mkdirSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const repositoryRoot = path.resolve(scriptDir, '..', '..', '..', '..')
const homeDir = process.env.LIVE_E2E_HOME_DIR || path.join(tmpdir(), `compresso-live-e2e-${process.pid}`)
const pythonBin = process.env.PYTHON_BIN || 'python3.13'
const host = process.env.BACKEND_HOST || '127.0.0.1'
const port = process.env.BACKEND_PORT || '8920'

rmSync(homeDir, { recursive: true, force: true })
mkdirSync(homeDir, { recursive: true })
for (const directory of ['cache', 'staging', 'library']) {
  mkdirSync(path.join(homeDir, directory), { recursive: true })
}

const child = spawn(pythonBin, ['-m', 'compresso', '--address', host, '--port', port], {
  cwd: repositoryRoot,
  env: {
    ...process.env,
    HOME_DIR: homeDir,
    PYTHONPATH: repositoryRoot,
    cache_path: path.join(homeDir, 'cache'),
    staging_path: path.join(homeDir, 'staging'),
    library_path: path.join(homeDir, 'library'),
  },
  stdio: 'inherit',
})

let stopping = false

function cleanup() {
  rmSync(homeDir, { recursive: true, force: true })
}

function stop(signal) {
  if (stopping) return
  stopping = true
  child.kill(signal)
}

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => stop(signal))
}

child.on('error', (error) => {
  console.error(`Unable to start Compresso backend with ${pythonBin}: ${error.message}`)
  cleanup()
  process.exitCode = 1
})

child.on('exit', (code, signal) => {
  cleanup()
  if (signal && stopping) {
    process.exit(0)
  }
  process.exit(code ?? 1)
})
