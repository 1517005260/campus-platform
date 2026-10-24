<script setup lang="ts">
import { ElMessage } from "element-plus";
import { onMounted, ref } from "vue";

import { showError } from "@/core/http";

import { repairApi, type WorkOrder } from "../api";

const items = ref<WorkOrder[]>([]);
const showForm = ref(false);
const form = ref({ room_id: 1, category: "空调", description: "" });

async function load() {
  try {
    const { data } = await repairApi.GET("/api/v1/repair/orders/mine", { params: { query: { page: 1, size: 50 } } });
    items.value = data!.items;
  } catch (e) {
    showError(e);
  }
}

async function submit() {
  try {
    await repairApi.POST("/api/v1/repair/orders", { body: form.value });
    ElMessage.success("已提交");
    showForm.value = false;
    await load();
  } catch (e) {
    showError(e);
  }
}

onMounted(load);
</script>

<template>
  <el-button type="primary" style="margin-bottom: 12px" @click="showForm = true">上报故障</el-button>
  <el-table :data="items">
    <el-table-column label="工单号" prop="id" width="90" />
    <el-table-column label="教室" prop="room_id" width="80" />
    <el-table-column label="分类" prop="category" width="100" />
    <el-table-column label="描述" prop="description" />
    <el-table-column label="状态" prop="status" width="150" />
  </el-table>

  <el-dialog v-model="showForm" title="上报故障" width="480px">
    <el-form label-width="80px">
      <el-form-item label="教室 ID"><el-input-number v-model="form.room_id" :min="1" /></el-form-item>
      <el-form-item label="分类"><el-input v-model="form.category" /></el-form-item>
      <el-form-item label="描述"><el-input v-model="form.description" type="textarea" :rows="3" /></el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="showForm = false">取消</el-button>
      <el-button type="primary" @click="submit">提交</el-button>
    </template>
  </el-dialog>
</template>
