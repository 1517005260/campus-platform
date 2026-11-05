<script setup lang="ts">
/** 运营统计：利用率、违约率总览，各整点平均利用率与各自习室明细。 */
import { computed, onMounted, ref } from "vue";

import { showError } from "@/core/http";

import { seatApi, type Room, type UsageStats } from "../api";

function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

const dateFrom = ref(isoDaysAgo(6));
const dateTo = ref(isoDaysAgo(0));
const rooms = ref<Room[]>([]);
const roomId = ref<number>();
const stats = ref<UsageStats | null>(null);
const loading = ref(false);

const percent = (v: number) => `${(v * 100).toFixed(1)}%`;

/** by_hour 的键是整点字符串，按整点排序展示 */
const hourRows = computed(() => {
  const byHour = stats.value?.by_hour ?? {};
  return Object.entries(byHour)
    .map(([hour, rate]) => ({ hour: Number(hour), rate }))
    .sort((a, b) => a.hour - b.hour);
});

async function load() {
  loading.value = true;
  try {
    const { data } = await seatApi.GET("/api/v1/seat/stats/usage", {
      params: { query: { date_from: dateFrom.value, date_to: dateTo.value, room_id: roomId.value } },
    });
    stats.value = data!;
  } catch (e) {
    showError(e);
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  try {
    const { data } = await seatApi.GET("/api/v1/seat/rooms", {
      params: { query: { page: 1, size: 100 } },
    });
    rooms.value = data!.items;
  } catch (e) {
    showError(e);
  }
  await load();
});
</script>

<template>
  <div>
    <el-form inline @submit.prevent="load">
      <el-form-item label="起止日期">
        <el-date-picker v-model="dateFrom" type="date" value-format="YYYY-MM-DD" />
        <span style="margin: 0 8px">至</span>
        <el-date-picker v-model="dateTo" type="date" value-format="YYYY-MM-DD" />
      </el-form-item>
      <el-form-item label="自习室">
        <el-select v-model="roomId" clearable filterable placeholder="全部" style="width: 220px">
          <el-option v-for="r in rooms" :key="r.id" :label="`${r.building} ${r.name}`" :value="r.id" />
        </el-select>
      </el-form-item>
      <el-button type="primary" native-type="submit" :loading="loading">查询</el-button>
    </el-form>

    <el-row :gutter="16" v-loading="loading">
      <el-col :span="8">
        <el-card>
          <el-statistic title="座位利用率" :value="stats ? stats.utilization * 100 : 0" :precision="1">
            <template #suffix>%</template>
          </el-statistic>
          <div class="hint">已签到小时数 / 可预约小时数</div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card>
          <el-statistic title="违约率" :value="stats ? stats.no_show_rate * 100 : 0" :precision="1">
            <template #suffix>%</template>
          </el-statistic>
          <div class="hint">未签到取消 / 全部预约</div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card>
          <el-statistic title="自习室数" :value="stats?.by_room.length ?? 0" />
          <div class="hint">统计范围内出现预约的自习室</div>
        </el-card>
      </el-col>
    </el-row>

    <el-card header="各整点平均利用率" style="margin-top: 16px">
      <el-empty v-if="hourRows.length === 0" description="暂无数据" :image-size="60" />
      <div v-for="h in hourRows" :key="h.hour" class="hour-row">
        <span class="hour">{{ h.hour }}:00</span>
        <el-progress :percentage="Math.round(h.rate * 100)" :stroke-width="14" class="bar" />
      </div>
    </el-card>

    <el-card header="各自习室明细" style="margin-top: 16px">
      <el-table :data="stats?.by_room ?? []">
        <el-table-column label="自习室" width="160">
          <template #default="{ row }">
            {{ rooms.find((r) => r.id === row.room_id)?.name ?? `#${row.room_id}` }}
          </template>
        </el-table-column>
        <el-table-column label="利用率">
          <template #default="{ row }">{{ percent(row.utilization) }}</template>
        </el-table-column>
        <el-table-column label="违约率">
          <template #default="{ row }">{{ percent(row.no_show_rate) }}</template>
        </el-table-column>
        <el-table-column label="预约数" prop="reservations" />
      </el-table>
    </el-card>
  </div>
</template>

<style scoped>
.hint {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  margin-top: 8px;
}
.hour-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.hour {
  width: 52px;
  color: var(--el-text-color-secondary);
}
.bar {
  flex: 1;
}
</style>
