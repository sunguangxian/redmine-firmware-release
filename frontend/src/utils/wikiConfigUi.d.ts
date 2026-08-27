export interface WikiConfigCategoryForm {
  key: string
  title: string
  hubPage: string
  listPage: string
}

export interface WikiConfigForm {
  mode: 'single_list' | 'multi_list'
  mainPage: string
  releaseDetailMode: 'inline' | 'page'
  textFormat: 'common_mark' | 'markdown'
  releasePagePrefix: string
  categories: WikiConfigCategoryForm[]
}

export function parseWikiConfigText(text: string): WikiConfigForm | null
export function buildWikiConfigText(config: WikiConfigForm): string
export function validateWikiConfigForm(config: WikiConfigForm): string[]
