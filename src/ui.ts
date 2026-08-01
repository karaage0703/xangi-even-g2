import {
  clearBridgeConfig,
  clearBridgeConfigFromEvenStorage,
  type EvenStorageBridge,
  getBridgeConfig,
  saveBridgeConfig,
  saveBridgeConfigToEvenStorage,
  type BridgeConfig,
} from './bridge'
import { APP_BUILD_LABEL } from './version'

type Status = 'connecting' | 'ready' | 'recording' | 'thinking' | 'error'
export type BodyLayout = 'wrapped' | 'session-list'

let statusEl: HTMLDivElement
let bodyEl: HTMLDivElement
let bridgeUrlInput: HTMLInputElement
let tokenInput: HTMLInputElement
let configSummaryEl: HTMLDivElement
let evenStorage: EvenStorageBridge | null = null

const STATUS_LABEL: Record<Status, string> = {
  connecting: 'CONNECTING',
  ready: 'READY',
  recording: '● REC',
  thinking: 'THINKING',
  error: 'ERROR',
}

export function mountUi(storage?: EvenStorageBridge) {
  evenStorage = storage ?? null
  const config = getBridgeConfig()
  const app = document.querySelector<HTMLDivElement>('#app')!
  app.innerHTML = `
    <main class="panel">
      <header>
        <h1>xangi for G2 <span class="version">${APP_BUILD_LABEL}</span></h1>
        <div id="status" class="status status-connecting">CONNECTING</div>
      </header>
      <section class="settings" aria-label="Bridge settings">
        <form id="settings-form" class="settings-form">
          <label>
            <span>Bridge URL</span>
            <input id="bridge-url" name="bridgeUrl" type="url" inputmode="url"
              placeholder="https://example.ts.net" autocomplete="url" />
          </label>
          <label>
            <span>Token</span>
            <input id="bridge-token" name="token" type="password" autocomplete="off"
              placeholder="optional" />
          </label>
          <div class="settings-actions">
            <button type="submit">保存</button>
            <button type="button" id="clear-settings" class="secondary">クリア</button>
          </div>
        </form>
        <div id="config-summary" class="config-summary"></div>
      </section>
      <section id="body" class="body" aria-live="polite"></section>
      <footer>${APP_BUILD_LABEL} / タップ=送信 / ダブルタップ=戻る</footer>
    </main>
  `
  statusEl = app.querySelector<HTMLDivElement>('#status')!
  bodyEl = app.querySelector<HTMLDivElement>('#body')!
  bridgeUrlInput = app.querySelector<HTMLInputElement>('#bridge-url')!
  tokenInput = app.querySelector<HTMLInputElement>('#bridge-token')!
  configSummaryEl = app.querySelector<HTMLDivElement>('#config-summary')!
  bridgeUrlInput.value = config.bridgeUrl
  tokenInput.value = config.token
  updateConfigSummary(config)
  bindSettingsForm()
  injectStyles()
}

export function setStatus(kind: Status, text?: string) {
  if (!statusEl) return
  statusEl.className = `status status-${kind}`
  statusEl.textContent = text ?? STATUS_LABEL[kind]
}

/** メガネに出すのと同じ本文を companion 画面にミラーする。 */
export function setBody(text: string, layout: BodyLayout = 'wrapped') {
  if (!bodyEl) return
  bodyEl.classList.toggle('body-session-list', layout === 'session-list')
  if (layout === 'wrapped') {
    bodyEl.textContent = text
    return
  }

  const fragment = document.createDocumentFragment()
  for (const line of text.split('\n')) {
    const row = document.createElement('div')
    row.className = 'body-line'
    row.textContent = line || '\u00a0'
    fragment.appendChild(row)
  }
  bodyEl.replaceChildren(fragment)
}

function bindSettingsForm() {
  const form = document.querySelector<HTMLFormElement>('#settings-form')!
  const clearButton = document.querySelector<HTMLButtonElement>('#clear-settings')!
  form.addEventListener('submit', async (event) => {
    event.preventDefault()
    const next = {
      bridgeUrl: bridgeUrlInput.value,
      token: tokenInput.value,
    }
    saveBridgeConfig(next)
    const saved = getBridgeConfig()
    if (evenStorage) await saveBridgeConfigToEvenStorage(evenStorage, saved)
    updateConfigSummary(saved)
    window.location.reload()
  })
  clearButton.addEventListener('click', async () => {
    clearBridgeConfig()
    if (evenStorage) await clearBridgeConfigFromEvenStorage(evenStorage)
    bridgeUrlInput.value = ''
    tokenInput.value = ''
    updateConfigSummary({ bridgeUrl: '', token: '' })
    window.location.reload()
  })
}

function updateConfigSummary(config: BridgeConfig) {
  if (!configSummaryEl) return
  if (!config.bridgeUrl) {
    configSummaryEl.textContent = '未設定'
    return
  }
  configSummaryEl.textContent = `${config.bridgeUrl}${config.token ? ' / tokenあり' : ''}`
}

function injectStyles() {
  // ER brand dark-theme surfaces: #232323 / #2E2E2E / #3E3E3E.
  // ER OS green (#3CFA44) + signal red (#FF453A) for state chips.
  const css = `
    :root { color-scheme: dark; }
    html, body { margin: 0; height: 100%; background: #232323; color: #E5E5E5;
      font: 16px/1.4 -apple-system, BlinkMacSystemFont, 'Helvetica Neue', system-ui, sans-serif;
      touch-action: manipulation; -webkit-text-size-adjust: 100%;
      overscroll-behavior: none; }
    #app { display: flex; min-height: 100%; }
    .panel { display: flex; flex-direction: column; gap: 16px;
      width: 100%; max-width: 640px; margin: 0 auto; padding: 24px; box-sizing: border-box; }
    header { display: flex; align-items: center; justify-content: space-between; }
    h1 { display: flex; flex-wrap: wrap; gap: 8px; align-items: baseline;
      font-size: 18px; font-weight: 600; margin: 0; letter-spacing: 0.02em; }
    .version { color: #9B9B9B; font-size: 12px; font-weight: 500; letter-spacing: 0; }
    .status { font-size: 12px; padding: 4px 10px; border-radius: 999px;
      border: 1px solid transparent; letter-spacing: 0.04em; }
    .status-connecting { color: #A7A7A7; border-color: #3E3E3E; }
    .status-ready      { color: #3CFA44; border-color: #3CFA44; background: rgba(60,250,68,0.08); }
    .status-recording  { color: #FF453A; border-color: #FF453A; background: rgba(255,69,58,0.12); }
    .status-thinking   { color: #FFD60A; border-color: #FFD60A; background: rgba(255,214,10,0.08); }
    .status-error      { color: #FF453A; border-color: #FF453A; background: rgba(255,69,58,0.08); }
    .settings { display: grid; gap: 8px; background: #2A2A2A; border: 1px solid #3E3E3E;
      border-radius: 8px; padding: 14px; }
    .settings-form { display: grid; gap: 10px; }
    label { display: grid; gap: 6px; color: #CFCFCF; font-size: 12px; letter-spacing: 0.02em; }
    input { width: 100%; box-sizing: border-box; border: 1px solid #4A4A4A; border-radius: 6px;
      padding: 10px 12px; background: #202020; color: #F5F5F5; font: inherit; }
    input:focus { outline: 2px solid rgba(60,250,68,0.45); outline-offset: 1px; border-color: #3CFA44; }
    .settings-actions { display: flex; gap: 8px; align-items: center; }
    button { min-height: 36px; border: 1px solid #3CFA44; border-radius: 6px; padding: 0 14px;
      background: #3CFA44; color: #111; font-weight: 600; font: inherit; }
    button.secondary { background: transparent; color: #DADADA; border-color: #555; }
    .config-summary { color: #8E8E8E; font-size: 12px; overflow-wrap: anywhere; }
    .body { flex: 1; overflow: auto; background: #2E2E2E; border: 1px solid #3E3E3E;
      color: #E5E5E5; border-radius: 12px; padding: 20px; font-size: 18px; line-height: 1.5;
      min-height: 180px; white-space: pre-wrap; word-break: break-word; }
    .body-session-list { overflow-x: hidden; white-space: normal; word-break: normal; }
    .body-session-list .body-line { min-width: 0; overflow: hidden; text-overflow: ellipsis;
      white-space: nowrap; }
    footer { font-size: 12px; color: #7B7B7B; text-align: center; }
  `
  const style = document.createElement('style')
  style.textContent = css
  document.head.appendChild(style)
}
