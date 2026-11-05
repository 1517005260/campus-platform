<script setup lang="ts" generic="T">
/**
 * 分页表格：el-table + el-pagination 的统一封装。
 * 列由默认插槽传入（el-table-column），当前页与每页条数用 v-model:page / v-model:size 双向绑定。
 */
defineProps<{
  data: T[];
  loading?: boolean;
  total: number;
  pageSizes?: number[];
}>();

const page = defineModel<number>("page", { required: true });
const size = defineModel<number>("size", { required: true });
</script>

<template>
  <div>
    <el-table :data="data" v-loading="loading">
      <slot />
    </el-table>
    <el-pagination
      v-model:current-page="page"
      v-model:page-size="size"
      :page-sizes="pageSizes ?? [10, 20, 50]"
      :total="total"
      layout="total, sizes, prev, pager, next"
      style="margin-top: 12px; justify-content: flex-end"
    />
  </div>
</template>
