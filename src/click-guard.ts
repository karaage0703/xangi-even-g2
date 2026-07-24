export function clickGuardDeadline(now: number, durationMs: number): number {
  return now + Math.max(0, durationMs)
}

export function shouldIgnoreSingleClick(now: number, ignoreUntil: number): boolean {
  return now < ignoreUntil
}
