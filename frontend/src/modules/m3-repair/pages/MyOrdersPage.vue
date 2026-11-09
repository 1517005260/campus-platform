<script setup lang="ts">
/**
 * 我的报修：上报故障（教室与座位来自 M1，分类来自系统参数）、查看工单与时间线、
 * 验收评价（评分 + 意见 / 不通过说明）、取消待派单的工单。
 */
import { ElMessage } from "element-plus";
import { onMounted, reactive, ref, watch } from "vue";

import PaginatedTable from "@/core/components/PaginatedTable.vue";
import { promptText } from "@/core/dialogs";
import { showError } from "@/core/http";
import { usePagedList } from "@/core/pagedList";
import { fetchRoomDetail, roomLabel, seatCode, useRooms, type Seat } from "@/core/rooms";

import OrderDetailDialog from "./OrderDetailDialog.vue";
import { orderStatusLabel, repairApi, type WorkOrder } from "../api";

/** 描述、原因至少几个字（去掉首尾空白），与后端一致 */
const TEXT_MIN = 2;

/** ---- 列表 ---- */
const { items, total, page, size, loading, load } = usePagedList((p) =>
  repairApi.GET("/api/v1/repair/orders/mine", { params: { query: p } }).then((r) => r.data!),
);

/** ---- 上报故障 ---- */
const showForm = ref(false);
const submitting = ref(false);
const { rooms, load: loadRooms, nameOf } = useRooms();
const seats = ref<Seat[]>([]);
const categories = ref<string[]>([]);
const form = reactive({
  room_id: undefined as number | undefined,
  seat_id: undefined as number | undefined,
  category: "",
  description: "",
  photos: "",
});

async function openForm() {
  showForm.value = true;
  if (categories.value.length > 0) return;
  try {
    const { data } = await repairApi.GET("/api/v1/repair/settings");
    categories.value = data!.categories;
    if (form.category === "" && categories.value.length > 0) form.category = categories.value[0]!;
  } catch (e) {
    showError(e);
  }
}

// 换教室后重新列出该教室的座位
watch(
  () => form.room_id,
  async (roomId) => {
    form.seat_id = undefined;
    seats.value = [];
    if (roomId === undefined) return;
    try {
      seats.value = (await fetchRoomDetail(roomId)).seats;
    } catch (e) {
      showError(e);
    }
  },
);

async function submit() {
  if (!form.room_id || !form.category || form.description.trim().length < TEXT_MIN) {
    ElMessage.warning(`请填写教室、分类和描述（至少 ${TEXT_MIN} 个字）`);
    return;
  }
  submitting.value = true;
  try {
    const { data } = await repairApi.POST("/api/v1/repair/orders", {
      body: {
        room_id: form.room_id,
        seat_id: form.seat_id ?? null,
        category: form.category,
        description: form.description.trim(),
        photos: form.photos
          .split("\n")
          .map((p) => p.trim())
          .filter(Boolean),
      },
    });
    ElMessage.success(`已上报，工单号 ${data!.id}`);
    showForm.value = false;
    form.description = "";
    form.photos = "";
    form.seat_id = undefined;
    await load();
  } catch (e) {
    showError(e);
  } finally {
    submitting.value = false;
  }
}

/** ---- 详情 / 验收 / 取消 ---- */
const detailVisible = ref(false);
const detailOrder = ref<WorkOrder | null>(null);

function showDetail(o: WorkOrder) {
  detailOrder.value = o;
  detailVisible.value = true;
}

const accepting = ref<WorkOrder | null>(null);
const acceptForm = reactive({ rating: 5, comment: "" });
const acceptSubmitting = ref(false);

function openAccept(o: WorkOrder) {
  accepting.value = o;
  acceptForm.rating = 5;
  acceptForm.comment = "";
}

async function accept() {
  if (!accepting.value) return;
  acceptSubmitting.value = true;
  try {
    await repairApi.POST("/api/v1/repair/orders/{order_id}/accept", {
      params: { path: { order_id: accepting.value.id } },
      body: { rating: acceptForm.rating, comment: acceptForm.comment.trim() || null },
    });
    ElMessage.success("已验收");
    accepting.value = null;
    await load();
  } catch (e) {
    showError(e);
  } finally {
    acceptSubmitting.value = false;
  }
}

async function rejectAcceptance(o: WorkOrder) {
  const reason = await promptText("请填写不通过的原因，工单将退回维修中", "验收不通过", {
    inputType: "textarea",
    minLength: TEXT_MIN,
  });
  if (reason === null) return;
  try {
    await repairApi.POST("/api/v1/repair/orders/{order_id}/reject-acceptance", {
      params: { path: { order_id: o.id } },
      body: { reason },
    });
    ElMessage.success("已退回维修中");
    await load();
  } catch (e) {
    showError(e);
  }
}

async function cancelOrder(o: WorkOrder) {
  const reason = await promptText("请填写取消原因", `取消工单 #${o.id}`, {
    action: "取消工单",
    inputType: "textarea",
    minLength: TEXT_MIN,
  });
  if (reason === null) return;
  try {
    await repairApi.POST("/api/v1/repair/orders/{order_id}/cancel", {
      params: { path: { order_id: o.id } },
      body: { reason },
    });
    ElMessage.success("已取消");
    await load();
  } catch (e) {
    showError(e);
  }
}

onMounted(() => {
  void load();
  void loadRooms();
});
</script>

<template>
  <el-button type="primary" style="margin-bottom: 12px" @click="openForm">上报故障</el-button>

  <PaginatedTable :data="items" :loading="loading" :total="total" v-model:page="page" v-model:size="size">
    <el-table-column label="工单号" prop="id" width="80" />
    <el-table-column label="教室" width="160">
      <template #default="{ row }">{{ nameOf(row.room_id) }}</template>
    </el-table-column>
    <el-table-column label="座位" width="90">
      <template #default="{ row }">{{ row.seat_id ? seatCode(row.room_id, row.seat_id) : "整体" }}</template>
    </el-table-column>
    <el-table-column label="分类" prop="category" width="90" />
    <el-table-column label="描述" prop="description" show-overflow-tooltip />
    <el-table-column label="状态" width="100">
      <template #default="{ row }">{{ orderStatusLabel[row.status as WorkOrder["status"]] }}</template>
    </el-table-column>
    <el-table-column label="维修人" width="100">
      <template #default="{ row }">{{ row.assignee?.name ?? "—" }}</template>
    </el-table-column>
    <el-table-column label="评分" width="70">
      <template #default="{ row }">{{ row.rating ?? "—" }}</template>
    </el-table-column>
    <el-table-column label="操作" width="200">
      <template #default="{ row }">
        <el-button size="small" link type="primary" @click="showDetail(row)">详情</el-button>
        <template v-if="row.status === 'pending_acceptance'">
          <el-button size="small" link type="success" @click="openAccept(row)">验收</el-button>
          <el-button size="small" link type="danger" @click="rejectAcceptance(row)">不通过</el-button>
        </template>
        <el-button v-if="row.status === 'submitted'" size="small" link type="danger" @click="cancelOrder(row)">
          取消
        </el-button>
      </template>
    </el-table-column>
  </PaginatedTable>

  <el-dialog v-model="showForm" title="上报故障" width="520px">
    <el-form label-width="80px">
      <el-form-item label="教室" required>
        <el-select v-model="form.room_id" filterable placeholder="选择教室" style="width: 100%">
          <el-option v-for="r in rooms" :key="r.id" :label="roomLabel(r)" :value="r.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="座位">
        <el-select
          v-model="form.seat_id"
          clearable
          filterable
          :disabled="form.room_id === undefined"
          placeholder="教室整体问题不选"
          style="width: 100%"
        >
          <el-option v-for="seat in seats" :key="seat.id" :label="seat.code" :value="seat.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="分类" required>
        <el-select v-model="form.category" style="width: 160px">
          <el-option v-for="c in categories" :key="c" :label="c" :value="c" />
        </el-select>
      </el-form-item>
      <el-form-item label="描述" required>
        <el-input
          v-model="form.description"
          type="textarea"
          :rows="3"
          maxlength="1000"
          show-word-limit
          placeholder="故障现象，如：空调不制冷"
        />
      </el-form-item>
      <el-form-item label="照片">
        <el-input v-model="form.photos" type="textarea" :rows="2" placeholder="图片链接，每行一个（可选）" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="showForm = false">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="submit">提交</el-button>
    </template>
  </el-dialog>

  <el-dialog
    :model-value="accepting !== null"
    :title="`验收工单 #${accepting?.id}`"
    width="420px"
    @close="accepting = null"
  >
    <el-form label-width="70px">
      <el-form-item label="评分">
        <el-rate v-model="acceptForm.rating" />
      </el-form-item>
      <el-form-item label="意见">
        <el-input v-model="acceptForm.comment" type="textarea" :rows="2" maxlength="500" placeholder="可选" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="accepting = null">取消</el-button>
      <el-button type="primary" :loading="acceptSubmitting" @click="accept">确认验收</el-button>
    </template>
  </el-dialog>

  <OrderDetailDialog
    v-model="detailVisible"
    :order="detailOrder"
    :room-name="detailOrder ? nameOf(detailOrder.room_id) : ''"
  />
</template>
