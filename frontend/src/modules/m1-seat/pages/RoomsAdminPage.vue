<script setup lang="ts">
/**
 * 教室与座位管理：空间主数据（教室/自习室、所属院系、开放时间）与座位（插座、启停）。
 * 座位状态历史（来源追溯）在座位行内查看。
 * 停用座位、停用教室、取消"作为自习室"会取消尚未结束的预约（后端通知学生），操作前确认。
 */
import { ElMessage, type FormInstance, type FormRules } from "element-plus";
import { computed, onMounted, reactive, ref } from "vue";

import { commonApi } from "@/core/commonApi";
import PaginatedTable from "@/core/components/PaginatedTable.vue";
import { confirmAction } from "@/core/dialogs";
import { fmtTime } from "@/core/format";
import { showError } from "@/core/http";
import { usePagedList } from "@/core/pagedList";

import {
  outletLabel,
  seatApi,
  type OpenHour,
  type Room,
  type RoomDetail,
  type Seat,
  type StatusHistoryItem,
} from "../api";

type RoomType = Room["type"];
type Outlet = Seat["outlet"];

const weekdayLabel = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];
const typeLabel: Record<string, string> = { classroom: "教室", library: "图书馆", other: "其他" };
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
const CANCELS_RESERVATIONS = "尚未结束的预约将被取消并通知学生（不记违约）。";

/** ---- 院系（所属院系下拉与列表显示） ---- */
const depts = ref<{ id: number; name: string }[]>([]);
const deptName = computed(() => Object.fromEntries(depts.value.map((d) => [d.id, d.name])));

/** ---- 教室列表 ---- */
const building = ref("");
const type = ref<RoomType>();
const {
  items: rooms,
  total,
  page,
  size,
  loading,
  load,
  reload,
} = usePagedList((p) =>
  seatApi
    .GET("/api/v1/seat/rooms", { params: { query: { building: building.value || undefined, type: type.value, ...p } } })
    .then((r) => r.data!),
);

/** ---- 新建 / 编辑教室 ---- */
const dialogVisible = ref(false);
const editing = ref<Room | null>(null);
const saving = ref(false);
const formRef = ref<FormInstance>();
const emptyForm = () => ({
  building: "",
  floor: 1,
  name: "",
  type: "classroom" as RoomType,
  dept_id: null as number | null,
  capacity: 40,
  is_study_room: true,
  is_whole_bookable: false,
  open_hours: [] as OpenHour[],
});
const form = reactive(emptyForm());
const notBlank = { required: true, whitespace: true, message: "不能为空", trigger: "blur" };
const rules: FormRules = { building: [notBlank], name: [notBlank] };

function openCreate() {
  editing.value = null;
  Object.assign(form, emptyForm());
  dialogVisible.value = true;
  formRef.value?.clearValidate();
}

function openEdit(r: Room) {
  editing.value = r;
  Object.assign(form, {
    building: r.building,
    floor: r.floor,
    name: r.name,
    type: r.type,
    dept_id: r.dept_id ?? null,
    capacity: r.capacity,
    is_study_room: r.is_study_room ?? true,
    is_whole_bookable: r.is_whole_bookable ?? false,
    open_hours: (r.open_hours ?? []).map((h) => ({ ...h })),
  });
  dialogVisible.value = true;
  formRef.value?.clearValidate();
}

async function saveRoom() {
  if (!(await formRef.value?.validate().catch(() => false))) return;
  const body = { ...form, building: form.building.trim(), name: form.name.trim() };
  const deregisters = editing.value?.is_study_room && !form.is_study_room;
  if (deregisters && !(await confirmAction(`取消 ${editing.value!.name} 的"作为自习室"？${CANCELS_RESERVATIONS}`))) {
    return;
  }
  saving.value = true;
  try {
    if (editing.value === null) {
      await seatApi.POST("/api/v1/seat/rooms", { body });
      ElMessage.success("已创建");
    } else {
      await seatApi.PATCH("/api/v1/seat/rooms/{room_id}", { params: { path: { room_id: editing.value.id } }, body });
      ElMessage.success("已保存");
    }
    dialogVisible.value = false;
    await load();
  } catch (e) {
    showError(e);
  } finally {
    saving.value = false;
  }
}

async function toggleRoom(r: Room) {
  const disabling = r.status === "enabled";
  const action = disabling ? "停用" : "启用";
  if (!(await confirmAction(`${action}教室 ${r.name}？${disabling ? CANCELS_RESERVATIONS : ""}`))) return;
  try {
    await seatApi.PATCH("/api/v1/seat/rooms/{room_id}", {
      params: { path: { room_id: r.id } },
      body: { status: disabling ? "disabled" : "enabled" },
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
const addingSeat = ref(false);

async function loadDetail(roomId: number) {
  try {
    const { data } = await seatApi.GET("/api/v1/seat/rooms/{room_id}", { params: { path: { room_id: roomId } } });
    detail.value = data!;
  } catch (e) {
    showError(e);
  }
}

async function openSeats(r: Room) {
  seatDrawer.value = true;
  detail.value = null;
  seatsLoading.value = true;
  await loadDetail(r.id);
  seatsLoading.value = false;
}

async function addSeat() {
  const code = newSeatCode.value.trim();
  if (!detail.value) return;
  if (!code) {
    ElMessage.warning("请填写座位号");
    return;
  }
  addingSeat.value = true;
  try {
    await seatApi.POST("/api/v1/seat/rooms/{room_id}/seats", {
      params: { path: { room_id: detail.value.id } },
      body: { code, outlet: newSeatOutlet.value },
    });
    ElMessage.success(`已添加座位 ${code}`);
    newSeatCode.value = "";
    await loadDetail(detail.value.id);
  } catch (e) {
    showError(e);
  } finally {
    addingSeat.value = false;
  }
}

async function patchSeat(seat: Seat, body: { status?: Seat["status"]; outlet?: Outlet }, done: string) {
  try {
    await seatApi.PATCH("/api/v1/seat/seats/{seat_id}", { params: { path: { seat_id: seat.id } }, body });
    ElMessage.success(done);
    await loadDetail(seat.room_id);
  } catch (e) {
    showError(e);
  }
}

async function toggleSeat(seat: Seat) {
  const disabling = seat.status === "enabled";
  if (disabling && !(await confirmAction(`停用座位 ${seat.code}？${CANCELS_RESERVATIONS}`))) return;
  await patchSeat(
    seat,
    { status: disabling ? "disabled" : "enabled" },
    `座位 ${seat.code} 已${disabling ? "停用" : "启用"}`,
  );
}

/** el-select 的 change 值按字符串传入，收窄为插座类型后提交 */
async function onOutletChange(seat: Seat, outlet: string) {
  await patchSeat(seat, { outlet: outlet as Outlet }, `座位 ${seat.code} 插座已更新`);
}

/** ---- 座位状态历史 ---- */
const historyVisible = ref(false);
const historySeatCode = ref("");
const history = ref<StatusHistoryItem[]>([]);

async function showHistory(seat: Seat) {
  try {
    const { data } = await seatApi.GET("/api/v1/seat/seats/{seat_id}/status-history", {
      params: { path: { seat_id: seat.id } },
    });
    historySeatCode.value = seat.code;
    history.value = data!;
    historyVisible.value = true;
  } catch (e) {
    showError(e);
  }
}

onMounted(async () => {
  void load();
  try {
    const { data } = await commonApi.GET("/api/v1/admin/depts");
    depts.value = data!;
  } catch (e) {
    showError(e);
  }
});
</script>

<template>
  <div>
    <el-form inline @submit.prevent="reload">
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
      <el-table-column label="所属院系">
        <template #default="{ row }">{{
          row.dept_id ? (deptName[row.dept_id] ?? `#${row.dept_id}`) : "全校"
        }}</template>
      </el-table-column>
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

    <el-dialog v-model="dialogVisible" :title="editing === null ? '新建教室' : `编辑 ${editing.name}`" width="640px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="楼宇" prop="building">
          <el-input v-model="form.building" placeholder="如：第三教学楼" />
        </el-form-item>
        <el-form-item label="楼层" required>
          <el-input-number v-model="form.floor" :value-on-clear="1" />
        </el-form-item>
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" placeholder="如：H3106" />
        </el-form-item>
        <el-form-item label="类型" required>
          <el-select v-model="form.type">
            <el-option v-for="(label, value) in typeLabel" :key="value" :label="label" :value="value" />
          </el-select>
        </el-form-item>
        <el-form-item label="所属院系">
          <el-select v-model="form.dept_id" clearable placeholder="全校开放" style="width: 100%">
            <el-option v-for="d in depts" :key="d.id" :label="d.name" :value="d.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="容量" required>
          <el-input-number v-model="form.capacity" :min="1" value-on-clear="min" />
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
            <el-input-number v-model="h.open_hour" :min="0" :max="23" value-on-clear="min" style="width: 110px" />
            <span style="margin: 0 4px">至</span>
            <el-input-number v-model="h.close_hour" :min="1" :max="24" value-on-clear="max" style="width: 110px" />
            <el-button link type="danger" @click="form.open_hours.splice(i, 1)">删除</el-button>
          </div>
          <el-button link type="primary" @click="form.open_hours.push({ weekday: 0, open_hour: 8, close_hour: 22 })"
            >添加时段</el-button
          >
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveRoom">保存</el-button>
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
          <el-button type="primary" native-type="submit" :loading="addingSeat">添加座位</el-button>
        </el-form>

        <el-table :data="detail?.seats ?? []">
          <el-table-column label="座位号" prop="code" />
          <el-table-column label="插座" width="140">
            <template #default="{ row }">
              <el-select
                :model-value="row.outlet"
                size="small"
                style="width: 110px"
                @change="(v: string) => onOutletChange(row, v)"
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
              <el-button size="small" @click="showHistory(row)">状态历史</el-button>
              <el-button size="small" :type="row.status === 'enabled' ? 'danger' : 'success'" @click="toggleSeat(row)">
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
