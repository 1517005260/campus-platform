<script setup lang="ts">
import { ElMessage } from "element-plus";
import { onMounted, ref } from "vue";

import { fmtTime } from "@/core/format";
import { showError } from "@/core/http";

import { roomApi, type ApplicationForApprover } from "../api";

const items = ref<ApplicationForApprover[]>([]);

async function load() {
  try {
    const { data } = await roomApi.GET("/api/v1/room/approvals/todo", { params: { query: { page: 1, size: 50 } } });
    items.value = data!.items;
  } catch (e) {
    showError(e);
  }
}

async function act(row: ApplicationForApprover, action: "approve" | "reject") {
  try {
    await roomApi.POST(`/api/v1/room/applications/{application_id}/${action}`, {
      params: { path: { application_id: row.id } },
      body: {},
    });
    ElMessage.success(action === "approve" ? "已通过" : "已驳回");
    await load();
  } catch (e) {
    showError(e);
  }
}

onMounted(load);
</script>

<template>
  <el-table :data="items">
    <el-table-column label="申请人" prop="applicant.name" width="110" />
    <el-table-column label="教室" prop="room_id" width="80" />
    <el-table-column label="开始">
      <template #default="{ row }">{{ fmtTime(row.start_at) }}</template>
    </el-table-column>
    <el-table-column label="用途" prop="purpose" />
    <el-table-column label="将取消的个人预约" prop="affected_reservations" width="150" />
    <el-table-column width="170">
      <template #default="{ row }">
        <el-button size="small" type="primary" @click="act(row, 'approve')">通过</el-button>
        <el-button size="small" type="danger" @click="act(row, 'reject')">驳回</el-button>
      </template>
    </el-table-column>
  </el-table>
</template>
