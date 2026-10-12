import assert from 'node:assert/strict'
import test from 'node:test'
import fs from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
import { completeReply } from '../src/reply-completion.ts'

// Execute the actual application handlers with device/network effects replaced.
const source = fs.readFileSync(new URL('../src/main.ts', import.meta.url), 'utf8')
const ast = ts.createSourceFile('main.ts', source, ts.ScriptTarget.Latest, true)
const names = new Set(['openSelectedSession', 'sendTextToTerminal', 'toReady', 'connectEvents', 'submit', 'startReplyPolling', 'isCurrentTerminalSession'])
const handlers: string[] = []
function visit(node: ts.Node) {
  if (ts.isFunctionDeclaration(node) && node.name && names.has(node.name.text)) handlers.push(node.getText(ast))
  ts.forEachChild(node, visit)
}
visit(ast)
const code = ts.transpileModule(handlers.join('\n'), { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText
function setup() {
  const renders: string[] = []
  const posts: string[] = []
  let creates = 0
  const polls = new Map<number, () => Promise<void>>()
  const replies: string[] = []
  let nextTimer = 0
  const ctx = vm.createContext({
    completeReply, console, replyPolls: new Map(),
    window: { setInterval: (fn: () => Promise<void>) => { polls.set(++nextTimer, fn); return nextTimer }, clearInterval: (id: number) => polls.delete(id) },
    getTerminalReply: async () => ({ status: 'done', reply: { content: 'answer' } }),
    syncCurrentTerminalHistory: async () => false,
    state: 'ready', viewMode: 'sessions', terminalSession: null, terminalSummary: null,
    pendingQuestion: '', pendingQuestionPageIndex: 0, recordingMode: null,
    audioStartPromise: null, bufLen: 2, replyCandidates: [], eventSource: null,
    historyMessages: [], historyIndex: -1, historyStart: 0, historyEnd: 0, historyTotal: 0,
    currentSession: () => ({ id: '__new__', title: '+ New Session', platform: 'web' }),
    stopSessionRefresh() {}, stopListeningAnimation() {}, setStatus() {}, scheduleAutoHide() {}, flushRender() {},
    render: (text: string) => renders.push(text), renderTerminalIdle: () => renders.push('idle'),
    bridge: { audioControl: async () => true },
    createTerminalSession: async () => { creates++; return { session_id: 'saved', thread_id: 'web:saved' } },
    openTerminalSession: async (id: string) => ({ session_id: id, thread_id: `web:${id}` }),
    loadTerminalHistory: async () => {}, refreshReplyCandidates: async () => {},
    terminalEventsUrl: () => 'events',
    EventSource: class { onmessage: unknown; onerror: unknown; addEventListener() {} close() {} },
    appendLatestHistory() {}, addAssistantHistory: (text: string) => replies.push(text), renderLiveAssistantText() {},
    postTerminalSessionMessage: async (id: string) => { posts.push(id); return {} },
    drainBuffer: () => new Uint8Array([1, 2]), transcribe: async () => 'hello', renderConfirming() {},
  })
  vm.runInContext(code, ctx)
  return { ctx, renders, posts, polls, replies, creates: () => creates }
}
const tick = () => new Promise(resolve => setImmediate(resolve))
test('opening New Session and transcribing does not save an empty session', async () => {
  const h = setup()
  await h.ctx.openSelectedSession()
  assert.equal(h.creates(), 0)
  h.ctx.state = 'recording'
  await h.ctx.submit()
  assert.equal(h.ctx.state, 'confirming')
  assert.equal(h.ctx.pendingQuestion, 'hello')
  assert.equal(h.creates(), 0)
  await h.ctx.sendTextToTerminal('hello')
  assert.equal(h.creates(), 1)
  assert.deepEqual(h.posts, ['saved'])
  await h.ctx.sendTextToTerminal('second')
  assert.equal(h.creates(), 1)
})
test('an existing session is reused without creating a session', async () => {
  const h = setup()
  h.ctx.currentSession = () => ({ id: 'existing', title: 'Existing', platform: 'web' })
  await h.ctx.openSelectedSession()
  await h.ctx.sendTextToTerminal('hello')
  assert.equal(h.creates(), 0)
  assert.deepEqual(h.posts, ['existing'])
})
test('completed web reply updates the display without waiting for microphone acknowledgement', async () => {
  const h = setup()
  h.ctx.terminalSession = { session_id: 'existing' }
  h.ctx.viewMode = 'terminal'
  h.ctx.state = 'thinking'
  h.ctx.bridge.audioControl = () => new Promise(() => {})
  h.ctx.connectEvents(h.ctx.terminalSession)
  h.ctx.eventSource.onmessage({ data: JSON.stringify({ type: 'turn.complete', text: 'answer' }) })
  await tick()
  assert.equal(h.ctx.state, 'ready')
  assert.ok(h.renders.includes('idle'))
})
test('late events from a previous session cannot overwrite the current screen', async () => {
  const h = setup()
  h.ctx.terminalSession = { session_id: 'old' }
  h.ctx.viewMode = 'terminal'
  h.ctx.connectEvents(h.ctx.terminalSession)
  const old = h.ctx.eventSource
  h.ctx.terminalSession = { session_id: 'new' }
  old.onmessage({ data: JSON.stringify({ type: 'turn.complete', text: 'old answer' }) })
  await tick()
  assert.deepEqual(h.renders, [])
})
test('empty submission does not persist a draft', async () => {
  const h = setup()
  await h.ctx.openSelectedSession()
  await h.ctx.sendTextToTerminal('  ')
  assert.equal(h.creates(), 0)
  assert.deepEqual(h.posts, [])
})
test('failed session creation can be retried from the same draft', async () => {
  const h = setup()
  await h.ctx.openSelectedSession()
  const create = h.ctx.createTerminalSession
  h.ctx.createTerminalSession = async () => { throw new Error('offline') }
  await h.ctx.sendTextToTerminal('hello')
  assert.equal(h.ctx.state, 'ready')
  assert.equal(h.ctx.terminalSession, null)
  assert.equal(h.ctx.terminalSummary.id, '__new__')
  h.ctx.createTerminalSession = create
  await h.ctx.sendTextToTerminal('retry')
  assert.deepEqual(h.posts, ['saved'])
})

test('Discord send returns to conversation before the reply arrives, then displays the reply', async () => {
  const h = setup()
  h.ctx.currentSession = () => ({ id: 'discord', title: 'Thread', platform: 'discord' })
  h.ctx.postTerminalSessionMessage = async () => ({ reply: 'queued', reply_job_id: 'job' })
  await h.ctx.openSelectedSession()
  h.renders.length = 0
  await h.ctx.sendTextToTerminal('hello')
  assert.equal(h.ctx.state, 'ready')
  assert.equal(h.renders.at(-1), 'idle')
  assert.equal(h.polls.size, 1)
  await [...h.polls.values()][0]()
  await tick()
  assert.deepEqual(h.replies, ['answer'])
  assert.equal(h.renders.at(-1), 'idle')
  assert.equal(h.polls.size, 0)
})
test('Discord completion after navigation leaves the other screen intact', async () => {
  const h = setup()
  h.ctx.terminalSession = { session_id: 'discord' }
  h.ctx.startReplyPolling('job', 'discord')
  h.ctx.terminalSession = { session_id: 'other' }
  await [...h.polls.values()][0]()
  await tick()
  assert.deepEqual(h.replies, [])
  assert.deepEqual(h.renders, [])
})
