/**
 * 分页列表的状态与加载，配合 PaginatedTable 使用：
 *
 *   const { items, total, page, size, loading, load, reload } = usePagedList((p) =>
 *     api.GET("/api/v1/...", { params: { query: { ...filters, ...p } } }).then((r) => r.data!),
 *   );
 *
 * 翻页时 load() 当前页；筛选条件变化或改每页条数时调用 reload() 回到第 1 页，避免停在越界页上。
 */
import { ref, watch, type Ref } from "vue";

import { showError } from "@/core/http";

export interface PageOf<T> {
  items: T[];
  total: number;
}

export function usePagedList<T>(fetchPage: (p: { page: number; size: number }) => Promise<PageOf<T>>) {
  const items = ref([]) as Ref<T[]>;
  const total = ref(0);
  const page = ref(1);
  const size = ref(10);
  const loading = ref(false);

  async function load() {
    loading.value = true;
    try {
      const data = await fetchPage({ page: page.value, size: size.value });
      items.value = data.items;
      total.value = data.total;
    } catch (e) {
      showError(e);
    } finally {
      loading.value = false;
    }
  }

  /** 回到第 1 页重新加载（已在第 1 页时直接加载，否则由翻页触发加载） */
  function reload() {
    if (page.value === 1) void load();
    else page.value = 1;
  }

  watch(page, () => void load());
  watch(size, reload);

  return { items, total, page, size, loading, load, reload };
}
