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
      </div>
      <el-input v-model="text" type="textarea" :rows="24" placeholder="Release_Tool_Config 内容" />
      <el-alert v-if="message" class="card" :closable="false" :type="ok ? 'success' : 'warning'" show-icon>
        <template #title>{{ message }}</template>
      </el-alert>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { checkWikiConfig, errorMessage, generateWikiConfig, getWikiConfig, getWikiTemplates, saveWikiConfig } from '../api/http'
import type { Project } from '../types'

const props = defineProps<{ projects: Project[] }>()
const projectId = ref(props.projects[0]?.identifier || '')
const templateKey = ref('single_list')
const templates = ref<Array<[string, string]>>([])
const text = ref('')
const message = ref('')
const ok = ref(true)

watch(
  () => props.projects,
  (value) => {
    if (!projectId.value && value.length) projectId.value = value[0].identifier
  },
  { immediate: true }
)

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

onMounted(async () => {
  templates.value = await getWikiTemplates()
})
</script>
