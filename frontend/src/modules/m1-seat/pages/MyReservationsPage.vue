<script setup lang="ts">
import { ElMessage, ElMessageBox } from "element-plus";
import { onMounted, ref } from "vue";

import { fmtTime } from "@/core/format";
import { showError } from "@/core/http";

import { seatApi, type ReservationDetail } from "../api";

const items = ref<ReservationDetail[]>([]);
const loading = ref(false);

const statusLabel: Record<string, string> = {
  booked: "已预约",
  checked_in: "已签到",
  completed: "已完成",
  cancelled: "已取消",
  no_show: "未签到（违约）",
};

async function load() {
  loading.value = true;
  try {
    const { data } = await seatApi.GET("/api/v1/seat/reservations/mine", { params: { query: { page: 1, size: 50 } } });
    items.value = data!.items;
  } catch (e) {
    showError(e);
  } finally {
    loading.value = false;
  }
}

async function cancel(r: ReservationDetail) {
  await ElMessageBox.confirm(`取消 ${r.room.name} ${r.seat.code} 的预约？`, "确认");
  try {
    await seatApi.POST("/api/v1/seat/reservations/{reservation_id}/cancel", {
      params: { path: { reservation_id: r.id } },
    });
    ElMessage.success("已取消");
    await load();
  } catch (e) {
    showError(e);
  }
}

async function checkIn(r: ReservationDetail) {
  const { value: code } = await ElMessageBox.prompt("输入教室屏幕上的签到码", "签到");
  try {
    await seatApi.POST("/api/v1/seat/reservations/{reservation_id}/check-in", {
      params: { path: { reservation_id: r.id } },
      body: { code },
    });
    ElMessage.success("签到成功");
    await load();
  } catch (e) {
    showError(e);
  }
}

onMounted(load);
</script>

<template>
  <el-table :data="items" v-loading="loading">
    <el-table-column label="自习室" prop="room.name" />
    <el-table-column label="座位" prop="seat.code" />
    <el-table-column label="开始">
      <template #default="{ row }">{{ fmtTime(row.start_at) }}</template>
    </el-table-column>
    <el-table-column label="结束">
      <template #default="{ row }">{{ fmtTime(row.end_at) }}</template>
    </el-table-column>
    <el-table-column label="状态">
      <template #default="{ row }">{{ statusLabel[row.status] ?? row.status }}</template>
    </el-table-column>
    <el-table-column width="180">
      <template #default="{ row }">
        <template v-if="row.status === 'booked'">
          <el-button size="small" type="primary" @click="checkIn(row)">签到</el-button>
          <el-button size="small" @click="cancel(row)">取消</el-button>
        </template>
      </template>
    </el-table-column>
  </el-table>
</template>
