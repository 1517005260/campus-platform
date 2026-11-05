<script setup lang="ts">
import { ElMessage, ElMessageBox } from "element-plus";
import { onMounted, ref } from "vue";

import { showError } from "@/core/http";

import { commonApi, type DeptOut } from "../api";

const depts = ref<DeptOut[]>([]);
const loading = ref(false);

async function load() {
  loading.value = true;
  try {
    const { data } = await commonApi.GET("/api/v1/admin/depts");
    depts.value = data!;
  } catch (e) {
    showError(e);
  } finally {
    loading.value = false;
  }
}

async function askName(title: string, current = ""): Promise<string | null> {
  try {
    const { value } = await ElMessageBox.prompt("院系名称", title, {
      inputValue: current,
      inputValidator: (v) => (v?.trim() ? true : "名称不能为空"),
    });
    return value.trim();
  } catch {
    return null; // 取消
  }
}

async function create() {
  const name = await askName("新建院系");
  if (!name) return;
  try {
    await commonApi.POST("/api/v1/admin/depts", { body: { name } });
    ElMessage.success("已新建");
    await load();
  } catch (e) {
    showError(e);
  }
}

async function rename(d: DeptOut) {
  const name = await askName("院系改名", d.name);
  if (!name || name === d.name) return;
  try {
    await commonApi.PATCH("/api/v1/admin/depts/{dept_id}", { params: { path: { dept_id: d.id } }, body: { name } });
    ElMessage.success("已改名");
    await load();
  } catch (e) {
    showError(e);
  }
}

onMounted(load);
</script>

<template>
  <div class="toolbar">
    <el-text type="info">院系被自习室、审批流按 ID 引用，因此只能新建和改名，不能删除。</el-text>
    <el-button type="primary" @click="create">新建院系</el-button>
  </div>
  <el-table :data="depts" v-loading="loading">
    <el-table-column label="ID" prop="id" width="80" />
    <el-table-column label="名称" prop="name" />
    <el-table-column width="100">
      <template #default="{ row }">
        <el-button size="small" link type="primary" @click="rename(row)">改名</el-button>
      </template>
    </el-table-column>
  </el-table>
</template>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
</style>
