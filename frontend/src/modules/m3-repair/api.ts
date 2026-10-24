import type { components, paths } from "@/api/types/m3-repair";
import { createApi } from "@/core/http";

export const repairApi = createApi<paths>();
export type WorkOrder = components["schemas"]["WorkOrder"];
