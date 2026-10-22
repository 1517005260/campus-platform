<script setup lang="ts">
import { onMounted, ref } from "vue";

import { fmtTime } from "@/core/format";
import { showError } from "@/core/http";

import { roomApi, type Application } from "../api";

const items = ref<Application[]>([]);
const eligible = ref<{ eligible: boolean; reasons: string[] } | null>(null);

onMounted(async () => {
  try {
    const [mine, elig] = await Promise.all([
      roomApi.GET("/api/v1/room/applications/mine", { params: { query: { page: 1, size: 50 } } }),
      roomApi.GET("/api/v1/room/eligibility"),
    ]);
    items.value = mine.data!.items;
    eligible.value = elig.data!;
  } catch (e) {
    showError(e);
  }
});
</script>

<template>
  <el-alert
    v-if="eligible && !eligible.eligible"
    type="warning"
    :title="`当前不能申请：${eligible.reasons.join('；')}`"
    :closable="false"
    style="margin-bottom: 12px"
  />
  <el-table :data="items">
    <el-table-column label="申请号" prop="id" width="90" />
    <el-table-column label="教室" prop="room_id" width="90" />
    <el-table-column label="开始">
      <template #default="{ row }">{{ fmtTime(row.start_at) }}</template>
    </el-table-column>
    <el-table-column label="用途" prop="purpose" />
    <el-table-column label="状态" prop="status" width="110" />
    <el-table-column label="审批进度" width="110">
      <template #default="{ row }">{{ row.current_level }} / {{ row.total_levels }}</template>
    </el-table-column>
  </el-table>
</template>
