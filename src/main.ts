import {
  waitForEvenAppBridge,
  TextContainerProperty,
  CreateStartUpPageContainer,
  TextContainerUpgrade,
  OsEventTypeList,
} from '@evenrealities/even_hub_sdk'
import {
  transcribe,
  bridgeConfigured,
  hydrateBridgeConfig,
  createTerminalSession,
  openTerminalSession,
  listTerminalSessions,
  getTerminalSessionDetail,
  getTerminalReply,
  postTerminalSessionMessage,
  terminalEventsUrl,
  type TerminalSession,
  type TerminalSessionMessage,
  type TerminalSessionSummary,
} from './bridge'
import { mountUi, setStatus, setBody } from './ui'
import { APP_BUILD_LABEL } from './version'
import { G2_DISPLAY_HEIGHT, G2_DISPLAY_WIDTH, paginateText } from './paginate'

function waitForLaunchSource(
  bridge: { onLaunchSource(callback: (source: string) => void): () => void },
  timeoutMs = 800,
): Promise<string> {
  return new Promise(resolve => {
    let done = false
    const unsubscribe = bridge.onLaunchSource(source => {
      if (done) return
      done = true
      unsubscribe()
      resolve(source)
    })
    window.setTimeout(() => {
      if (done) return
      done = true
      unsubscribe()
      resolve('unknown')
    }, timeoutMs)
  })
}

const bridge = await waitForEvenAppBridge()
const launchSource = await waitForLaunchSource(bridge)
await hydrateBridgeConfig(bridge)
mountUi(bridge)

if (launchSource === 'appMenu') {
  setStatus('ready', 'SETTINGS')
  setBody(
    bridgeConfigured()
      ? `${APP_BUILD_LABEL}\n設定済みです。Bridge URL / Token を変更する場合は上のフォームで保存してください。`
      : `${APP_BUILD_LABEL}\nBridge URL と Token を入力して保存してください。保存後、G2 側からアプリを起動します。`,
  )
} else {

const PROMPT = bridgeConfigured()
  ? `${APP_BUILD_LABEL}\nセッション読込中…`
  : `${APP_BUILD_LABEL}\nBridge URL 未設定\niPhone側の画面でURLを入力して保存してください。`
const RECORDING = '録音中… 話してください。\nもう一度タップで送信。'
const AUTO_HIDE_MS = 30_000
const SESSION_REFRESH_MS = 5_000
const VISIBLE_SESSION_COUNT = 4
const TEXT_CONTAINER_PADDING = 4
const TEXT_INNER_WIDTH = G2_DISPLAY_WIDTH - TEXT_CONTAINER_PADDING * 2
const HISTORY_PAGE_BOX = {
  width: TEXT_INNER_WIDTH,
  // The single TextContainer also carries a clock/status line and 2 hint lines.
  // Keep body pages to 7 LVGL lines (7 * 27px) so the composed screen fits 576x288.
  height: Math.min(189, G2_DISPLAY_HEIGHT - TEXT_CONTAINER_PADDING * 2),
  maxPages: 255,
}

if (!bridgeConfigured()) {
  setStatus('error', 'Bridge URL 未設定')
  setBody(`${APP_BUILD_LABEL}\niPhone側の設定フォームに xangi bridge URL と token を入力して保存してください。`)
}

const container = new TextContainerProperty({
  xPosition: 0,
  yPosition: 0,
  width: 576,
  height: 288,
  borderWidth: 0,
  borderColor: 5,
  paddingLength: 4,
  containerID: 1,
  containerName: 'main',
  content: PROMPT,
  isEventCapture: 1,
})

const created = await bridge.createStartUpPageContainer(
  new CreateStartUpPageContainer({ containerTotalNum: 1, textObject: [container] }),
)
if (created !== 0) {
  setStatus('error', `createStartUpPageContainer failed: ${created}`)
  console.error('Failed to create startup page')
}

// ---- メガネ描画 -------------------------------------------------------------
let lastRender = ''
let bodyContent = PROMPT
let pendingContent = ''
let renderTimer: number | null = null
let displayVisible = true
let hideTimer: number | null = null

function clockText(now = new Date()): string {
  return now.toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit' })
}

function stateLabel(): string {
  if (state === 'recording') return 'REC'
  if (state === 'thinking') return 'THINK'
  if (state === 'confirming') return 'CONF'
  return viewMode === 'sessions' ? 'SESS' : 'READY'
}

function composeContent(): string {
  if (!displayVisible) return ' '
  return `${clockText()} ${stateLabel()}\n${bodyContent}`
}

function flushRender() {
  pendingContent = composeContent()
  if (renderTimer !== null) return
  renderTimer = window.setTimeout(async () => {
    renderTimer = null
    if (pendingContent === lastRender) return
    lastRender = pendingContent
    await bridge.textContainerUpgrade(
      new TextContainerUpgrade({
        containerID: 1,
        containerName: 'main',
        content: pendingContent,
      }),
    )
  }, 120)
}

function render(text: string) {
  bodyContent = text
  setBody(text)
  displayVisible = true
  flushRender()
  scheduleAutoHide()
}

function scheduleAutoHide() {
  if (hideTimer !== null) window.clearTimeout(hideTimer)
  if (state !== 'ready') return
  hideTimer = window.setTimeout(() => {
    if (state !== 'ready') return
    displayVisible = false
    flushRender()
  }, AUTO_HIDE_MS)
}

function wakeDisplay(): boolean {
  if (displayVisible) return false
  displayVisible = true
  flushRender()
  scheduleAutoHide()
  return true
}

const clockTimer = window.setInterval(flushRender, 15_000)

// ---- 状態機械（Terminal セッション）----------------------------------------
type State = 'ready' | 'recording' | 'thinking' | 'confirming'
type ViewMode = 'sessions' | 'terminal'

let state: State = 'ready'
let viewMode: ViewMode = 'sessions'
let chunks: Uint8Array[] = []
let bufLen = 0
let sessions: TerminalSessionSummary[] = []
let sessionIndex = 0
let terminalSession: TerminalSession | null = null
let terminalSummary: TerminalSessionSummary | null = null
let eventSource: EventSource | null = null
let sessionRefreshTimer: number | null = null
let historyMessages: TerminalSessionMessage[] = []
let historyIndex = -1
let historyPageIndex = 0
let pendingQuestion = ''
let pendingQuestionPageIndex = 0
const replyPolls = new Map<string, number>()

function appendPcm(chunk: Uint8Array) {
  if (state !== 'recording') return
  chunks.push(chunk)
  bufLen += chunk.length
}

function drainBuffer(): Uint8Array {
  const out = new Uint8Array(bufLen)
  let off = 0
  for (const c of chunks) {
    out.set(c, off)
    off += c.length
  }
  chunks = []
  bufLen = 0
  return out
}

async function toReady() {
  state = 'ready'
  await bridge.audioControl(false)
  setStatus('ready')
  scheduleAutoHide()
  flushRender()
}

function currentSession(): TerminalSessionSummary | null {
  return sessions[sessionIndex] ?? null
}

function formatSessionList(): string {
  if (!sessions.length) return `${APP_BUILD_LABEL}\nセッションなし\nタップ:新規作成`
  const start = Math.max(0, Math.min(sessionIndex - 2, sessions.length - VISIBLE_SESSION_COUNT))
  const visible = sessions.slice(start, start + VISIBLE_SESSION_COUNT)
  const lines = visible.map((s, i) => {
    const actualIndex = start + i
    const text = sessionListText(s)
    const marker = actualIndex === sessionIndex ? '>' : ' '
    const status = s.id === '__new__' ? '+' : s.isActive || s.status === 'busy' ? '*' : ' '
    const platform = platformLabel(s)
    const remaining = s.isActive || s.status === 'busy' ? formatRemaining(s) : ''
    return `${marker}${status}${platform}${remaining ? ` T-${remaining}` : ''} ${text}`
  })
  const selected = currentSession()
  const detail = selected && selected.id !== '__new__' ? sessionDetail(selected) : 'タップ:新規作成'
  return `${APP_BUILD_LABEL} セッション ${sessionIndex + 1}/${sessions.length}\n${lines.join('\n')}\n${detail}\n上下:選択 タップ:開く`
}

function sessionListText(s: TerminalSessionSummary): string {
  const latest = latestMessageLine(s, 28)
  if (latest) return latest
  return s.title.length > 28 ? `${s.title.slice(0, 27)}…` : s.title
}

function sessionDetail(s: TerminalSessionSummary): string {
  const platform = platformName(s)
  const latest = latestMessageLine(s)
  if (s.isActive || s.status === 'busy') {
    const remaining = formatRemaining(s)
    const status = `${platform} 作業中${remaining ? ` 残り${remaining}` : ''}`
    return latest ? `${status}\n${latest}` : status
  }
  if (latest) return latest
  if (s.messageCount) return `${platform} 履歴 ${s.messageCount} 件`
  return `${platform} 待機中`
}

function latestMessageLine(s: TerminalSessionSummary, maxChars = 44): string {
  if (!s.lastMessage) return ''
  const text =
    s.lastMessage.length > maxChars ? `${s.lastMessage.slice(0, maxChars - 1)}…` : s.lastMessage
  return `${s.lastRole === 'user' ? 'Q' : 'A'}: ${text}`
}

function platformLabel(s: TerminalSessionSummary): string {
  if (s.id === '__new__') return 'N'
  if (s.platform === 'discord') return 'D'
  if (s.platform === 'slack') return 'S'
  return 'W'
}

function platformName(s: TerminalSessionSummary): string {
  if (s.platform === 'discord') return 'Discord'
  if (s.platform === 'slack') return 'Slack'
  return 'Web'
}

function formatRemaining(s: TerminalSessionSummary): string {
  if (typeof s.remainingSec === 'number' && s.remainingSec > 0) {
    return formatDuration(s.remainingSec)
  }
  const timeoutAt = s.timeoutAt
  if (!timeoutAt) return ''
  const target = Number(timeoutAt)
  if (!Number.isFinite(target) || target <= 0) return ''
  const seconds = Math.max(0, Math.round((target - Date.now()) / 1000))
  if (seconds <= 0) return '0:00'
  return formatDuration(seconds)
}

function formatDuration(totalSeconds: number): string {
  const seconds = Math.max(0, Math.round(totalSeconds))
  const minutes = Math.floor(seconds / 60)
  const rest = seconds % 60
  return `${minutes}:${String(rest).padStart(2, '0')}`
}

function renderTerminalIdle() {
  const summary = terminalSummary ?? currentSession()
  const platform = summary ? platformLabel(summary) : 'W'
  const history = historyBlock()
  const postHint = summary?.platform === 'discord' ? 'タップ:音声投稿' : 'タップ:音声入力'
  const navHint = historyMessages.length > 1 || currentHistoryPages().length > 1 ? '上下:読む ' : ''
  render(`${platform} ${APP_BUILD_LABEL}\n${history}\n${navHint}${postHint}\nダブル:一覧`)
}

function historyBlock(): string {
  if (!historyMessages.length || historyIndex < 0) return '履歴なし'
  const msg = currentHistoryMessage()
  if (!msg) return '履歴なし'
  const pages = currentHistoryPages()
  const safePage = Math.max(0, Math.min(historyPageIndex, pages.length - 1))
  const prefix = msg.role === 'user' ? 'Q' : 'A'
  const pos = `${historyIndex + 1}/${historyMessages.length}`
  return `${pos} ${prefix} p${safePage + 1}/${pages.length}\n${pages[safePage]}`
}

function currentHistoryMessage(): TerminalSessionMessage | null {
  if (!historyMessages.length || historyIndex < 0) return null
  return historyMessages[Math.max(0, Math.min(historyIndex, historyMessages.length - 1))] ?? null
}

function currentHistoryPages(): string[] {
  return displayPages(currentHistoryMessage()?.content ?? '')
}

function splitPages(text: string): string[] {
  return displayPages(text)
}

function displayPages(text: string): string[] {
  return paginateText(text, HISTORY_PAGE_BOX)
}

function resetHistoryPage(toLastPage = false) {
  const pages = currentHistoryPages()
  historyPageIndex = toLastPage ? Math.max(0, pages.length - 1) : 0
}

async function loadTerminalHistory(sessionId: string) {
  const detail = await getTerminalSessionDetail(sessionId, 30)
  historyMessages = detail.messages
  historyIndex = historyMessages.length - 1
  resetHistoryPage()
}

function browseHistory(offset: number) {
  if (state !== 'ready' || viewMode !== 'terminal' || !historyMessages.length) return
  const pages = currentHistoryPages()
  if (offset > 0) {
    if (historyPageIndex < pages.length - 1) {
      historyPageIndex += 1
    } else if (historyIndex < historyMessages.length - 1) {
      historyIndex += 1
      resetHistoryPage()
    }
  } else if (offset < 0) {
    if (historyPageIndex > 0) {
      historyPageIndex -= 1
    } else if (historyIndex > 0) {
      historyIndex -= 1
      resetHistoryPage(true)
    }
  }
  renderTerminalIdle()
}

function renderConfirming() {
  const pages = splitPages(pendingQuestion)
  pendingQuestionPageIndex = Math.max(0, Math.min(pendingQuestionPageIndex, pages.length - 1))
  render(
    `聞き取り結果 p${pendingQuestionPageIndex + 1}/${pages.length}\n${pages[pendingQuestionPageIndex]}\nタップ:送信\nダブル:破棄`,
  )
}

function renderLiveAssistantText(text: string) {
  const pages = displayPages(text)
  const lastPage = pages[Math.max(0, pages.length - 1)]
  render(`生成中 p${pages.length}/${pages.length}\n${lastPage}`)
}

function addAssistantHistory(content: string) {
  historyMessages.push({
    id: `assistant-${Date.now()}`,
    role: 'assistant',
    content,
  })
  historyIndex = historyMessages.length - 1
  resetHistoryPage()
}

function startReplyPolling(jobId: string) {
  if (!jobId || replyPolls.has(jobId)) return
  const startedAt = Date.now()
  const timer = window.setInterval(async () => {
    try {
      const result = await getTerminalReply(jobId)
      if (result.status === 'done' && result.reply?.content) {
        window.clearInterval(timer)
        replyPolls.delete(jobId)
        addAssistantHistory(result.reply.content)
        if (viewMode === 'terminal') renderTerminalIdle()
      } else if (result.status === 'error' || result.status === 'expired') {
        window.clearInterval(timer)
        replyPolls.delete(jobId)
        addAssistantHistory(
          result.reply?.content || result.error || 'Discord返信の取得に失敗しました',
        )
        if (viewMode === 'terminal') renderTerminalIdle()
      }
    } catch (err) {
      if (Date.now() - startedAt > 60_000) {
        window.clearInterval(timer)
        replyPolls.delete(jobId)
        addAssistantHistory(`Discord返信の確認に失敗: ${(err as Error)?.message ?? err}`)
        if (viewMode === 'terminal') renderTerminalIdle()
      }
    }
  }, 3_000)
  replyPolls.set(jobId, timer)
}

function browsePendingQuestion(offset: number) {
  if (state !== 'confirming' || !pendingQuestion) return
  const pages = splitPages(pendingQuestion)
  pendingQuestionPageIndex = Math.max(
    0,
    Math.min(pendingQuestionPageIndex + offset, pages.length - 1),
  )
  renderConfirming()
}

async function loadSessionList() {
  const result = await listTerminalSessions(12)
  const selectedId = currentSession()?.id
  sessions = [result.new_session, ...result.sessions]
  if (selectedId) {
    const nextIndex = sessions.findIndex(s => s.id === selectedId)
    sessionIndex = nextIndex >= 0 ? nextIndex : 0
  } else {
    sessionIndex = sessions.length ? 0 : -1
  }
}

function stopSessionRefresh() {
  if (sessionRefreshTimer !== null) {
    window.clearInterval(sessionRefreshTimer)
    sessionRefreshTimer = null
  }
}

function startSessionRefresh() {
  stopSessionRefresh()
  sessionRefreshTimer = window.setInterval(async () => {
    if (viewMode !== 'sessions' || state !== 'ready') return
    try {
      await loadSessionList()
      render(formatSessionList())
    } catch {
      // 次回の更新で復帰させる。メガネ表示は直前の一覧を維持する。
    }
  }, SESSION_REFRESH_MS)
}

function connectEvents(session: TerminalSession) {
  eventSource?.close()
  eventSource = new EventSource(terminalEventsUrl(session))
  eventSource.addEventListener('ready', () => {
    setStatus(state === 'confirming' ? 'ready' : state)
  })
  eventSource.onmessage = event => {
    try {
      const payload = JSON.parse(event.data) as {
        type?: string
        user_text?: string
        full_text?: string
        text?: string
        message?: string
      }
      if (payload.type === 'turn.started') {
        state = 'thinking'
        setStatus('thinking')
        if (payload.user_text) render(`Q: ${payload.user_text}\n\n考え中…`)
      } else if (payload.type === 'message.delta') {
        renderLiveAssistantText(payload.full_text || payload.text || '')
      } else if (payload.type === 'turn.complete') {
        const text = payload.text || '（応答が空でした）'
        historyMessages.push({
          id: `assistant-${Date.now()}`,
          role: 'assistant',
          content: text,
        })
        historyIndex = historyMessages.length - 1
        resetHistoryPage()
        renderTerminalIdle()
        void toReady()
      } else if (payload.type === 'agent.error') {
        render(`エラー: ${payload.message || 'agent error'}\nタップで再試行。`)
        void toReady()
      }
    } catch {
      // keepalive/comment 以外で不正 JSON が来ても表示は維持する。
    }
  }
  eventSource.onerror = () => {
    setStatus('error')
  }
}

async function openSelectedSession() {
  const selected = currentSession()
  if (!selected) return
  stopSessionRefresh()
  state = 'thinking'
  setStatus('thinking')
  render(`${selected.title}\n開いています…`)
  try {
    const session =
      selected.id === '__new__'
        ? await createTerminalSession('Even G2 Terminal')
        : await openTerminalSession(selected.id)
    terminalSession = session
    terminalSummary =
      selected.id === '__new__'
        ? { id: session.session_id, title: 'Even G2 Terminal', platform: 'web' }
        : selected
    viewMode = 'terminal'
    await loadTerminalHistory(session.session_id)
    if (!terminalSummary.platform || terminalSummary.platform === 'web') {
      connectEvents(session)
    } else {
      eventSource?.close()
      eventSource = null
    }
    renderTerminalIdle()
    await toReady()
  } catch (err) {
    render(`セッションエラー: ${(err as Error)?.message ?? err}`)
    await toReady()
  }
}

async function showSessionList() {
  eventSource?.close()
  eventSource = null
  terminalSession = null
  terminalSummary = null
  historyMessages = []
  historyIndex = -1
  viewMode = 'sessions'
  state = 'thinking'
  setStatus('thinking')
  render(`${APP_BUILD_LABEL}\nセッション読込中…`)
  try {
    await loadSessionList()
    state = 'ready'
    setStatus('ready')
    render(formatSessionList())
    startSessionRefresh()
  } catch (err) {
    render(`セッション一覧エラー: ${(err as Error)?.message ?? err}`)
    await toReady()
  }
}

function selectSession(offset: number) {
  if (!sessions.length || state !== 'ready') return
  sessionIndex = (sessionIndex + offset + sessions.length) % sessions.length
  render(formatSessionList())
}

async function startRecording() {
  if (state !== 'ready' || viewMode !== 'terminal') return
  chunks = []
  bufLen = 0
  state = 'recording'
  await bridge.audioControl(true)
  setStatus('recording')
  render(RECORDING)
}

async function submit() {
  if (state !== 'recording') return
  state = 'thinking'
  setStatus('thinking')
  await bridge.audioControl(false)
  if (bufLen === 0) {
    render('音声が入りませんでした。\nタップでもう一度。')
    await toReady()
    return
  }
  const pcm = drainBuffer()
  render('聞き取り中…')
  try {
    const question = await transcribe(pcm)
    if (!question) {
      render('うまく聞き取れませんでした。\nタップでもう一度。')
      await toReady()
      return
    }
    if (!terminalSession) {
      render('セッションがありません。\nダブルタップで一覧へ。')
      await toReady()
      return
    }
    pendingQuestion = question
    pendingQuestionPageIndex = 0
    state = 'confirming'
    setStatus('ready', 'CONFIRM')
    renderConfirming()
  } catch (err) {
    render(`エラー: ${(err as Error)?.message ?? err}\nタップで再試行。`)
    await toReady()
  }
}

async function sendPendingQuestion() {
  if (state !== 'confirming' || !pendingQuestion) return
  const question = pendingQuestion
  pendingQuestion = ''
  state = 'thinking'
  setStatus('thinking')
  if (!terminalSession) {
    render('セッションがありません。\nダブルタップで一覧へ。')
    await toReady()
    return
  }
  try {
    historyMessages.push({
      id: `local-${Date.now()}`,
      role: 'user',
      content: question,
    })
    historyIndex = historyMessages.length - 1
    resetHistoryPage()
    if (terminalSummary?.platform === 'discord') {
      render(`投稿/応答中…\n${question}`)
      const result = await postTerminalSessionMessage(terminalSummary.id, question)
      if (typeof result?.reply === 'object' && result.reply?.content) {
        addAssistantHistory(result.reply.content)
      } else if (result?.reply_job_id) {
        startReplyPolling(result.reply_job_id)
      }
      renderTerminalIdle()
      await toReady()
      return
    }
    render(`Q: ${question}\n\n考え中…`)
    await postTerminalSessionMessage(terminalSession.session_id, question)
  } catch (err) {
    render(`エラー: ${(err as Error)?.message ?? err}\nタップで再試行。`)
    await toReady()
  }
}

async function discardPendingQuestion() {
  if (state !== 'confirming') return
  pendingQuestion = ''
  pendingQuestionPageIndex = 0
  render('破棄しました。')
  await toReady()
  renderTerminalIdle()
}

function onSingleClick() {
  if (wakeDisplay()) return
  if (state === 'ready' && viewMode === 'sessions') {
    void openSelectedSession()
  } else if (state === 'ready' && viewMode === 'terminal') {
    void startRecording()
  } else if (state === 'recording') {
    void submit()
  } else if (state === 'confirming') {
    void sendPendingQuestion()
  }
}

if (bridgeConfigured()) {
  await bridge.audioControl(false)
  void showSessionList()
}

// ---- 後始末 -----------------------------------------------------------------
let cleanedUp = false
function cleanup() {
  if (cleanedUp) return
  cleanedUp = true
  eventSource?.close()
  stopSessionRefresh()
  for (const timer of replyPolls.values()) window.clearInterval(timer)
  replyPolls.clear()
  if (hideTimer !== null) window.clearTimeout(hideTimer)
  window.clearInterval(clockTimer)
  bridge.audioControl(false)
  unsubscribe()
}

// ---- イベント振り分け -------------------------------------------------------
function envelopeType(env: { eventType?: OsEventTypeList | string | number } | undefined): number {
  if (!env) return -1
  return OsEventTypeList.fromJson(env.eventType ?? OsEventTypeList.CLICK_EVENT) ?? -1
}

const unsubscribe = bridge.onEvenHubEvent(event => {
  const pcm = event.audioEvent?.audioPcm
  if (pcm && pcm.length) {
    appendPcm(pcm)
    return
  }

  const sysType = envelopeType(event.sysEvent)
  const textType = envelopeType(event.textEvent)

  if (
    sysType === OsEventTypeList.DOUBLE_CLICK_EVENT ||
    textType === OsEventTypeList.DOUBLE_CLICK_EVENT
  ) {
    if (wakeDisplay()) return
    if (state === 'confirming') {
      void discardPendingQuestion()
      return
    }
    if (viewMode === 'terminal') {
      void showSessionList()
      return
    }
    bridge.shutDownPageContainer(1)
    return
  }

  if (
    sysType === OsEventTypeList.SCROLL_TOP_EVENT ||
    textType === OsEventTypeList.SCROLL_TOP_EVENT
  ) {
    if (wakeDisplay()) return
    if (state === 'confirming') browsePendingQuestion(-1)
    else if (viewMode === 'sessions') selectSession(-1)
    else if (viewMode === 'terminal') browseHistory(-1)
    return
  }

  if (
    sysType === OsEventTypeList.SCROLL_BOTTOM_EVENT ||
    textType === OsEventTypeList.SCROLL_BOTTOM_EVENT
  ) {
    if (wakeDisplay()) return
    if (state === 'confirming') browsePendingQuestion(1)
    else if (viewMode === 'sessions') selectSession(1)
    else if (viewMode === 'terminal') browseHistory(1)
    return
  }

  if (
    sysType === OsEventTypeList.SYSTEM_EXIT_EVENT ||
    sysType === OsEventTypeList.ABNORMAL_EXIT_EVENT
  ) {
    cleanup()
    return
  }

  if (
    sysType === OsEventTypeList.CLICK_EVENT ||
    textType === OsEventTypeList.CLICK_EVENT
  ) {
    onSingleClick()
  }
})

window.addEventListener('beforeunload', cleanup)
}
