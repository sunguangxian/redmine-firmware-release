<template>
  <div>
    <el-card class="card">
      <div class="toolbar">
        <el-select v-model="projectId" placeholder="选择项目" filterable style="width: 320px">
          <el-option v-for="project in projects" :key="project.identifier" :label="`${project.name} (${project.identifier})`" :value="project.identifier" />
        </el-select>
        <el-select v-model="templateKey" placeholder="结构模板" style="width: 280px">
          <el-option v-for="item in templates" :key="String(item[1])" :label="String(item[0])" :value="String(item[1])" />
        </el-select>
        <el-button @click="generate">生成模板</el-button>
        <el-button @click="load">读取当前配置</el-button>
        <el-button @click="check">检测配置</el-button>
        <el-button type="primary" @click="save">保存到项目 Wiki</el-button>
        <el-button :loading="previewing" @click="previewRefresh">预览重建索引</el-button>
        <el-button type="warning" :loading="refreshing" @click="refreshIndex">确认重建索引</el-button>
      </div>
      <el-input v-model="text" type="textarea" :rows="24" placeholder="Release_Tool_Config 内容" />
      <el-alert v-if="message" class="card" :closable="false" :type="ok ? 'success' : 'warning'" show-icon>
        <template #title>{{ message }}</template>
      </el-alert>
    </el-card>

    <el-card class="card">
      <template #header>Release page / inline 互转</template>
      <div class="toolbar">
        <el-select v-model="targetMode" placeholder="目标版本模式" style="width: 180px">
          <el-option label="Inline 内联模式" value="inline" />
          <el-option label="Page 独立页面模式" value="page" />
        </el-select>
        <el-button :loading="previewingConvert" @click="previewConvert">预览转换</el-button>
        <el-button type="warning" :loading="converting" @click="convertMode">确认转换</el-button>
      </div>

      <div v-if="convertPreview" class="release-log">
        <div>配置模式：{{ convertPreview.current_mode }}；实际源模式：{{ convertPreview.source_mode }} -> 目标模式：{{ convertPreview.target_mode }}</div>
        <div>识别 Release：{{ convertPreview.release_count }} 个</div>
        <div>将写入页面：</div>
        <div v-for="page in convertPreview.pages_to_write" :key="page">- {{ page }}</div>
        <div v-if="!convertPreview.pages_to_write.length">- 无</div>
        <div>将删除旧列表页：</div>
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
        <span>结构：{{ refreshPreview.mode }}</span>
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
        <el-table-column prop="key" label="分类" width="140" />
        <el-table-column prop="title" label="标题" min-width="180" />
        <el-table-column prop="hub" label="Hub 页面" min-width="180" />
        <el-table-column prop="list_page" label="列表页面" min-width="180" />
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
import { onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { checkWikiConfig, convertWikiMode, errorMessage, generateWikiConfig, getWikiConfig, getWikiTemplates, previewWikiModeConvert, previewWikiRefresh, refreshWikiIndex, saveWikiConfig } from '../api/http'
import type { Project, WikiModeConvertPreview, WikiRefreshPreview } from '../types'

const props = defineProps<{ projects: Project[] }>()
const projectId = ref(props.projects[0]?.identifier || '')
const templateKey = ref('single_list')
const templates = ref<Array<[string, string]>>([])
const text = ref('')
const message = ref('')
const ok = ref(true)
const refreshPreview = ref<WikiRefreshPreview | null>(null)
const convertPreview = ref<WikiModeConvertPreview | null>(null)
const targetMode = ref<'inline' | 'page'>('inline')
const previewing = ref(false)
const refreshing = ref(false)
const previewingConvert = ref(false)
const converting = ref(false)

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

async function generate() {
  if (!projectId.value) return ElMessage.warning('请选择项目')
  try {
    const data = await generateWikiConfig(projectId.value, templateKey.value)
    text.value = data.text
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
    ok.value = Boolean(data.text)
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
  try {
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
      '将把当前 Release 内容复制为目标版本模式、切换 Release_Tool_Config 并重建索引；page 转 inline 会删除旧列表页，但不会删除原有 Release 详情页或 inline 块。是否继续？',
      '确认 Release 模式转换',
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
})
</script>
