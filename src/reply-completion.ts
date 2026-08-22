export type ReplyCompletionEffects = {
  isCurrentSession: () => boolean
  showReply: (content: string) => void
  syncHistory: () => Promise<boolean>
  renderSyncedHistory: () => void
  refreshCandidates: () => Promise<void>
  onSyncError?: (error: unknown) => void
}

export async function completeReply(
  content: string,
  effects: ReplyCompletionEffects,
): Promise<boolean> {
  if (!content || !effects.isCurrentSession()) return false

  // The completed job is the fastest reliable source for the visible reply.
  // History synchronization is only reconciliation and must not gate display.
  effects.showReply(content)

  try {
    const synced = await effects.syncHistory()
    if (!synced || !effects.isCurrentSession()) return true
    effects.renderSyncedHistory()
    await effects.refreshCandidates()
  } catch (error) {
    effects.onSyncError?.(error)
  }

  return true
}
