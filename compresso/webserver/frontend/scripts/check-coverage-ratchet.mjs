#!/usr/bin/env node
// Coverage auto-ratchet: fail when achieved coverage exceeds a configured
// floor by more than the allowed slack, so the floors in
// coverage-thresholds.json must be raised as tests are added. Vitest itself
// enforces the floors as minimums; this script enforces them as *current*.
//
// Run after `npx vitest run --coverage` (needs the json-summary reporter).

import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const frontendRoot = join(dirname(fileURLToPath(import.meta.url)), '..')
const thresholdsPath = join(frontendRoot, 'coverage-thresholds.json')
const summaryPath = join(frontendRoot, 'coverage', 'coverage-summary.json')

const thresholds = JSON.parse(readFileSync(thresholdsPath, 'utf8'))
let summary
try {
  summary = JSON.parse(readFileSync(summaryPath, 'utf8'))
} catch (error) {
  console.error(`Unable to read ${summaryPath} - run "npx vitest run --coverage" first (${error.message})`)
  process.exit(1)
}

const totals = summary.total
const slack = Number(thresholds.ratchetSlackPoints ?? 2)
const metrics = ['lines', 'functions', 'branches', 'statements']
const failures = []

for (const metric of metrics) {
  const floor = Number(thresholds[metric])
  const achieved = Number(totals?.[metric]?.pct)
  if (!Number.isFinite(floor) || !Number.isFinite(achieved)) {
    console.error(`Missing ${metric} in thresholds or coverage summary`)
    process.exit(1)
  }
  if (achieved > floor + slack) {
    failures.push(
      `${metric}: achieved ${achieved}% exceeds the ${floor}% floor by more than ${slack} points - ` +
        `raise "${metric}" in coverage-thresholds.json to ${Math.floor(achieved)}`,
    )
  }
}

if (failures.length > 0) {
  console.error('Coverage ratchet check failed:')
  for (const failure of failures) console.error(`  - ${failure}`)
  console.error('Raising the floor locks in the new coverage so it cannot silently regress.')
  process.exit(1)
}

console.log(`Coverage ratchet OK (floors within ${slack} points of achieved coverage).`)
