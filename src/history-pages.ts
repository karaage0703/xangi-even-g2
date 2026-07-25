export function virtualPageCount(contentPageCount: number, candidateCount: number): number {
  return Math.max(0, contentPageCount) + Math.max(0, candidateCount)
}

export function candidateIndexForPage(
  pageIndex: number,
  contentPageCount: number,
  candidateCount: number,
): number | null {
  const index = pageIndex - Math.max(0, contentPageCount)
  return index >= 0 && index < Math.max(0, candidateCount) ? index : null
}
