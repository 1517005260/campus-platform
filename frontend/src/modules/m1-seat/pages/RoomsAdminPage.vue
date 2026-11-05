<script setup lang="ts">
/**
 * 教室与座位管理：空间主数据（教室/自习室、开放时间）与座位（插座、启停）。
 * 座位状态历史（来源追溯）在座位行内查看。
 */
import { ElMessage, ElMessageBox } from "element-plus";
import { onMounted, reactive, ref, watch } from "vue";

import PaginatedTable from "@/core/components/PaginatedTable.vue";
import { fmtTime } from "@/core/format";
import { showError } from "@/core/http";

import { seatApi, type Room, type RoomDetail, type StatusHistoryItem } from "../api";

type RoomType = Room["type"];
type Outlet = RoomDetail["seats"][number]["outlet"];
type SeatStatus = RoomDetail["seats"][number]["status"];

/** 与后端 OpenHour 一致；weekday 0 = 周一 */
interface OpenHourRow {
  weekday: number;
  open_hour: number;
  close_hour: number;
}

const weekdayLabel = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];
const typeLabel: Record<string, string> = { classroom: "教室", library: "图书馆", other: "其他" };
const outletLabel: Record<string, string> = { none: "无", fixed: "固定", rail: "导轨" };
const sourceLabel: Record<string, string> = {
  M1_RESERVATION: "预约",
  M1_ADMIN: "管理员",
  M2_OCCUPY: "整室占用",
  M3_MAINTENANCE: "维修下架",
};
const stateLabel: Record<string, string> = {
  reserved: "被预约",
  released: "释放",
  blocked: "封闭",
  unblocked: "解封",
};

/** ---- 教室列表 ---- */
const rooms = ref<Room[]>([]);
const loading = ref(false);
const total = ref(0);
const page = ref(1);
const size = ref(10);
const building = ref("");
const type = ref<RoomType>();

async function load() {
  loading.value = true;
  try {
    const { data } = await seatApi.GET("/api/v1/seat/rooms", {
      params: {
        query: { building: building.value || undefined, type: type.value, page: page.value, size: size.value },
      },
    });
    rooms.value = data!.items;
    total.value = data!.total;
  } catch (e) {
    showError(e);
  } finally {
    loading.value = false;
  }
}

/** ---- 新建 / 编辑教室 ---- */
const dialogVisible = ref(false);
const editingId = ref<number | null>(null);
const form = reactive({
  building: "",
  floor: 1,
  name: "",
  type: "classroom" as RoomType,
  capacity: 40,
  is_study_room: true,
  is_whole_bookable: false,
  open_hours: [] as OpenHourRow[],
});

function openCreate() {
  editingId.value = null;
  Object.assign(form, {
    building: "",
    floor: 1,
    name: "",
    type: "classroom",
    capacity: 40,
    is_study_room: true,
    is_whole_bookable: false,
    open_hours: [],
  });
  dialogVisible.value = true;
}

function openEdit(r: Room) {
  editingId.value = r.id;
  Object.assign(form, {
    building: r.building,
    floor: r.floor,
    name: r.name,
    type: r.type,
    capacity: r.capacity,
    is_study_room: r.is_study_room ?? true,
    is_whole_bookable: r.is_whole_bookable ?? false,
    open_hours: (r.open_hours ?? []).map((h) => ({ ...h })),
  });
  dialogVisible.value = true;
}

function addOpenHour() {
  form.open_hours.push({ weekday: 0, open_hour: 8, close_hour: 22 });
}

async function saveRoom() {
  try {
    if (editingId.value === null) {
      await seatApi.POST("/api/v1/seat/rooms", { body: { ...form } });
      ElMessage.success("已创建");
    } else {
      await seatApi.PATCH("/api/v1/seat/rooms/{room_id}", {
        params: { path: { room_id: editingId.value } },
        body: { ...form },
      });
      ElMessage.success("已保存");
    }
    dialogVisible.value = false;
    await load();
  } catch (e) {
    showError(e);
  }
}

async function toggleRoom(r: Room) {
  const action = r.status === "enabled" ? "停用" : "启用";
  await ElMessageBox.confirm(`${action}教室 ${r.name}？`, "确认");
  try {
    await seatApi.PATCH("/api/v1/seat/rooms/{room_id}", {
      params: { path: { room_id: r.id } },
      body: { status: r.status === "enabled" ? "disabled" : "enabled" },
    });
    ElMessage.success(`已${action}`);
    await load();
  } catch (e) {
    showError(e);
  }
}

/** ---- 座位管理 ---- */
const seatDrawer = ref(false);
const detail = ref<RoomDetail | null>(null);
const seatsLoading = ref(false);
const newSeatCode = ref("");
const newSeatOutlet = ref<Outlet>("none");

async function openSeats(r: Room) {
  seatDrawer.value = true;
  detail.value = null;
  seatsLoading.value = true;
  try {
    const { data } = await seatApi.GET("/api/v1/seat/rooms/{room_id}", {
      params: { path: { room_id: r.id } },
    });
    detail.value = data!;
  } catch (e) {
    showError(e);
  } finally {
    seatsLoading.value = false;
  }
}

async function reloadDetail() {
  if (!detail.value) return;
  const { data } = await seatApi.GET("/api/v1/seat/rooms/{room_id}", {
    params: { path: { room_id: detail.value.id } },
  });
  detail.value = data!;
}

async function addSeat() {
  if (!detail.value || !newSeatCode.value) return;
  try {
    await seatApi.POST("/api/v1/seat/rooms/{room_id}/seats", {
      params: { path: { room_id: detail.value.id } },
      body: { code: newSeatCode.value, outlet: newSeatOutlet.value },
    });
    ElMessage.success(`已添加座位 ${newSeatCode.value}`);
    newSeatCode.value = "";
    await reloadDetail();
  } catch (e) {
    showError(e);
  }
}

async function patchSeat(seatId: number, body: { status?: SeatStatus; outlet?: Outlet }) {
  try {
    await seatApi.PATCH("/api/v1/seat/seats/{seat_id}", {
      params: { path: { seat_id: seatId } },
      body,
    });
    await reloadDetail();
  } catch (e) {
    showError(e);
  }
}

/** el-select 的 change 值按字符串传入，收窄为插座类型后提交 */
async function onOutletChange(seatId: number, outlet: string) {
  await patchSeat(seatId, { outlet: outlet as Outlet });
}

/** ---- 座位状态历史 ---- */
const historyVisible = ref(false);
const historySeatCode = ref("");
const history = ref<StatusHistoryItem[]>([]);

async function showHistory(seatCode: string, seatId: number) {
  try {
    const { data } = await seatApi.GET("/api/v1/seat/seats/{seat_id}/status-history", {
      params: { path: { seat_id: seatId } },
    });
    historySeatCode.value = seatCode;
    history.value = data!;
    historyVisible.value = true;
  } catch (e) {
    showError(e);
  }
}

watch([page, size], () => void load());
onMounted(load);
</script>

<template>
  <div>
    <el-form inline @submit.prevent="load">
      <el-form-item label="楼宇">
        <el-input v-model="building" clearable placeholder="如：第三教学楼" style="width: 180px" />
      </el-form-item>
      <el-form-item label="类型">
        <el-select v-model="type" clearable placeholder="全部" style="width: 120px">
          <el-option v-for="(label, value) in typeLabel" :key="value" :label="label" :value="value" />
        </el-select>
      </el-form-item>
      <el-button type="primary" native-type="submit" :loading="loading">查询</el-button>
      <el-button @click="openCreate">新建教室</el-button>
    </el-form>

    <PaginatedTable :data="rooms" :loading="loading" :total="total" v-model:page="page" v-model:size="size">
      <el-table-column label="楼宇" prop="building" />
      <el-table-column label="楼层" prop="floor" width="70" />
      <el-table-column label="名称" prop="name" />
      <el-table-column label="类型">
        <template #default="{ row }">{{ typeLabel[row.type] ?? row.type }}</template>
      </el-table-column>
      <el-table-column label="自习室" width="70">
        <template #default="{ row }">
          <el-tag v-if="row.is_study_room" size="small" type="success">是</el-tag>
          <span v-else>否</span>
        </template>
      </el-table-column>
      <el-table-column label="整室可借" width="80">
        <template #default="{ row }">
          <el-tag v-if="row.is_whole_bookable" size="small" type="success">可</el-tag>
          <span v-else>否</span>
        </template>
      </el-table-column>
      <el-table-column label="容量" prop="capacity" width="70" />
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <el-tag :type="row.status === 'enabled' ? 'success' : 'info'" size="small">
            {{ row.status === "enabled" ? "启用" : "停用" }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="240">
        <template #default="{ row }">
          <el-button size="small" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" @click="openSeats(row)">座位管理</el-button>
          <el-button size="small" :type="row.status === 'enabled' ? 'danger' : 'success'" @click="toggleRoom(row)">
            {{ row.status === "enabled" ? "停用" : "启用" }}
          </el-button>
        </template>
      </el-table-column>
    </PaginatedTable>

    <el-dialog v-model="dialogVisible" :title="editingId === null ? '新建教室' : `编辑 ${form.name}`" width="640px">
      <el-form label-width="100px">
        <el-form-item label="楼宇" required>
          <el-input v-model="form.building" placeholder="如：第三教学楼" />
        </el-form-item>
        <el-form-item label="楼层" required>
          <el-input-number v-model="form.floor" :min="1" />
        </el-form-item>
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="如：H3106" />
        </el-form-item>
        <el-form-item label="类型" required>
          <el-select v-model="form.type">
            <el-option v-for="(label, value) in typeLabel" :key="value" :label="label" :value="value" />
          </el-select>
        </el-form-item>
        <el-form-item label="容量" required>
          <el-input-number v-model="form.capacity" :min="1" />
        </el-form-item>
        <el-form-item label="作为自习室">
          <el-switch v-model="form.is_study_room" />
        </el-form-item>
        <el-form-item label="允许整室借用">
          <el-switch v-model="form.is_whole_bookable" />
        </el-form-item>
        <el-form-item label="开放时间">
          <div v-for="(h, i) in form.open_hours" :key="i" class="open-hour-row">
            <el-select v-model="h.weekday" style="width: 90px">
              <el-option v-for="(label, wd) in weekdayLabel" :key="wd" :label="label" :value="Number(wd)" />
            </el-select>
            <el-input-number v-model="h.open_hour" :min="0" :max="23" style="width: 110px" />
            <span style="margin: 0 4px">至</span>
            <el-input-number v-model="h.close_hour" :min="1" :max="24" style="width: 110px" />
            <el-button link type="danger" @click="form.open_hours.splice(i, 1)">删除</el-button>
          </div>
          <el-button link type="primary" @click="addOpenHour">添加时段</el-button>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveRoom">保存</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="seatDrawer" :title="`座位管理 · ${detail?.building} ${detail?.name}`" size="720px">
      <div v-loading="seatsLoading">
        <el-form inline @submit.prevent="addSeat">
          <el-form-item label="座位号">
            <el-input v-model="newSeatCode" placeholder="如：A-01" style="width: 120px" />
          </el-form-item>
          <el-form-item label="插座">
            <el-select v-model="newSeatOutlet" style="width: 120px">
              <el-option v-for="(label, value) in outletLabel" :key="value" :label="label" :value="value" />
            </el-select>
          </el-form-item>
          <el-button type="primary" native-type="submit">添加座位</el-button>
        </el-form>

        <el-table :data="detail?.seats ?? []">
          <el-table-column label="座位号" prop="code" />
          <el-table-column label="插座" width="140">
            <template #default="{ row }">
              <el-select
                :model-value="row.outlet"
                size="small"
                style="width: 110px"
                @change="(v: string) => onOutletChange(row.id, v)"
              >
                <el-option v-for="(label, value) in outletLabel" :key="value" :label="label" :value="value" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="row.status === 'enabled' ? 'success' : 'info'" size="small">
                {{ row.status === "enabled" ? "启用" : "停用" }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="220">
            <template #default="{ row }">
              <el-button size="small" @click="showHistory(row.code, row.id)">状态历史</el-button>
              <el-button
                size="small"
                :type="row.status === 'enabled' ? 'danger' : 'success'"
                @click="patchSeat(row.id, { status: row.status === 'enabled' ? 'disabled' : 'enabled' })"
              >
                {{ row.status === "enabled" ? "停用" : "启用" }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-drawer>

    <el-dialog v-model="historyVisible" :title="`座位 ${historySeatCode} 状态历史`" width="640px">
      <el-table :data="history">
        <el-table-column label="时间">
          <template #default="{ row }">{{ fmtTime(row.at) }}</template>
        </el-table-column>
        <el-table-column label="动作">
          <template #default="{ row }">{{ stateLabel[row.state] ?? row.state }}</template>
        </el-table-column>
        <el-table-column label="来源">
          <template #default="{ row }">{{ sourceLabel[row.source] ?? row.source }}</template>
        </el-table-column>
        <el-table-column label="关联单号" prop="ref_id" width="90" />
      </el-table>
    </el-dialog>
  </div>
</template>

<style scoped>
.open-hour-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
</style>
