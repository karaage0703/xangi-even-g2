import assert from 'node:assert/strict'
import test from 'node:test'
import { completeReply, type ReplyCompletionEffects } from '../src/reply-completion.ts'

function createEffects(
  overrides: Partial<ReplyCompletionEffects> = {},
): ReplyCompletionEffects & {
  state: {
    shown: string[]
    renders: number
    refreshes: number
    syncErrors: unknown[]
  }
} {
  const state = {
    shown: [] as string[],
    renders: 0,
    refreshes: 0,
    syncErrors: [] as unknown[],
  }
  return {
    state,
    isCurrentSession: () => true,
    showReply: content => state.shown.push(content),
    syncHistory: async () => true,
    renderSyncedHistory: () => {
      state.renders += 1
    },
    refreshCandidates: async () => {
      state.refreshes += 1
    },
    onSyncError: error => state.syncErrors.push(error),
    ...overrides,
  }
}

test('shows a completed reply before history synchronization finishes', async () => {
  let finishSync: ((value: boolean) => void) | undefined
  const effects = createEffects({
    syncHistory: () =>
      new Promise<boolean>(resolve => {
        finishSync = resolve
      }),
  })

  const completion = completeReply('回答です', effects)
  assert.deepEqual(effects.state.shown, ['回答です'])

  finishSync?.(true)
  await completion
  assert.equal(effects.state.renders, 1)
})

test('keeps the displayed reply when history synchronization fails', async () => {
  const failure = new Error('history unavailable')
  const effects = createEffects({
    syncHistory: async () => {
      throw failure
    },
  })

  assert.equal(await completeReply('回答です', effects), true)
  assert.deepEqual(effects.state.shown, ['回答です'])
  assert.deepEqual(effects.state.syncErrors, [failure])
  assert.equal(effects.state.renders, 0)
})

test('does not overwrite the screen after moving to another session', async () => {
  const effects = createEffects({ isCurrentSession: () => false })

  assert.equal(await completeReply('別セッションの回答', effects), false)
  assert.deepEqual(effects.state.shown, [])
  assert.equal(effects.state.renders, 0)
  assert.equal(effects.state.refreshes, 0)
})

test('replaces the optimistic reply with synchronized history without duplication', async () => {
  let messages: string[] = []
  const effects = createEffects({
    showReply: content => {
      messages.push(content)
    },
    syncHistory: async () => {
      messages = ['回答です']
      return true
    },
  })

  await completeReply('回答です', effects)
  assert.deepEqual(messages, ['回答です'])
  assert.equal(effects.state.renders, 1)
  assert.equal(effects.state.refreshes, 1)
})
