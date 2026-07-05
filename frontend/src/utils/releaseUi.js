export function splitEmails(text) {
  return String(text || '')
    .split(/[;,\s]+/)
    .map((item) => item.trim())
    .filter(Boolean)
}

export function mergeEmails(groups) {
  const seen = new Set()
  const result = []
  groups.flat().forEach((email) => {
    const value = String(email || '').trim()
    const key = value.toLowerCase()
    if (value && !seen.has(key)) {
      seen.add(key)
      result.push(value)
    }
  })
  return result
}

export function changelogLines(text) {
  return String(text || '').split(/\r?\n/).map((item) => item.trim()).filter(Boolean)
}

export function uniqueItems(items) {
  const seen = new Set()
  const result = []
  items.forEach((item) => {
    const value = String(item || '').trim()
    const key = value.toLowerCase()
    if (value && !seen.has(key)) {
      seen.add(key)
      result.push(value)
    }
  })
  return result
}

export function formatBytes(size) {
  const value = Number(size || 0)
  if (value >= 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MB`
  if (value >= 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${value} B`
}

export function duplicateFileNames(files) {
  const counts = new Map()
  ;(files || []).forEach((file) => {
    const name = String(file?.name || '').trim().toLowerCase()
    if (!name) return
    counts.set(name, (counts.get(name) || 0) + 1)
  })
  return new Set([...counts.entries()].filter(([, count]) => count > 1).map(([name]) => name))
}

export function selectedFileRows(files) {
  const duplicates = duplicateFileNames(files)
  return (files || []).map((file) => ({
    name: file.name,
    size: file.size || 0,
    sizeText: formatBytes(file.size || 0),
    duplicate: duplicates.has(String(file.name || '').trim().toLowerCase()),
  }))
}

export function totalFileSize(files) {
  return (files || []).reduce((sum, file) => sum + Number(file?.size || 0), 0)
}

export function releaseNameFromAttachments(names, fallbackVersion, fallbackDate) {
  const models = []
  let parsedVersion = ''
  let parsedDate = ''
  ;(names || []).forEach((filename) => {
    const stem = String(filename || '').replace(/\.[A-Za-z0-9]+$/, '')
    const parts = stem.split('_').filter(Boolean)
    const versionIndex = parts.findIndex((part) => /^V?\d+(?:\.\d+)+$/i.test(part))
    const dateIndex = parts.findIndex((part) => /^\d{8}$|^\d{4}-\d{2}-\d{2}$/.test(part))
    if (versionIndex > 0) {
      const model = parts.slice(0, versionIndex).join('_')
      if (model) models.push(model)
      if (!parsedVersion) parsedVersion = parts[versionIndex]
      if (dateIndex > versionIndex && !parsedDate) parsedDate = parts[dateIndex]
    } else if (stem) {
      models.push(stem)
    }
  })
  const cleanModels = uniqueItems(models)
  const modelText = cleanModels.length > 4 ? `${cleanModels.slice(0, 4).join('/')} 等${cleanModels.length}个机型` : cleanModels.join('/')
  return [modelText, parsedVersion || fallbackVersion, parsedDate || String(fallbackDate || '').replace(/-/g, '')].filter(Boolean).join(' ')
}

export function buildMailSubject(scope, names, versionName, releaseDate) {
  const releaseName = releaseNameFromAttachments(names, versionName, releaseDate)
  return scope === 'external' ? `Firmware Release ${releaseName}` : `固件版本发布 ${releaseName}`
}

export function buildMailBody(scope, names, versionName, releaseDate, commit, changelogText) {
  const releaseName = releaseNameFromAttachments(names, versionName, releaseDate)
  const changelog = changelogLines(changelogText).map((item, index) => `${index + 1}. ${item}`).join('\n') || '（无）'
  const attachments = (names || []).map((name) => `- ${name}`).join('\n') || (scope === 'external' ? '（本次邮件未附加文件，请联系相关人员获取固件文件）' : '（本次邮件未附加文件，请查看 Redmine 项目文件）')
  if (scope === 'external') {
    return ['您好，', '', '固件版本已发布，请查收。', '', `版本：${releaseName}`, `发布日期：${releaseDate}`, '', `变更说明：\n${changelog}`, '', `附件：\n${attachments}`, '', '如有问题，请联系技术支持人员。'].join('\n')
  }
  return ['固件版本已发布。', '', `版本：${releaseName}`, `发布日期：${releaseDate}`, `Commit：${commit}`, '', `变更说明：\n${changelog}`, '', `附件：\n${attachments}`, '', 'Wiki：{{wiki_url}}', '项目文件：{{files_url}}'].join('\n')
}

export function validateReleaseInput(input) {
  const errors = []
  if (!String(input.projectId || '').trim()) errors.push('请选择项目')
  if (input.requireSelectedVersion && !String(input.selectedWikiTitle || '').trim()) errors.push('请选择要编辑的版本')
  if (!String(input.versionName || '').trim()) errors.push('请填写版本号')
  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(input.releaseDate || '').trim())) errors.push('发布日期格式必须是 YYYY-MM-DD')
  if (!String(input.commit || '').trim()) errors.push('请填写 Commit')
  if (!changelogLines(input.changelog).length) errors.push('请填写至少一条变更说明')
  const duplicates = duplicateFileNames(input.files || [])
  if (duplicates.size) errors.push(`选择的附件有重名文件：${[...duplicates].join(', ')}`)
  if (input.noticeEnabled) {
    const recipients = mergeEmails([input.mailTo || [], splitEmails(input.manualMailTo || '')])
    if (!recipients.length) errors.push('请填写或选择至少一个收件人')
    if (!String(input.mailSubject || '').trim()) errors.push('请先生成或填写邮件主题')
    if (!String(input.mailBody || '').trim()) errors.push('请先生成或填写邮件正文')
  }
  return errors
}

export function friendlyReleaseError(message) {
  const text = String(message || '')
  if (text.includes('正在发布中') || text.includes('发布锁')) {
    return '该项目版本正在被其他用户发布，请稍后刷新列表后再试。'
  }
  if (text.includes('Wiki 页面已被其他用户修改')) {
    return 'Wiki 页面已被其他用户修改。请先刷新版本详情，确认内容后重新发布。'
  }
  if (text.includes('Network Error')) return '无法连接后端服务，请检查服务是否启动或网络是否可用。'
  if (text.includes('timeout')) return '请求超时，请稍后重试；如果正在发布大文件，请检查后端日志。'
  return text
}

export function hasReleaseDraft(input) {
  return Boolean(
    String(input.versionName || '').trim() ||
    String(input.commit || '').trim() ||
    String(input.changelog || '').trim() ||
    String(input.productLine || '').trim() ||
    (input.files || []).length ||
    input.noticeEnabled ||
    String(input.mailSubject || '').trim() ||
    String(input.mailBody || '').trim()
  )
}
