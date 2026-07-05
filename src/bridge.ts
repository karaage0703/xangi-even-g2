// xangi ブリッジ（even_g2_bridge.py）クライアント。
//
// 主に 4 つ叩く:
//   - POST <base>/stt   生 PCM (s16le 16kHz mono) -> {"text": "..."}（ローカル Whisper）
//   - POST <base>/       OpenAI 互換チャット -> 答え（xangi 本体に橋渡し、メガネ整形済み）
//   - POST <base>/terminal/session  G2 用 Web session 作成
//   - GET  <base>/terminal/sessions G2 用 Web session 一覧
//   - POST <base>/terminal/inbox    terminal/device inbox へテキスト投入
//   - GET  <base>/terminal/events   xangi events SSE proxy
//
// base / token は companion 画面の設定を localStorage に保存して読む。開発時は
// .env.local の VITE_BRIDGE_URL / VITE_BRIDGE_TOKEN を初期値として使える。

const STORAGE_KEY = 'xangi-g2-config-v1'

export interface EvenStorageBridge {
  getLocalStorage(key: string): Promise<string>
  setLocalStorage(key: string, value: string): Promise<boolean>
}

export interface BridgeConfig {
  bridgeUrl: string
  token: string
}

export interface TerminalSession {
  session_id: string
  thread_id: string
  events_url: string
  inbox_url: string
}

export interface TerminalSessionSummary {
  id: string
  title: string
  platform?: 'web' | 'discord' | 'slack' | string
  contextKey?: string
  updatedAt?: string
  messageCount?: number
  status?: 'idle' | 'busy' | 'awaiting' | string
  isActive?: boolean
  timeoutAt?: string
  timeoutMs?: number
  remainingSec?: number
  lastMessage?: string
  lastRole?: string
}

export interface TerminalSessionMessage {
  id: string
  role: 'user' | 'assistant' | string
  content: string
  createdAt?: string
}

export interface PostTerminalSessionResult {
  ok?: boolean
  posted?: { content?: string }
  reply?: { content?: string }
  reply_error?: string
}

export interface TerminalSessionDetail {
  id: string
  title: string
  platform?: 'web' | 'discord' | 'slack' | string
  messages: TerminalSessionMessage[]
}

export interface DiscordChannel {
  id: string
  name: string
  guild_id?: string
}

export interface DiscordMessage {
  id: string
  author: string
  content: string
  timestamp?: string
}

export function getBridgeConfig(): BridgeConfig {
  const stored = readStoredConfig()
  return {
    bridgeUrl: normalizeBaseUrl(stored.bridgeUrl || ((import.meta.env.VITE_BRIDGE_URL as string) || '')),
    token: stored.token || ((import.meta.env.VITE_BRIDGE_TOKEN as string) || ''),
  }
}

export function saveBridgeConfig(config: BridgeConfig): void {
  const next = {
    bridgeUrl: normalizeBaseUrl(config.bridgeUrl),
    token: config.token.trim(),
  }
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
}

export function clearBridgeConfig(): void {
  window.localStorage.removeItem(STORAGE_KEY)
}

export async function hydrateBridgeConfig(storage: EvenStorageBridge): Promise<void> {
  try {
    const raw = await storage.getLocalStorage(STORAGE_KEY)
    if (raw) window.localStorage.setItem(STORAGE_KEY, raw)
  } catch (error) {
    console.warn('Failed to hydrate bridge config from Even storage', error)
  }
}

export async function saveBridgeConfigToEvenStorage(
  storage: EvenStorageBridge,
  config = getBridgeConfig(),
): Promise<void> {
  try {
    await storage.setLocalStorage(STORAGE_KEY, JSON.stringify(config))
  } catch (error) {
    console.warn('Failed to save bridge config to Even storage', error)
  }
}

export async function clearBridgeConfigFromEvenStorage(storage: EvenStorageBridge): Promise<void> {
  try {
    await storage.setLocalStorage(STORAGE_KEY, '')
  } catch (error) {
    console.warn('Failed to clear bridge config from Even storage', error)
  }
}

export function bridgeConfigured(): boolean {
  return getBridgeConfig().bridgeUrl.length > 0
}

function readStoredConfig(): BridgeConfig {
  const fallback = { bridgeUrl: '', token: '' }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return fallback
    const parsed = JSON.parse(raw) as Partial<BridgeConfig>
    return {
      bridgeUrl: typeof parsed.bridgeUrl === 'string' ? parsed.bridgeUrl : '',
      token: typeof parsed.token === 'string' ? parsed.token : '',
    }
  } catch {
    return fallback
  }
}

function normalizeBaseUrl(value: string): string {
  return value.trim().replace(/\/+$/, '')
}

function baseUrl(): string {
  const base = getBridgeConfig().bridgeUrl
  if (!base) throw new Error('Bridge URL is not configured')
  return base
}

function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const h: Record<string, string> = { ...extra }
  const token = getBridgeConfig().token
  if (token) h['Authorization'] = `Bearer ${token}`
  return h
}

/** 録音した PCM をブリッジの /stt に送り、文字起こしテキストを得る。 */
export async function transcribe(pcm: Uint8Array): Promise<string> {
  const base = baseUrl()
  const res = await fetch(`${base}/stt`, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/octet-stream' }),
    body: pcm as BodyInit,
  })
  if (!res.ok) throw new Error(`STT HTTP ${res.status}`)
  const data = (await res.json()) as { text?: string }
  return (data.text ?? '').trim()
}

/** 文字起こしした質問を xangi に投げ、メガネ表示向けに整形済みの答えを得る。 */
export async function ask(question: string): Promise<string> {
  const base = baseUrl()
  const res = await fetch(`${base}/`, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({
      model: 'xangi',
      messages: [{ role: 'user', content: question }],
    }),
  })
  if (!res.ok) throw new Error(`ASK HTTP ${res.status}`)
  const data = (await res.json()) as {
    choices?: Array<{ message?: { content?: string } }>
  }
  return (data?.choices?.[0]?.message?.content ?? '').trim()
}

export async function createTerminalSession(title = 'Even G2 Terminal'): Promise<TerminalSession> {
  const base = baseUrl()
  const res = await fetch(`${base}/terminal/session`, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ title }),
  })
  if (!res.ok) throw new Error(`SESSION HTTP ${res.status}`)
  const data = (await res.json()) as TerminalSession
  if (!data.session_id || !data.thread_id) throw new Error('terminal session response missing ids')
  return data
}

export async function openTerminalSession(sessionId: string): Promise<TerminalSession> {
  const base = baseUrl()
  const res = await fetch(`${base}/terminal/session`, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ session_id: sessionId }),
  })
  if (!res.ok) throw new Error(`SESSION HTTP ${res.status}`)
  const data = (await res.json()) as TerminalSession
  if (!data.session_id || !data.thread_id) throw new Error('terminal session response missing ids')
  return data
}

export async function listTerminalSessions(limit = 10): Promise<{
  sessions: TerminalSessionSummary[]
  new_session: TerminalSessionSummary
}> {
  const base = baseUrl()
  const url = new URL(`${base}/terminal/sessions`)
  url.searchParams.set('limit', String(limit))
  const res = await fetch(url.toString(), {
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`SESSIONS HTTP ${res.status}`)
  const data = (await res.json()) as {
    sessions?: TerminalSessionSummary[]
    new_session?: TerminalSessionSummary
  }
  return {
    sessions: data.sessions ?? [],
    new_session: data.new_session ?? { id: '__new__', title: '+ New Session' },
  }
}

export async function getTerminalSessionDetail(
  sessionId: string,
  limit = 20,
): Promise<TerminalSessionDetail> {
  const base = baseUrl()
  const url = new URL(`${base}/terminal/session`)
  url.searchParams.set('session_id', sessionId)
  url.searchParams.set('limit', String(limit))
  const res = await fetch(url.toString(), {
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`SESSION DETAIL HTTP ${res.status}`)
  const data = (await res.json()) as TerminalSessionDetail
  return { ...data, messages: data.messages ?? [] }
}

export async function sendTerminalMessage(session: TerminalSession, text: string): Promise<void> {
  const base = baseUrl()
  const res = await fetch(`${base}${session.inbox_url || '/terminal/inbox'}`, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({
      appSessionId: session.session_id,
      source: 'even-g2',
      text,
    }),
  })
  if (!res.ok) throw new Error(`INBOX HTTP ${res.status}`)
}

export async function postTerminalSessionMessage(
  sessionId: string,
  text: string,
): Promise<PostTerminalSessionResult | void> {
  const base = baseUrl()
  const res = await fetch(`${base}/terminal/post`, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({
      session_id: sessionId,
      source: 'even-g2',
      text,
    }),
  })
  if (!res.ok) throw new Error(`POST HTTP ${res.status}: ${await responseErrorText(res)}`)
  return (await res.json()) as PostTerminalSessionResult
}

async function responseErrorText(res: Response): Promise<string> {
  try {
    const data = (await res.json()) as { error?: { message?: string } }
    return data.error?.message || res.statusText || 'unknown error'
  } catch {
    try {
      return (await res.text()) || res.statusText || 'unknown error'
    } catch {
      return res.statusText || 'unknown error'
    }
  }
}

export function terminalEventsUrl(session: TerminalSession): string {
  const config = getBridgeConfig()
  if (!config.bridgeUrl) throw new Error('Bridge URL is not configured')
  const url = new URL(`${config.bridgeUrl}${session.events_url || '/terminal/events'}`)
  if (config.token) url.searchParams.set('token', config.token)
  return url.toString()
}

export async function listDiscordChannels(): Promise<{
  channels: DiscordChannel[]
  default_channel_id?: string
}> {
  const base = baseUrl()
  const res = await fetch(`${base}/discord/channels`, {
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`DISCORD CHANNELS HTTP ${res.status}`)
  const data = (await res.json()) as {
    channels?: DiscordChannel[]
    default_channel_id?: string
  }
  return {
    channels: data.channels ?? [],
    default_channel_id: data.default_channel_id,
  }
}

export async function listDiscordMessages(
  channelId: string,
  limit = 5,
): Promise<DiscordMessage[]> {
  const base = baseUrl()
  const url = new URL(`${base}/discord/messages`)
  url.searchParams.set('channel_id', channelId)
  url.searchParams.set('limit', String(limit))
  const res = await fetch(url.toString(), {
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`DISCORD MESSAGES HTTP ${res.status}`)
  const data = (await res.json()) as { messages?: DiscordMessage[] }
  return data.messages ?? []
}

export async function postDiscordMessage(channelId: string, content: string): Promise<void> {
  const base = baseUrl()
  const res = await fetch(`${base}/discord/messages`, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({
      channel_id: channelId,
      content,
    }),
  })
  if (!res.ok) throw new Error(`DISCORD POST HTTP ${res.status}`)
}
