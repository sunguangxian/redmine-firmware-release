<template>
  <div>
    <el-card class="card">
      <template #header>旧 Changelog 项目升级</template>
      <div class="toolbar">
        <el-select v-model="projectId" placeholder="选择项目" filterable style="width: 320px" @change="clearPreview">
          <el-option v-for="project in projects" :key="project.identifier" :label="`${project.name} (${project.identifier})`" :value="project.identifier" />
        </el-select>
        <el-input v-model="entryPagesText" placeholder="入口页，多个用逗号分隔" style="width: 280px">
          <template #prepend>入口页</template>
        </el-input>
        <el-button :loading="previewing" @click="preview">预览升级</el-button>
        <el-button type="danger" :loading="executing" :disabled="executeDisabled" @click="execute">确认执行升级</el-button>
      </div>

      <el-alert class="card" type="warning" :closable="false" show-icon>
        <template #title>
          执行升级会创建/复用 Redmine Version、把旧 Wiki 附件上传到项目文件、生成新的 Release Wiki 和索引；不会删除旧 Changelog 页面。
        </template>
      </el-alert>

      <el-alert v-if="message" class="card" :type="ok ? 'success' : 'warning'" :closable="false" show-icon>
        <template #title>{{ message }}</template>
      </el-alert>
    </el-card>

    <el-card v-if="previewData" class="card">
      <template #header>升级预览</template>
      <div class="migration-summary">
        <div>型号：{{ previewData.model_count }}</div>
        <div>源页面：{{ previewData.source_page_count }}</div>
        <div>历史版本：{{ previewData.release_count }}</div>
        <div>附件引用：{{ previewData.attachment_ref_count }}</div>
        <div>匹配附件：{{ previewData.matched_attachment_count }}</div>
        <div>新建 Version：{{ previewData.versions_to_create }}</div>
        <div>复用 Version：{{ previewData.existing_versions }}</div>
        <div>新建 Release 页：{{ previewData.release_pages_to_create }}</div>
        <div>更新 Release 页：{{ previewData.existing_release_pages }}</div>
        <div>上传项目文件：{{ previewData.project_files_to_upload }}</div>
        <div>复用项目文件：{{ previewData.existing_project_files }}</div>
      </div>

      <el-alert
        v-for="warning in previewData.warnings"
        :key="warning"
        class="card"
        type="warning"
        :closable="false"
        show-icon
      >
        <template #title>{{ warning }}</template>
      </el-alert>

      <el-table :data="previewData.source_pages" border height="300">
        <el-table-column prop="model" label="型号" width="140" />
        <el-table-column prop="title" label="源 Wiki 页面" min-width="220" />
        <el-table-column prop="release_count" label="版本数" width="100" />
        <el-table-column prop="attachment_ref_count" label="附件引用" width="110" />
        <el-table-column prop="matched_attachment_count" label="已匹配附件" width="120" />
      </el-table>

      <el-table v-if="previewData.problems.length" :data="previewData.problems" border height="260" style="margin-top: 12px">
        <el-table-column prop="level" label="级别" width="100" />
        <el-table-column prop="source_page" label="源页面" width="180" />
        <el-table-column prop="version" label="版本" width="140" />
        <el-table-column prop="message" label="问题" min-width="260" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { errorMessage, executeLegacyMigration, previewLegacyMigration } from '../api/http'
import type { LegacyMigrationPreview, Project } from '../types'

const props = defineProps<{ projects: Project[] }>()
const projectId = ref(props.projects[0]?.identifier || '')
const entryPagesText = ref('Changelog')
const previewData = ref<LegacyMigrationPreview | null>(null)
const previewing = ref(false)
const executing = ref(false)
const message = ref('')
const ok = ref(true)
const executeDisabled = computed(() => !previewData.value || (previewData.value.attachment_ref_count > 0 && !previewData.value.can_read_project_files))

watch(
  () => props.projects,
  (value) => {
    if (!projectId.value && value.length) projectId.value = value[0].identifier
  },
  { immediate: true }
)

function entryPages(): string[] {
  return entryPagesText.value.split(/[,，;\s]+/).map((item) => item.trim()).filter(Boolean)
}

function clearPreview() {
  previewData.value = null
  message.value = ''
}

async function preview() {
  if (!projectId.value) return ElMessage.warning('请选择项目')
  previewing.value = true
  try {
    previewData.value = await previewLegacyMigration({ project_id: projectId.value, entry_pages: entryPages() })
    message.value = `预览完成：识别 ${previewData.value.model_count} 个型号、${previewData.value.release_count} 个历史版本`
    ok.value = !previewData.value.warnings.length && !previewData.value.problems.length
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    previewing.value = false
  }
}

async function execute() {
  if (!projectId.value || !previewData.value) return
  try {
    await ElMessageBox.confirm(
      '将写入 Redmine：创建/复用版本、上传旧附件到项目文件、生成 Release Wiki、重建索引。旧 Changelog 页面不会删除。是否继续？',
      '确认执行旧项目升级',
      { type: 'warning' }
    )
  } catch {
    return
  }

  executing.value = true
  try {
    const result = await executeLegacyMigration({ project_id: projectId.value, entry_pages: entryPages() })
    previewData.value = result.preview
    message.value = result.message
    ok.value = true
    ElMessage.success(result.message)
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    executing.value = false
  }
}
</script>
