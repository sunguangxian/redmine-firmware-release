const BEGIN = '<!-- RELEASE_CONFIG_BEGIN -->'
const END = '<!-- RELEASE_CONFIG_END -->'

function valueAfterColon(line) {
  const value = line.slice(line.indexOf(':') + 1).trim()
  if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
    return value.slice(1, -1)
  }
  return value
}

export function parseWikiConfigText(text) {
  const markerStart = text.indexOf(BEGIN)
  const markerEnd = text.indexOf(END)
  let block = markerStart >= 0 && markerEnd > markerStart
    ? text.slice(markerStart + BEGIN.length, markerEnd)
    : text
  const fence = block.match(/```(?:yaml|yml)?\s*([\s\S]*?)```/i)
  if (fence) block = fence[1]

  const config = {
    mode: '',
    mainPage: '',
    releaseDetailMode: 'inline',
    textFormat: 'common_mark',
    releasePagePrefix: '',
    categories: [],
  }
  let category = null
  let inCategories = false

  for (const rawLine of block.split(/\r?\n/)) {
    const line = rawLine.trim()
    if (!line || line.startsWith('#') || line.startsWith('```')) continue
    if (line === 'categories:') {
      inCategories = true
      category = null
      continue
    }
    if (inCategories && line.startsWith('- ')) {
      category = { key: '', title: '', hubPage: '', listPage: '' }
      config.categories.push(category)
      const item = line.slice(2).trim()
      if (item.startsWith('key:')) category.key = valueAfterColon(item)
      continue
    }
    if (!line.includes(':')) continue
    const key = line.slice(0, line.indexOf(':')).trim()
    const value = valueAfterColon(line)
    if (inCategories && category) {
      if (key === 'key') category.key = value
      else if (key === 'title') category.title = value
      else if (key === 'hub_page' || key === 'hub') category.hubPage = value
      else if (key === 'list_page' || key === 'list') category.listPage = value
      continue
    }
    inCategories = false
    if (key === 'mode') config.mode = value
    else if (key === 'main_page') config.mainPage = value
    else if (key === 'release_detail_mode') config.releaseDetailMode = value || 'inline'
    else if (key === 'text_format') config.textFormat = value || 'common_mark'
    else if (key === 'release_page_prefix') config.releasePagePrefix = value
  }

  if (!['single_list', 'multi_list'].includes(config.mode) || !config.mainPage) return null
  if (config.mode === 'multi_list' && !config.categories.length) return null
  return config
}

function categoryYaml(item) {
  return [
    `  - key: ${item.key.trim()}`,
    `    title: ${item.title.trim() || item.key.trim()}`,
    `    hub_page: ${item.hubPage.trim()}`,
    `    list_page: ${(item.listPage.trim() || item.hubPage.trim())}`,
  ].join('\n')
}

export function buildWikiConfigText(config) {
  const isMulti = config.mode === 'multi_list'
  const mainPage = config.mainPage.trim()
  const categories = isMulti ? config.categories : []
  const detailIsPage = config.releaseDetailMode === 'page'
  const structure = isMulti
    ? [mainPage, ...categories.map((item, index) => {
        const branch = index === categories.length - 1 ? '└──' : '├──'
        const list = item.listPage.trim() || item.hubPage.trim()
        const legacy = list && list !== item.hubPage.trim() ? ` [旧列表页: ${list}]` : ''
        const detail = detailIsPage ? ' → 每个版本独立页面' : ' → 页内保存全部版本'
        return `${branch} ${item.title.trim() || item.key.trim()} (${item.hubPage.trim()})${detail}${legacy}`
      })].join('\n')
    : `${mainPage}\n└── ${detailIsPage ? '每个版本独立页面' : '页内保存全部版本'}`
  const prefix = detailIsPage && config.releasePagePrefix.trim()
    ? `release_page_prefix: ${config.releasePagePrefix.trim()}\n`
    : ''
  const categoryBlock = isMulti
    ? `categories:\n${categories.map(categoryYaml).join('\n\n')}\n`
    : ''

  return `# Release Tool Config

本页面由 Release 工具的“结构管理”功能维护，请不要直接修改配置区。

## 当前 Wiki 结构

\`\`\`text
${structure}
\`\`\`

## 工具配置

${BEGIN}
\`\`\`yaml
mode: ${config.mode}
text_format: ${config.textFormat || 'common_mark'}
main_page: ${mainPage}
release_detail_mode: ${config.releaseDetailMode}
${prefix}${categoryBlock}\`\`\`
${END}
`
}

export function validateWikiConfigForm(config) {
  const errors = []
  if (!config.mainPage.trim()) errors.push('请填写主页面名称')
  if (config.mode === 'multi_list') {
    if (!config.categories.length) errors.push('多模块结构至少需要一个模块')
    const keys = new Set()
    config.categories.forEach((item, index) => {
      const label = `模块 ${index + 1}`
      if (!item.key.trim()) errors.push(`${label}：请填写模块标识`)
      else if (keys.has(item.key.trim().toLowerCase())) errors.push(`${label}：模块标识不能重复`)
      else keys.add(item.key.trim().toLowerCase())
      if (!item.title.trim()) errors.push(`${label}：请填写显示名称`)
      if (!item.hubPage.trim()) errors.push(`${label}：请填写模块页面`)
    })
  }
  return errors
}
