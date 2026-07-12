import { spawn, spawnSync } from 'node:child_process'
import { existsSync, mkdirSync, readdirSync, rmSync, unlinkSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const repositoryRoot = path.resolve(scriptDir, '..', '..', '..', '..')
const homeDir = process.env.LIVE_E2E_HOME_DIR || path.join(tmpdir(), `compresso-live-e2e-${process.pid}`)
const bootstrapPython = process.env.PYTHON_BIN || 'python3.13'
const host = process.env.BACKEND_HOST || '127.0.0.1'
const port = process.env.BACKEND_PORT || '8920'
const restartRequestPath = path.join(homeDir, 'restart-requested')
const pidPath = path.join(homeDir, 'backend.pid')
const wheelDir = path.join(homeDir, 'wheel')
const venvDir = path.join(homeDir, 'venv')

function runChecked(command, args, options = {}) {
  const result = spawnSync(command, args, { stdio: 'inherit', ...options })
  if (result.status !== 0) {
    throw new Error(`${command} ${args.join(' ')} failed with exit code ${result.status}`)
  }
}

rmSync(homeDir, { recursive: true, force: true })
mkdirSync(homeDir, { recursive: true })
for (const directory of ['cache', 'staging', 'library', 'wheel']) {
  mkdirSync(path.join(homeDir, directory), { recursive: true })
}

runChecked(bootstrapPython, ['-m', 'build', '--wheel', '--outdir', wheelDir], { cwd: repositoryRoot })
runChecked(bootstrapPython, ['-m', 'venv', '--system-site-packages', venvDir])
const packagedPython = path.join(venvDir, process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')
const wheel = readdirSync(wheelDir).find((name) => name.endsWith('.whl'))
if (!wheel) throw new Error('Wheel build completed without producing a wheel')
runChecked(packagedPython, ['-m', 'pip', 'install', '--no-deps', path.join(wheelDir, wheel)], { cwd: homeDir })

const backendEnv = {
  ...process.env,
  HOME_DIR: homeDir,
  cache_path: path.join(homeDir, 'cache'),
  staging_path: path.join(homeDir, 'staging'),
  library_path: path.join(homeDir, 'library'),
  approval_required: 'true',
  onboarding_completed: 'true',
}
delete backendEnv.PYTHONPATH

runChecked(packagedPython, [path.join(scriptDir, 'seed-live-backend.py')], { cwd: homeDir, env: backendEnv })

let child = null
let stopping = false
let restarting = false

function startBackend() {
  child = spawn(packagedPython, ['-m', 'compresso', '--address', host, '--port', port], {
    cwd: homeDir,
    env: backendEnv,
    stdio: 'inherit',
  })
  writeFileSync(pidPath, String(child.pid))

  child.on('error', (error) => {
    console.error(`Unable to start packaged Compresso backend: ${error.message}`)
    stop('SIGTERM', 1)
  })
  child.on('exit', (code, signal) => {
    if (restarting && !stopping) {
      restarting = false
      startBackend()
      return
    }
    cleanup()
    if (signal && stopping) process.exit(0)
    process.exit(code ?? 1)
  })
}

function cleanup() {
  rmSync(homeDir, { recursive: true, force: true })
}

function stop(signal, exitCode = 0) {
  if (stopping) return
  stopping = true
  process.exitCode = exitCode
  if (child) child.kill(signal)
}

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => stop(signal))
}

setInterval(() => {
  if (!stopping && !restarting && existsSync(restartRequestPath)) {
    unlinkSync(restartRequestPath)
    restarting = true
    child.kill('SIGTERM')
  }
}, 200)

startBackend()
