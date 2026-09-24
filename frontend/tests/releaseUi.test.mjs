import assert from 'node:assert/strict'
import test from 'node:test'

import {
  duplicateFileNames,
  friendlyReleaseError,
  releaseNameFromAttachments,
  mergeContactPeople,
  publishedAttachmentIssue,
  validateReleaseInput,
} from '../src/utils/releaseUi.js'

function file(name, size = 10) {
  return { name, size }
}

test('releaseNameFromAttachments parses model version and date', () => {
  assert.equal(releaseNameFromAttachments(['DP580_V5.3.8.3_20260705.bin'], 'V1', '2026-01-01'), 'DP580 V5.3.8.3 20260705')
})

test('duplicateFileNames detects duplicate selected files', () => {
  assert.deepEqual([...duplicateFileNames([file('fw.bin'), file('FW.bin'), file('other.bin')])], ['fw.bin'])
})

test('validateReleaseInput reports frontend validation errors', () => {
  const errors = validateReleaseInput({ projectId: '', versionName: '', releaseDate: '2026/07/05', commit: '', changelog: '', files: [file('a.bin'), file('A.bin')] })
  assert.ok(errors.includes('请选择项目'))
  assert.ok(errors.includes('请填写版本号'))
  assert.ok(errors.includes('发布日期格式必须是 YYYY-MM-DD'))
  assert.ok(errors.some((item) => item.includes('重名文件')))
})

test('mergeContactPeople keeps cc-only and template-only addresses', () => {
  const people = mergeContactPeople([
    [{ name: '在职', email: 'stay@example.com' }],
    ['stay@example.com'],
    [{ name: '离职', email: 'Left@example.com' }],
    [{ email: 'left@example.com' }],
  ])
  assert.deepEqual(people.map((item) => item.email), ['stay@example.com', 'Left@example.com'])
  assert.equal(people[1].name, '离职')
})

test('publishedAttachmentIssue requires every firmware file to have a download url', () => {
  assert.equal(publishedAttachmentIssue([]), '该版本没有可随邮件发送的固件附件')
  assert.match(publishedAttachmentIssue([{ filename: 'fw.bin' }, { filename: 'boot.bin', url: '/attachments/download/2/boot.bin' }]), /fw\.bin/)
  assert.equal(publishedAttachmentIssue([{ filename: 'fw.bin', url: '/attachments/download/1/fw.bin' }]), '')
})

test('friendlyReleaseError maps publish lock and wiki conflict errors', () => {
  assert.match(friendlyReleaseError('当前项目版本正在发布中，请稍后再试'), /正在被其他用户发布/)
  assert.match(friendlyReleaseError('Wiki 页面已被其他用户修改：Release_A'), /刷新版本详情/)
})
