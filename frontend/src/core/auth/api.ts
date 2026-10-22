import type { paths } from "@/api/types/common";
import { createApi } from "@/core/http";

export const authApi = createApi<paths>();
