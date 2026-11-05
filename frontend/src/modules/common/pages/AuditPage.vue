<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";

import { bizIso, fmtTime } from "@/core/format";
import { showError } from "@/core/http";

import { commonApi, moduleLabel, type AuditLogOut } from "../api";

const items = ref<AuditLogOut[]>([]);
const total = ref(0);
const loading = ref(false);
const page = ref(1);
const size = 20;

const filters = reactive({ actor_id: "", module: "", action: "", target_type: "", target_id: "" });
/** [起, 止)，选择器给出业务时区（北京时间）的墙上时间，提交时用 bizIso 加上 +08:00 */
const range = ref<[string, string] | null>(null);

async function load() {
  loading.value = true;
  const query = Object.fromEntries(Object.entries(filters).filter(([, v]) => v.trim()));
  try {
    const { data } = await commonApi.GET("/api/v1/audit", {
      params: {
        query: {
          ...query,
          date_from: range.value ? bizIso(range.value[0]) : undefined,
          date_to: range.value ? bizIso(range.value[1]) : undefined,
          page: page.value,
          size,
        },
      },
    });
    items.value = data!.items;
    total.value = data!.total;
  } catch (e) {
    showError(e);
  } finally {
    loading.value = false;
  }
}

function search() {
  page.value = 1;
  load();
}

const actorLabel: Record<string, string> = { user: "用户", service: "服务", system: "系统" };

onMounted(load);
</script>

<template>
  <el-form inline @submit.prevent="search">
    <el-form-item><el-input v-model="filters.actor_id" placeholder="操作人 ID / 服务名" clearable /></el-form-item>
    <el-form-item>
      <el-select v-model="filters.module" placeholder="模块" clearable style="width: 120px">
        <el-option v-for="(label, m) in moduleLabel" :key="m" :label="label" :value="m" />
      </el-select>
    </el-form-item>
    <el-form-item><el-input v-model="filters.action" placeholder="动作，如 block.create" clearable /></el-form-item>
    <el-form-item
      ><el-input v-model="filters.target_type" placeholder="对象类型" clearable style="width: 120px"
    /></el-form-item>
    <el-form-item
      ><el-input v-model="filters.target_id" placeholder="对象 ID" clearable style="width: 100px"
    /></el-form-item>
    <el-form-item>
      <el-date-picker
        v-model="range"
        type="datetimerange"
        start-placeholder="开始（含，北京时间）"
        end-placeholder="结束（不含）"
        value-format="YYYY-MM-DDTHH:mm:ss"
      />
    </el-form-item>
    <el-form-item><el-button type="primary" native-type="submit">查询</el-button></el-form-item>
  </el-form>

  <el-table :data="items" v-loading="loading" row-key="id">
    <el-table-column type="expand">
      <template #default="{ row }">
        <div class="detail">
          <div>
            <b>变更前</b>
            <pre>{{ row.before ? JSON.stringify(row.before, null, 2) : "—" }}</pre>
          </div>
          <div>
            <b>变更后</b>
            <pre>{{ row.after ? JSON.stringify(row.after, null, 2) : "—" }}</pre>
          </div>
          <div><b>请求 ID</b> {{ row.request_id ?? "—" }}</div>
        </div>
      </template>
    </el-table-column>
    <el-table-column label="时间" width="180">
      <template #default="{ row }">{{ fmtTime(row.at) }}</template>
    </el-table-column>
    <el-table-column label="操作人" width="160">
      <template #default="{ row }">{{ actorLabel[row.actor_type] ?? row.actor_type }} {{ row.actor_id }}</template>
    </el-table-column>
    <el-table-column label="模块" width="100">
      <template #default="{ row }">{{ moduleLabel[row.module] ?? row.module }}</template>
    </el-table-column>
    <el-table-column label="动作" prop="action" width="160" />
    <el-table-column label="对象">
      <template #default="{ row }">{{ row.target_type }} #{{ row.target_id }}</template>
    </el-table-column>
  </el-table>
  <el-pagination
    v-model:current-page="page"
    class="pager"
    layout="total, prev, pager, next"
    :page-size="size"
    :total="total"
    @current-change="load"
  />
</template>

<style scoped>
.detail {
  display: flex;
  gap: 32px;
  padding: 0 16px;
}
.detail pre {
  margin: 4px 0;
  font-size: 12px;
}
.pager {
  margin-top: 12px;
  justify-content: flex-end;
}
</style>
