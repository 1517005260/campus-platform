import type { components, paths } from "@/api/types/common";
import { createApi } from "@/core/http";

export const commonApi = createApi<paths>();
export type RoleOut = components["schemas"]["RoleOut"];
export type PermissionOut = components["schemas"]["PermissionOut"];
