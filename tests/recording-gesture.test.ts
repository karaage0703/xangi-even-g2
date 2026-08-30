import assert from 'node:assert/strict'
import test from 'node:test'

import { longPressAction, recordingPrompt } from '../src/recording-gesture.ts'

test('shows an animated listening prompt only for hold recording', () => {
  assert.equal(recordingPrompt('hold', 0), '長押し中入力\nListening .\n指を離すと送信。')
  assert.equal(recordingPrompt('hold', 1), '長押し中入力\nListening ..\n指を離すと送信。')
  assert.equal(recordingPrompt('hold', 2), '長押し中入力\nListening ...\n指を離すと送信。')
  assert.equal(recordingPrompt('hold', 3), recordingPrompt('hold', 0))
  assert.equal(recordingPrompt('tap', 2), '録音中… 話してください。\nもう一度タップで送信。')
})

test('starts hold recording from an idle terminal', () => {
  assert.equal(longPressAction('start', 'ready', 'terminal', null), 'start-hold')
})

test('adopts hold mode if a click event started recording first', () => {
  assert.equal(longPressAction('start', 'recording', 'terminal', 'tap'), 'adopt-hold')
})

test('submits only a recording started or adopted by a hold', () => {
  assert.equal(longPressAction('release', 'recording', 'terminal', 'hold'), 'submit')
  assert.equal(longPressAction('release', 'recording', 'terminal', 'tap'), 'ignore')
})

test('ignores long press outside an idle or recording terminal', () => {
  assert.equal(longPressAction('start', 'ready', 'sessions', null), 'ignore')
  assert.equal(longPressAction('start', 'confirming', 'terminal', null), 'ignore')
  assert.equal(longPressAction('release', 'ready', 'terminal', null), 'ignore')
})
