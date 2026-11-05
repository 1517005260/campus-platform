<script setup lang="ts">
/**
 * 我的预约：签到、取消、一键复订；附我的违约记录。
 * 复订以历史预约为模板（同一座位），时段重新选择。
 */
import { ElMessage, ElMessageBox } from "element-plus";
import { onMounted, ref, watch } from "vue";

import HourRangePicker, { type HourRange } from "@/core/components/HourRangePicker.vue";
import PaginatedTable from "@/core/components/PaginatedTable.vue";
import { fmtTime } from "@/core/format";
import { showError } from "@/core/http";

import { seatApi, type ReservationDetail, type Violation } from "../api";

const tab = ref<"reservations" | "violations">("reservations");

const statusLabel: Record<string, string> = {
  booked: "已预约",
  checked_in: "已签到",
  completed: "已完成",
  cancelled: "已取消",
  no_show: "未签到（违约）",
};

/** ---- 预约记录 ---- */
const items = ref<ReservationDetail[]>([]);
const loading = ref(false);
const total = ref(0);
const page = ref(1);
const size = ref(10);
const statusFilter = ref<ReservationDetail["status"]>();

const statusOptions = Object.entries(statusLabel).map(([value, label]) => ({ value, label }));

async function load() {
  loading.value = true;
  try {
    const { data } = await seatApi.GET("/api/v1/seat/reservations/mine", {
      params: { query: { status: statusFilter.value || undefined, page: page.value, size: size.value } },
    });
    items.value = data!.items;
    total.value = data!.total;
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

/** ---- 一键复订 ---- */
const rebooking = ref<ReservationDetail | null>(null);
const rebookRange = ref<HourRange>({ date: new Date().toISOString().slice(0, 10), start_hour: 14, end_hour: 16 });
const rebookMaxHours = ref(4);

async function openRebook(r: ReservationDetail) {
  const { data } = await seatApi.GET("/api/v1/seat/settings");
  rebookMaxHours.value = data!.max_hours;
  rebooking.value = r;
}

async function rebook() {
  const r = rebooking.value;
  if (!r) return;
  try {
    const { data } = await seatApi.POST("/api/v1/seat/reservations/{reservation_id}/rebook", {
      params: { path: { reservation_id: r.id } },
      body: { ...rebookRange.value },
    });
    ElMessage.success(`已复订 ${r.room.name} ${r.seat.code}，预约号 ${data!.id}`);
    rebooking.value = null;
    await load();
  } catch (e) {
    showError(e);
  }
}

/** ---- 违约记录 ---- */
const violations = ref<Violation[]>([]);
const violationsLoading = ref(false);
const violationsTotal = ref(0);
const violationsPage = ref(1);
const violationsSize = ref(10);

async function loadViolations() {
  violationsLoading.value = true;
  try {
    const { data } = await seatApi.GET("/api/v1/seat/violations/mine", {
      params: { query: { page: violationsPage.value, size: violationsSize.value } },
    });
    violations.value = data!.items;
    violationsTotal.value = data!.total;
  } catch (e) {
    showError(e);
  } finally {
    violationsLoading.value = false;
  }
}

watch(statusFilter, () => {
  page.value = 1;
  void load();
});
watch([page, size], () => void load());
watch([violationsPage, violationsSize], () => void loadViolations());
watch(tab, (t) => {
  if (t === "violations" && violations.value.length === 0) void loadViolations();
});
onMounted(load);
</script>

<template>
  <el-tabs v-model="tab">
    <el-tab-pane label="预约记录" name="reservations">
      <el-select v-model="statusFilter" clearable placeholder="全部状态" style="width: 160px; margin-bottom: 12px">
        <el-option v-for="o in statusOptions" :key="o.value" :label="o.label" :value="o.value" />
      </el-select>
      <PaginatedTable :data="items" :loading="loading" :total="total" v-model:page="page" v-model:size="size">
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
        <el-table-column label="取消原因" prop="cancel_reason" show-overflow-tooltip />
        <el-table-column width="220">
          <template #default="{ row }">
            <template v-if="row.status === 'booked'">
              <el-button size="small" type="primary" @click="checkIn(row)">签到</el-button>
              <el-button size="small" @click="cancel(row)">取消</el-button>
            </template>
            <el-button v-else size="small" @click="openRebook(row)">一键复订</el-button>
          </template>
        </el-table-column>
      </PaginatedTable>
    </el-tab-pane>

    <el-tab-pane label="违约记录" name="violations">
      <PaginatedTable
        :data="violations"
        :loading="violationsLoading"
        :total="violationsTotal"
        v-model:page="violationsPage"
        v-model:size="violationsSize"
      >
        <el-table-column label="编号" prop="id" width="80" />
        <el-table-column label="关联预约号" prop="reservation_id" />
        <el-table-column label="记录时间">
          <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
        </el-table-column>
      </PaginatedTable>
    </el-tab-pane>
  </el-tabs>

  <el-dialog
    :model-value="rebooking !== null"
    :title="`复订 ${rebooking?.room.name} ${rebooking?.seat.code}`"
    width="420px"
    @close="rebooking = null"
  >
    <el-form label-width="60px">
      <el-form-item label="时段">
        <HourRangePicker v-model="rebookRange" :max-hours="rebookMaxHours" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="rebooking = null">取消</el-button>
      <el-button type="primary" @click="rebook">复订</el-button>
    </template>
  </el-dialog>
</template>
