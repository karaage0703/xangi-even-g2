import assert from 'node:assert/strict'
import test from 'node:test'
import { clickGuardDeadline, shouldIgnoreSingleClick } from '../src/click-guard.ts'

test('ignores a trailing click after a candidate send returns to ready', () => {
  const ignoreUntil = clickGuardDeadline(1_000, 700)

  assert.equal(shouldIgnoreSingleClick(1_100, ignoreUntil), true)
  assert.equal(shouldIgnoreSingleClick(1_699, ignoreUntil), true)
  assert.equal(shouldIgnoreSingleClick(1_700, ignoreUntil), false)
})
