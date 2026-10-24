<script setup lang="ts">
import { ElMessage } from "element-plus";
import { ref } from "vue";

import HourRangePicker, { type HourRange } from "@/core/components/HourRangePicker.vue";
import { showError } from "@/core/http";

import { seatApi, type SeatSearchItem } from "../api";

const today = new Date().toISOString().slice(0, 10);
const range = ref<HourRange>({ date: today, start_hour: 14, end_hour: 16 });
const outlet = ref<"fixed" | "rail" | undefined>();
const items = ref<SeatSearchItem[]>([]);
const total = ref(0);
const loading = ref(false);

async function search() {
  loading.value = true;
  try {
    const { data } = await seatApi.GET("/api/v1/seat/seats/search", {
      params: { query: { ...range.value, outlet: outlet.value, page: 1, size: 50 } },
    });
    items.value = data!.items;
    total.value = data!.total;
  } catch (e) {
    showError(e);
  } finally {
    loading.value = false;
  }
}

async function reserve(item: SeatSearchItem) {
  try {
    const { data } = await seatApi.POST("/api/v1/seat/reservations", {
      body: { seat_id: item.seat.id, ...range.value },
    });
    ElMessage.success(`已预约 ${item.room.name} ${item.seat.code}，预约号 ${data!.id}`);
    await search();
  } catch (e) {
    showError(e);
  }
}
</script>

<template>
  <el-form inline @submit.prevent="search">
    <el-form-item label="时段">
      <HourRangePicker v-model="range" :max-hours="4" />
    </el-form-item>
    <el-form-item label="插座">
      <el-select v-model="outlet" clearable placeholder="不限" style="width: 140px">
        <el-option label="固定插座" value="fixed" />
        <el-option label="移动导轨插座" value="rail" />
      </el-select>
    </el-form-item>
    <el-button type="primary" native-type="submit" :loading="loading">搜索</el-button>
  </el-form>

  <el-table :data="items" v-loading="loading">
    <el-table-column label="楼宇" prop="room.building" />
    <el-table-column label="自习室" prop="room.name" />
    <el-table-column label="座位" prop="seat.code" />
    <el-table-column label="插座">
      <template #default="{ row }">
        {{ { none: "无", fixed: "固定", rail: "导轨" }[row.seat.outlet as "none" | "fixed" | "rail"] }}
      </template>
    </el-table-column>
    <el-table-column width="120">
      <template #default="{ row }">
        <el-button size="small" type="primary" @click="reserve(row)">预约</el-button>
      </template>
    </el-table-column>
  </el-table>
  <p v-if="total">共 {{ total }} 个可预约座位</p>
</template>
