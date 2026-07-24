import assert from 'node:assert/strict'
import test from 'node:test'
import { candidateIndexForPage, virtualPageCount } from '../src/history-pages.ts'

test('allocates one virtual page per reply candidate', () => {
  assert.equal(virtualPageCount(5, 3), 8)
  assert.equal(candidateIndexForPage(5, 5, 3), 0)
  assert.equal(candidateIndexForPage(6, 5, 3), 1)
  assert.equal(candidateIndexForPage(7, 5, 3), 2)
})

test('does not select a candidate on content or out-of-range pages', () => {
  assert.equal(candidateIndexForPage(4, 5, 3), null)
  assert.equal(candidateIndexForPage(8, 5, 3), null)
})
