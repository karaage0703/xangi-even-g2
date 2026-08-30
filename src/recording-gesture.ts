export type RecordingMode = 'tap' | 'hold' | null
export type RecordingState = 'ready' | 'recording' | 'thinking' | 'confirming'
export type RecordingViewMode = 'sessions' | 'terminal'
export type LongPressAction = 'start-hold' | 'adopt-hold' | 'submit' | 'ignore'

export function recordingPrompt(mode: Exclude<RecordingMode, null>, animationFrame = 0): string {
  if (mode === 'tap') return '録音中… 話してください。\nもう一度タップで送信。'
  const dots = '.'.repeat((Math.max(0, animationFrame) % 3) + 1)
  return `長押し中入力\nListening ${dots}\n指を離すと送信。`
}

export function longPressAction(
  phase: 'start' | 'release',
  state: RecordingState,
  viewMode: RecordingViewMode,
  recordingMode: RecordingMode,
): LongPressAction {
  if (phase === 'release') {
    return state === 'recording' && recordingMode === 'hold' ? 'submit' : 'ignore'
  }

  if (viewMode !== 'terminal') return 'ignore'
  if (state === 'ready') return 'start-hold'
  if (state === 'recording' && recordingMode === 'tap') return 'adopt-hold'
  return 'ignore'
}
