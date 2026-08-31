<template>
  <div>
    <el-card class="card structure-manager">
      <template #header>
        <div class="structure-heading">
          <div>
            <div>版本管理结构</div>
            <p>先选择项目包含一种还是多种型号，再选择每种型号的版本页面布局。</p>
          </div>
          <el-tag type="info" effect="plain">{{ form.mode === 'multi_list' ? `${form.categories.length} 种型号` : '单型号' }}</el-tag>
        </div>
      </template>

      <div class="toolbar structure-toolbar">
        <el-select v-model="projectId" placeholder="选择项目" filterable style="width: 320px">
          <el-option v-for="project in projects" :key="project.identifier" :label="`${project.name} (${project.identifier})`" :value="project.identifier" />
        </el-select>
        <el-button @click="load">读取当前配置</el-button>
        <span class="toolbar-spacer" />
        <el-select v-model="templateKey" placeholder="快速套用结构" style="width: 280px">
          <el-option v-for="item in templates" :key="String(item[1])" :label="String(item[0])" :value="String(item[1])" />
        </el-select>
        <el-button @click="generate">套用模板</el-button>
      </div>

      <div class="structure-layout">
        <section class="structure-form-panel">
          <div class="section-title">基础设置</div>
          <el-form label-position="top">
            <div class="form-grid">
              <el-form-item label="项目型号结构">
                <el-radio-group v-model="form.mode">
                  <el-radio-button value="single_list">一种型号</el-radio-button>
                  <el-radio-button value="multi_list">多种型号</el-radio-button>
                </el-radio-group>
              </el-form-item>
              <el-form-item label="每种型号的版本页面布局">
                <el-radio-group v-model="form.releaseDetailMode">
                  <el-radio-button value="inline">所有版本一个页面</el-radio-button>
                  <el-radio-button value="page">每个版本独立页面</el-radio-button>
                </el-radio-group>
              </el-form-item>
              <el-form-item label="主页面名称">
                <el-input v-model="form.mainPage" placeholder="例如 Release_Notes" />
              </el-form-item>
              <el-form-item v-if="form.releaseDetailMode === 'page'" label="版本页面命名规则">
                <el-input v-model="form.releasePagePrefix" placeholder="例如 Release_{category}_FW_" />
              </el-form-item>
            </div>
          </el-form>

          <template v-if="form.mode === 'multi_list'">
            <div class="module-section-header">
              <div>
                <div class="section-title">型号列表</div>
                <p>每种型号固定对应一个型号页；不再额外创建 *_List 中间页。</p>
              </div>
              <el-button type="primary" plain @click="addCategory">添加型号</el-button>
            </div>

            <div v-if="!form.categories.length" class="empty-modules">
              暂无型号，请点击“添加型号”。
            </div>
            <div v-for="(item, index) in form.categories" :key="item.id" class="module-card">
              <div class="module-card-header">
                <div class="module-number">{{ index + 1 }}</div>
                <strong>{{ item.title || item.key || `型号 ${index + 1}` }}</strong>
                <div class="module-actions">
                  <el-button text :disabled="index === 0" @click="moveCategory(index, -1)">上移</el-button>
                  <el-button text :disabled="index === form.categories.length - 1" @click="moveCategory(index, 1)">下移</el-button>
                  <el-button text type="danger" @click="removeCategory(index)">删除</el-button>
                </div>
              </div>
              <div class="module-fields">
                <el-form-item label="型号显示名称">
                  <el-input v-model="item.title" placeholder="例如 F864X" />
                </el-form-item>
                <el-form-item label="型号标识">
                  <el-input v-model="item.key" placeholder="例如 F864X" />
                </el-form-item>
                <el-form-item label="型号页面">
                  <el-input :model-value="item.hubPage" placeholder="例如 Release_Notes_F864X" @input="updateCategoryPage(item, String($event))" />
                  <div class="field-tip">集中布局时保存全部版本；独立布局时保存版本索引。</div>
                </el-form-item>
              </div>
            </div>
          </template>
        </section>

        <aside class="structure-preview-panel">
          <div class="section-title">结构预览</div>
          <p class="preview-caption">保存后，工具会按下列关系维护 Wiki 页面。</p>
          <div class="wiki-tree">
            <div class="tree-node tree-root">
              <span class="node-type">主页面</span>
              <strong>{{ form.mainPage || '未填写主页面' }}</strong>
            </div>
            <div v-if="form.mode === 'multi_list'" class="tree-children">
              <div v-for="(item, index) in form.categories" :key="`preview-${item.id}`" class="tree-branch">
                <span class="branch-line" />
                <div class="tree-node">
                  <span class="node-type">型号 {{ index + 1 }}</span>
                  <strong>{{ item.title || item.key || '未命名模块' }}</strong>
                  <small>{{ item.hubPage || '未填写模块页面' }}</small>
                  <div class="list-page">{{ form.releaseDetailMode === 'inline' ? '页内保存全部版本' : '版本索引 → 每个版本独立页面' }}</div>
                </div>
              </div>
            </div>
            <div v-else class="tree-children">
              <div class="tree-branch">
                <span class="branch-line" />
                <div class="tree-node release-storage">
                  <span class="node-type">版本内容</span>
                  <strong>{{ form.releaseDetailMode === 'inline' ? '主页面内保存全部版本' : '主页面索引 → 每个版本独立页面' }}</strong>
                </div>
              </div>
            </div>
          </div>
          <el-alert v-if="formErrors.length" type="warning" :closable="false" show-icon>
            <template #title>还有 {{ formErrors.length }} 项需要完善</template>
            <div v-for="error in formErrors.slice(0, 4)" :key="error">• {{ error }}</div>
          </el-alert>
        </aside>
      </div>
      <el-alert
        v-if="legacyListPages.length"
        class="card"
        type="warning"
        :closable="false"
        show-icon
        :title="`检测到 ${legacyListPages.length} 个旧式 *_List 页面，请先在下方执行一次当前版本布局转换。`"
      />

      <el-collapse class="advanced-editor">
        <el-collapse-item name="raw">
          <template #title>高级：查看或编辑原始配置</template>
          <el-alert type="info" :closable="false" title="一般无需修改这里。手工编辑后，请先应用到上方表单。" />
          <el-input v-model="text" type="textarea" :rows="18" placeholder="Release_Tool_Config 内容" />
          <div class="toolbar raw-actions">
            <el-button @click="applyRawText">应用到表单</el-button>
            <el-button @click="check">检测原始配置</el-button>
          </div>
        </el-collapse-item>
      </el-collapse>

      <div class="toolbar save-actions">
        <el-button type="primary" @click="save">保存结构到项目 Wiki</el-button>
        <el-button :loading="previewing" @click="previewRefresh">预览重建索引</el-button>
        <el-button type="warning" :loading="refreshing" @click="refreshIndex">确认重建索引</el-button>
      </div>
      <el-alert v-if="message" class="card" :closable="false" :type="ok ? 'success' : 'warning'" show-icon>
        <template #title>{{ message }}</template>
      </el-alert>
    </el-card>

    <el-card class="card">
      <template #header>版本页面布局转换</template>
      <p class="preview-caption">只转换“所有版本一个页面 / 每个版本独立页面”，不会改变单型号或多型号结构。</p>
      <div class="toolbar">
        <el-select v-model="targetMode" placeholder="目标版本布局" style="width: 240px">
          <el-option label="所有版本一个页面" value="inline" />
          <el-option label="每个版本独立页面" value="page" />
        </el-select>
        <el-button :loading="previewingConvert" @click="previewConvert">预览转换</el-button>
        <el-button type="warning" :loading="converting" @click="convertMode">确认转换</el-button>
      </div>

      <div v-if="convertPreview" class="release-log">
        <div>项目结构：{{ projectStructureLabel(convertPreview.project_structure) }}（{{ convertPreview.model_count }} 种型号）</div>
        <div>当前内容：{{ layoutLabel(convertPreview.source_mode) }} → 目标：{{ layoutLabel(convertPreview.target_mode) }}</div>
        <div>识别 Release：{{ convertPreview.release_count }} 个</div>
        <div>型号页面：</div>
        <div v-for="page in convertPreview.model_pages" :key="`model-${page}`">- {{ page }}</div>
        <div v-if="!convertPreview.model_pages.length">- {{ form.mainPage }}（单型号主页面）</div>
        <div>将写入页面：</div>
        <div v-for="page in convertPreview.pages_to_write" :key="page">- {{ page }}</div>
        <div v-if="!convertPreview.pages_to_write.length">- 无</div>
        <div>转换完成后清理的旧页面：</div>
        <div v-for="page in convertPreview.pages_to_delete" :key="page">- {{ page }}</div>
        <div v-if="!convertPreview.pages_to_delete.length">- 无</div>
      </div>

      <el-alert
        v-for="item in convertPreview?.warnings || []"
        :key="item"
        class="card"
        type="warning"
        :closable="false"
        show-icon
      >
        <template #title>{{ item }}</template>
      </el-alert>
    </el-card>

    <el-card v-if="refreshPreview" class="card">
      <template #header>索引重建预览</template>
      <div class="toolbar">
        <span>项目：{{ projectStructureLabel(refreshPreview.project_structure) }}</span>
        <span>版本布局：{{ layoutLabel(refreshPreview.version_layout) }}</span>
        <span>主页面：{{ refreshPreview.main_page }}</span>
        <span>Release：{{ refreshPreview.release_count }} 个</span>
      </div>

      <el-alert
        v-for="item in refreshPreview.warnings"
        :key="item"
        class="card"
        type="warning"
        :closable="false"
        show-icon
      >
        <template #title>{{ item }}</template>
      </el-alert>

      <el-table v-if="refreshPreview.categories.length" :data="refreshPreview.categories" border style="margin-bottom: 12px">
        <el-table-column prop="key" label="型号标识" width="140" />
        <el-table-column prop="title" label="型号" min-width="180" />
        <el-table-column prop="hub" label="型号页面" min-width="180" />
        <el-table-column prop="release_count" label="Release 数" width="110" />
      </el-table>

      <div class="release-log">
        <div>将更新页面：</div>
        <div v-for="page in refreshPreview.pages_to_update" :key="page">- {{ page }}</div>
        <div v-if="!refreshPreview.pages_to_update.length">- 无</div>
      </div>

      <el-table v-if="refreshPreview.parents_to_update.length" :data="refreshPreview.parents_to_update" border style="margin-top: 12px">
        <el-table-column prop="page" label="需要调整父页面的 Release" min-width="220" />
        <el-table-column prop="from" label="当前父页面" min-width="180" />
        <el-table-column prop="to" label="目标父页面" min-width="180" />
      </el-table>

      <el-table v-if="refreshPreview.uncategorized.length" :data="refreshPreview.uncategorized" border style="margin-top: 12px">
        <el-table-column prop="page" label="无法归类 Release" min-width="220" />
        <el-table-column prop="version" label="版本" width="160" />
        <el-table-column prop="date" label="日期" width="140" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { checkWikiConfig, convertWikiMode, errorMessage, generateWikiConfig, getWikiConfig, getWikiTemplates, previewWikiModeConvert, previewWikiRefresh, refreshWikiIndex, saveWikiConfig } from '../api/http'
import type { Project, WikiModeConvertPreview, WikiRefreshPreview } from '../types'
import { buildWikiConfigText, parseWikiConfigText, validateWikiConfigForm } from '../utils/wikiConfigUi'
import type { WikiConfigCategoryForm, WikiConfigForm } from '../utils/wikiConfigUi'

const props = defineProps<{ projects: Project[] }>()
const projectId = ref(props.projects[0]?.identifier || '')
const templateKey = ref('single_list')
const templates = ref<Array<[string, string]>>([])
type CategoryRow = WikiConfigCategoryForm & { id: number }
type ConfigFormState = Omit<WikiConfigForm, 'categories'> & { categories: CategoryRow[] }
let nextCategoryId = 1
const form = reactive<ConfigFormState>({
  mode: 'single_list',
  mainPage: 'Release_Notes',
  releaseDetailMode: 'inline',
  textFormat: 'common_mark',
  releasePagePrefix: '',
  categories: [],
})
const text = ref(buildWikiConfigText(form))
const message = ref('')
const ok = ref(true)
const refreshPreview = ref<WikiRefreshPreview | null>(null)
const convertPreview = ref<WikiModeConvertPreview | null>(null)
const targetMode = ref<'inline' | 'page'>('inline')
const previewing = ref(false)
const refreshing = ref(false)
const previewingConvert = ref(false)
const converting = ref(false)
const formErrors = computed(() => validateWikiConfigForm(form))
const legacyListPages = computed(() => form.categories.filter((item) => item.listPage && item.listPage !== item.hubPage))

watch(
  () => props.projects,
  (value) => {
    if (!projectId.value && value.length) projectId.value = value[0].identifier
  },
  { immediate: true }
)

watch(projectId, () => {
  refreshPreview.value = null
  convertPreview.value = null
})

watch(form, () => {
  text.value = buildWikiConfigText(form)
  refreshPreview.value = null
}, { deep: true })

function replaceForm(value: WikiConfigForm) {
  form.mode = value.mode
  form.mainPage = value.mainPage
  form.releaseDetailMode = value.releaseDetailMode
  form.textFormat = value.textFormat
  form.releasePagePrefix = value.releasePagePrefix
  form.categories = value.categories.map((item) => ({ ...item, id: nextCategoryId++ }))
  text.value = buildWikiConfigText(form)
}

function addCategory() {
  const number = form.categories.length + 1
  const hubPage = `${form.mainPage || 'Release_Notes'}_Model${number}`
  form.categories.push({
    id: nextCategoryId++,
    key: `Model${number}`,
    title: `型号 ${number}`,
    hubPage,
    listPage: hubPage,
  })
}

function updateCategoryPage(item: CategoryRow, value: string) {
  const followsModelPage = !item.listPage || item.listPage === item.hubPage
  item.hubPage = value
  if (followsModelPage) item.listPage = value
}

function layoutLabel(mode: string) {
  if (mode === 'inline') return '所有版本一个页面'
  if (mode === 'page') return '每个版本独立页面'
  return '混合布局'
}

function projectStructureLabel(mode: string) {
  return mode === 'multi_model' ? '多型号项目' : '单型号项目'
}

function removeCategory(index: number) {
  form.categories.splice(index, 1)
}

function moveCategory(index: number, offset: number) {
  const target = index + offset
  if (target < 0 || target >= form.categories.length) return
  const [item] = form.categories.splice(index, 1)
  form.categories.splice(target, 0, item)
}

function applyRawText() {
  const parsed = parseWikiConfigText(text.value)
  if (!parsed) {
    ok.value = false
    message.value = '无法识别原始配置，请检查配置标记、结构方式和主页面。'
    return ElMessage.warning(message.value)
  }
  replaceForm(parsed)
  ok.value = true
  message.value = '原始配置已应用到可视化表单。'
  ElMessage.success(message.value)
}

async function generate() {
  if (!projectId.value) return ElMessage.warning('请选择项目')
  try {
    const data = await generateWikiConfig(projectId.value, templateKey.value)
    const parsed = parseWikiConfigText(data.text)
    if (!parsed) throw new Error('模板内容无法转换为可视化配置')
    replaceForm(parsed)
    message.value = data.message
    ok.value = true
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

async function load() {
  if (!projectId.value) return ElMessage.warning('请选择项目')
  try {
    const data = await getWikiConfig(projectId.value)
    text.value = data.text
    message.value = data.message
    const parsed = parseWikiConfigText(data.text)
    if (parsed) {
      replaceForm(parsed)
      ok.value = true
    } else {
      ok.value = false
      if (data.text) message.value = `${data.message}。可在“高级”区域检查原始内容。`
    }
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

async function check() {
  try {
    const data = await checkWikiConfig(text.value)
    message.value = data.message
    ok.value = data.ok
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

async function save() {
  if (!projectId.value) return ElMessage.warning('请选择项目')
  if (formErrors.value.length) {
    ok.value = false
    message.value = formErrors.value.join('\n')
    return ElMessage.warning('请先完善结构配置')
  }
  if (legacyListPages.value.length) {
    return ElMessage.warning('当前仍有旧式 *_List 页面，请先执行下方版本布局转换')
  }
  try {
    text.value = buildWikiConfigText(form)
    const data = await saveWikiConfig(projectId.value, text.value)
    message.value = data.message
    ok.value = true
    ElMessage.success('已保存')
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

async function previewRefresh() {
  if (!projectId.value) return ElMessage.warning('请选择项目')
  previewing.value = true
  try {
    refreshPreview.value = await previewWikiRefresh(projectId.value)
    message.value = `预览完成：当前结构 ${refreshPreview.value.mode}，Release ${refreshPreview.value.release_count} 个`
    ok.value = !refreshPreview.value.warnings.length
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    previewing.value = false
  }
}

async function refreshIndex() {
  if (!projectId.value) return ElMessage.warning('请选择项目')
  if (!refreshPreview.value) {
    await previewRefresh()
    if (!refreshPreview.value) return
  }
  try {
    await ElMessageBox.confirm(
      '将按当前 Release_Tool_Config 重建索引并调整 Release 父页面，不会删除旧 Wiki 页面。是否继续？',
      '确认重建索引',
      { type: 'warning' }
    )
  } catch {
    return
  }
  refreshing.value = true
  try {
    const data = await refreshWikiIndex(projectId.value)
    refreshPreview.value = data.preview
    message.value = data.message
    ok.value = true
    ElMessage.success(data.message)
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    refreshing.value = false
  }
}

async function previewConvert() {
  if (!projectId.value) return ElMessage.warning('请选择项目')
  previewingConvert.value = true
  try {
    convertPreview.value = await previewWikiModeConvert(projectId.value, targetMode.value)
    message.value = convertPreview.value.message
    ok.value = !convertPreview.value.warnings.length
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    previewingConvert.value = false
  }
}

async function convertMode() {
  if (!projectId.value) return ElMessage.warning('请选择项目')
  if (!convertPreview.value || convertPreview.value.target_mode !== targetMode.value) {
    await previewConvert()
    if (!convertPreview.value) return
  }
  try {
    await ElMessageBox.confirm(
      `将转换为“${layoutLabel(targetMode.value)}”、重建型号索引，并清理预览中列出的 ${convertPreview.value.pages_to_delete.length} 个旧页面。是否继续？`,
      '确认版本页面布局转换',
      { type: 'warning' }
    )
  } catch {
    return
  }
  converting.value = true
  try {
    const data = await convertWikiMode(projectId.value, targetMode.value)
    convertPreview.value = data
    refreshPreview.value = null
    message.value = data.message
    ok.value = true
    ElMessage.success(data.message)
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    converting.value = false
  }
}

onMounted(async () => {
  templates.value = await getWikiTemplates()
  if (projectId.value) await load()
})
</script>

<style scoped>
.structure-heading,
.module-section-header,
.module-card-header,
.save-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.structure-heading p,
.module-section-header p,
.preview-caption {
  margin: 5px 0 0;
  color: #7a8798;
  font-size: 12px;
  font-weight: 400;
}

.structure-toolbar {
  padding-bottom: 16px;
  border-bottom: 1px solid #edf1f5;
}

.toolbar-spacer {
  flex: 1;
}

.structure-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.55fr) minmax(300px, 0.8fr);
  gap: 22px;
  align-items: start;
}

.structure-form-panel,
.structure-preview-panel {
  min-width: 0;
}

.structure-preview-panel {
  position: sticky;
  top: 86px;
  padding: 18px;
  border: 1px solid #e1e8f0;
  border-radius: 14px;
  background: linear-gradient(145deg, #f8fbff, #f7fbfa);
}

.section-title {
  color: #2d3d53;
  font-size: 14px;
  font-weight: 750;
}

.module-section-header {
  margin: 10px 0 12px;
}

.module-card {
  margin-bottom: 12px;
  padding: 14px 16px 4px;
  border: 1px solid #e1e7ef;
  border-radius: 13px;
  background: #fbfcfe;
}

.module-card-header {
  justify-content: flex-start;
  margin-bottom: 14px;
}

.module-number {
  display: grid;
  width: 27px;
  height: 27px;
  place-items: center;
  border-radius: 8px;
  background: #eaf2fd;
  color: #2d67b5;
  font-size: 12px;
  font-weight: 800;
}

.module-actions {
  display: flex;
  gap: 2px;
  margin-left: auto;
}

.module-actions :deep(.el-button + .el-button) {
  margin-left: 0;
}

.module-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 14px;
}

.field-tip {
  margin-top: 5px;
  color: #929dad;
  font-size: 11px;
  line-height: 1.4;
}

.empty-modules {
  margin-bottom: 12px;
  padding: 28px;
  border: 1px dashed #cfd9e6;
  border-radius: 13px;
  color: #8490a2;
  text-align: center;
}

.wiki-tree {
  margin: 16px 0;
}

.tree-node {
  display: grid;
  gap: 3px;
  padding: 11px 13px;
  border: 1px solid #dce5ef;
  border-radius: 11px;
  background: #fff;
  box-shadow: 0 4px 12px rgba(45, 67, 94, 0.045);
}

.tree-root {
  border-color: #bcd2ee;
  background: #f0f6ff;
}

.node-type {
  color: #7890ad;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.05em;
}

.tree-node strong {
  overflow-wrap: anywhere;
  color: #30445e;
  font-size: 13px;
}

.tree-node small,
.list-page {
  overflow-wrap: anywhere;
  color: #718096;
  font-size: 11px;
}

.list-page {
  margin-top: 4px;
  padding-top: 6px;
  border-top: 1px dashed #e0e6ed;
  color: #347166;
}

.tree-children {
  margin-left: 18px;
  padding-left: 17px;
  border-left: 2px solid #d9e3ef;
}

.tree-branch {
  position: relative;
  padding-top: 12px;
}

.branch-line {
  position: absolute;
  top: 31px;
  left: -17px;
  width: 17px;
  border-top: 2px solid #d9e3ef;
}

.advanced-editor {
  margin-top: 20px;
  border-top: 1px solid #edf1f5;
}

.advanced-editor :deep(.el-alert) {
  margin-bottom: 10px;
}

.advanced-editor :deep(textarea) {
  font-family: Consolas, "Liberation Mono", monospace;
  font-size: 12px;
}

.raw-actions {
  margin: 10px 0 0;
}

.save-actions {
  justify-content: flex-start;
  margin-top: 18px;
  margin-bottom: 0;
  padding-top: 18px;
  border-top: 1px solid #edf1f5;
}

@media (max-width: 980px) {
  .structure-layout {
    grid-template-columns: 1fr;
  }

  .structure-preview-panel {
    position: static;
  }
}

@media (max-width: 680px) {
  .module-fields {
    grid-template-columns: 1fr;
  }

  .toolbar-spacer {
    display: none;
  }

  .structure-toolbar :deep(.el-select) {
    width: 100% !important;
  }

  .module-card-header {
    flex-wrap: wrap;
  }

  .module-actions {
    width: 100%;
    margin-left: 0;
  }
}
</style>
