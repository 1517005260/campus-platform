import type { components, paths } from "@/api/types/m2-room";
import { createApi } from "@/core/http";

export const roomApi = createApi<paths>();
export type Application = components["schemas"]["Application"];
export type ApplicationForApprover = components["schemas"]["ApplicationForApprover"];
