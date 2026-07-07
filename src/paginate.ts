import { measureTextWrap } from '@evenrealities/pretext'

export const G2_DISPLAY_WIDTH = 576
export const G2_DISPLAY_HEIGHT = 288
export const G2_LINE_HEIGHT = 27
export const TEXT_CONTAINER_UPGRADE_MAX_CHARS = 2000
export const G2_PROTOCOL_MAX_PAGES = 255

const TOKEN_RE =
  /[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Hangul}]|[^\s]+(?:\s+)?|\s+/gu

export interface PageBox {
  width: number
  height: number
  maxPages?: number
  maxCharsPerPage?: number
}

export function paginateText(source: string, box: PageBox): string[] {
  const text = normalizeText(source)
  if (!text) return ['(空)']

  const maxLines = Math.max(1, Math.floor(box.height / G2_LINE_HEIGHT))
  const maxPages = Math.max(1, Math.min(box.maxPages ?? G2_PROTOCOL_MAX_PAGES, G2_PROTOCOL_MAX_PAGES))
  const maxCharsPerPage = Math.max(
    1,
    Math.min(box.maxCharsPerPage ?? TEXT_CONTAINER_UPGRADE_MAX_CHARS, TEXT_CONTAINER_UPGRADE_MAX_CHARS),
  )
  const pages: string[] = []
  let current = ''

  const fits = (candidate: string) => {
    if (!candidate) return true
    if (candidate.length > maxCharsPerPage) return false
    return measureTextWrap(candidate, box.width).lineCount <= maxLines
  }

  const pushPage = () => {
    const page = current.trim()
    if (page) pages.push(page)
    current = ''
  }

  const appendBlock = (block: string) => {
    if (!block) return
    const candidate = joinBlocks(current, block)
    if (fits(candidate)) {
      current = candidate
      return
    }
    if (current) pushPage()
    if (fits(block)) {
      current = block
      return
    }
    appendTokens(block)
  }

  const appendTokens = (block: string) => {
    const tokens = block.match(TOKEN_RE) ?? Array.from(block)
    for (const token of tokens) {
      if (!token) continue
      const candidate = current + token
      if (fits(candidate)) {
        current = candidate
        continue
      }
      if (current) pushPage()
      if (fits(token)) {
        current = token.trimStart()
        continue
      }
      appendCodepoints(token)
    }
  }

  const appendCodepoints = (token: string) => {
    for (const ch of Array.from(token)) {
      const candidate = current + ch
      if (fits(candidate)) {
        current = candidate
      } else {
        if (current) pushPage()
        current = ch.trimStart()
      }
    }
  }

  for (const block of text.split(/\n{2,}/)) {
    appendBlock(block.trim())
    if (pages.length >= maxPages) break
  }
  if (current && pages.length < maxPages) pushPage()

  if (pages.length > maxPages) pages.length = maxPages
  if (pages.length >= maxPages && textContinues(text, pages)) {
    pages[maxPages - 1] = fitTruncationMarker(pages[maxPages - 1], fits)
  }
  return pages.length ? pages : ['(空)']
}

function normalizeText(value: string): string {
  return String(value || '')
    .replace(/\r\n/g, '\n')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n[ \t]+/g, '\n')
    .trim()
}

function joinBlocks(left: string, right: string): string {
  if (!left) return right
  if (!right) return left
  return `${left}\n\n${right}`
}

function textContinues(source: string, pages: string[]): boolean {
  const joined = pages.join('')
  return joined.length < source.replace(/\s+/g, '').length
}

function fitTruncationMarker(page: string, fits: (candidate: string) => boolean): string {
  const marker = '\n… 続きはDiscord/Webで確認'
  if (fits(page + marker)) return page + marker
  const chars = Array.from(page)
  while (chars.length > 0) {
    chars.pop()
    const candidate = `${chars.join('').trimEnd()}${marker}`
    if (fits(candidate)) return candidate
  }
  return '… 続きはDiscord/Webで確認'
}
