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
import { checkWikiConfig, errorMessage, generateWikiConfig, getWikiConfig, getWikiTemplates, previewWikiRefresh, refreshWikiIndex, saveWikiConfig } from '../api/http'
import type { Project, WikiRefreshPreview } from '../types'

const props = defineProps<{ projects: Project[] }>()
const projectId = ref(props.projects[0]?.identifier || '')
const templateKey = ref('single_list')
const templates = ref<Array<[string, string]>>([])
const text = ref('')
const message = ref('')
const ok = ref(true)
const refreshPreview = ref<WikiRefreshPreview | null>(null)
const previewing = ref(false)
const refreshing = ref(false)

watch(
  () => props.projects,
  (value) => {
    if (!projectId.value && value.length) projectId.value = value[0].identifier
  },
  { immediate: true }
)

watch(projectId, () => {
  refreshPreview.value = null
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

onMounted(async () => {
  templates.value = await getWikiTemplates()
})
</script>
