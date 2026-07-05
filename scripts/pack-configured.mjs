import { mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { spawnSync } from 'node:child_process'
import appManifest from '../app.json' with { type: 'json' }

function argValue(name, fallback) {
  const prefix = `${name}=`
  const args = process.argv.slice(2)
  const match = args.find(arg => arg.startsWith(prefix))
  if (match) return match.slice(prefix.length)
  const index = args.indexOf(name)
  if (index >= 0 && args[index + 1]) return args[index + 1]
  return fallback
}

function run(command, args, env = process.env) {
  const result = spawnSync(command, args, {
    stdio: 'inherit',
    env,
    shell: process.platform === 'win32',
  })
  if (result.status !== 0) process.exit(result.status ?? 1)
}

const bridgeUrl = argValue('--bridge-url', process.env.BRIDGE_URL || process.env.VITE_BRIDGE_URL)
const bridgeToken = argValue('--bridge-token', process.env.BRIDGE_TOKEN || process.env.VITE_BRIDGE_TOKEN || '')
const output = resolve(argValue('--output', process.env.OUTPUT || './xangi-even-g2-configured.ehpk'))

if (!bridgeUrl) {
  console.error('BRIDGE_URL or --bridge-url is required')
  process.exit(1)
}

let parsed
try {
  parsed = new URL(bridgeUrl)
} catch {
  console.error(`Invalid bridge URL: ${bridgeUrl}`)
  process.exit(1)
}

const manifest = structuredClone(appManifest)
for (const permission of manifest.permissions ?? []) {
  if (permission.name !== 'network') continue
  const existing = Array.isArray(permission.whitelist) ? permission.whitelist : []
  permission.whitelist = Array.from(new Set([...existing, parsed.origin]))
}

const tempDir = mkdtempSync(join(tmpdir(), 'xangi-even-g2-pack-'))
const tempManifest = join(tempDir, 'app.configured.json')
writeFileSync(tempManifest, `${JSON.stringify(manifest, null, 2)}\n`)

run('npm', ['run', 'build'], {
  ...process.env,
  VITE_BRIDGE_URL: bridgeUrl,
  VITE_BRIDGE_TOKEN: bridgeToken,
})
run('evenhub', ['pack', tempManifest, './dist', '--output', output])
