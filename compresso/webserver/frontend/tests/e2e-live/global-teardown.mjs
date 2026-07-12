import { rmSync } from 'node:fs'

export default function globalTeardown() {
  if (process.env.LIVE_E2E_HOME_DIR) {
    rmSync(process.env.LIVE_E2E_HOME_DIR, { recursive: true, force: true })
  }
}
