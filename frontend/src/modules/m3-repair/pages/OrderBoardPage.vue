<script setup lang="ts">
import { onMounted, ref } from "vue";

import { fmtTime } from "@/core/format";
import { showError } from "@/core/http";

import { repairApi, type WorkOrder } from "../api";

const items = ref<WorkOrder[]>([]);

onMounted(async () => {
  try {
    const { data } = await repairApi.GET("/api/v1/repair/orders", { params: { query: { page: 1, size: 50 } } });
    items.value = data!.items;
  } catch (e) {
    showError(e);
  }
});
</script>

<template>
  <el-table :data="items">
    <el-table-column label="工单号" prop="id" width="90" />
    <el-table-column label="报修人" prop="reporter.name" width="110" />
    <el-table-column label="教室" prop="room_id" width="80" />
    <el-table-column label="分类" prop="category" width="100" />
    <el-table-column label="状态" prop="status" width="150" />
    <el-table-column label="下架教室" width="100">
      <template #default="{ row }">{{ row.blocks_room ? "是" : "否" }}</template>
    </el-table-column>
    <el-table-column label="截止">
      <template #default="{ row }">{{ fmtTime(row.deadline_at) }}</template>
    </el-table-column>
    <el-table-column label="升级" prop="escalation_level" width="70" />
  </el-table>
</template>
