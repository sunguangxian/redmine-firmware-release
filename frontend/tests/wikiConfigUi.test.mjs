import assert from 'node:assert/strict'
import test from 'node:test'

import { buildWikiConfigText, parseWikiConfigText, validateWikiConfigForm } from '../src/utils/wikiConfigUi.js'

test('multi-module config round trips through the visual form model', () => {
  const form = {
    mode: 'multi_list',
    mainPage: 'Release_Notes',
    releaseDetailMode: 'inline',
    textFormat: 'common_mark',
    releasePagePrefix: '',
    categories: [
      { key: 'Regular', title: '常规版本', hubPage: 'Release_Notes_Regular', listPage: 'Release_Notes_Regular' },
      { key: 'Record', title: '录音版本', hubPage: 'Release_Notes_Record', listPage: 'Release_Notes_Record_List' },
    ],
  }
  const text = buildWikiConfigText(form)
  assert.deepEqual(parseWikiConfigText(text), form)
  assert.match(text, /常规版本 \(Release_Notes_Regular\)/)
  assert.match(text, /录音版本 \(Release_Notes_Record → Release_Notes_Record_List\)/)
})

test('form validation reports incomplete and duplicate modules', () => {
  const errors = validateWikiConfigForm({
    mode: 'multi_list',
    mainPage: '',
    releaseDetailMode: 'inline',
    textFormat: 'common_mark',
    releasePagePrefix: '',
    categories: [
      { key: 'Radio', title: '', hubPage: '', listPage: '' },
      { key: 'radio', title: 'Radio 2', hubPage: 'Release_Radio_2', listPage: '' },
    ],
  })
  assert.ok(errors.includes('请填写主页面名称'))
  assert.ok(errors.some((item) => item.includes('显示名称')))
  assert.ok(errors.some((item) => item.includes('模块页面')))
  assert.ok(errors.some((item) => item.includes('模块标识不能重复')))
})
