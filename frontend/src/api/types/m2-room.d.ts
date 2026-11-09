// 由 scripts/gen-types.mjs 从 contracts/openapi/m2-room.json 生成，不要手改。
export interface paths {
    "/api/v1/room/applications": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 提交整教室申请
         * @description 校验通过后匹配审批流并快照到申请上，进入第 1 级审批，通知第 1 级审批人。错误码：
         *
         *     - 400 ADVANCE_DAYS_OUT_OF_RANGE：开始时间不晚于现在，或开始日期（业务时区）不在今天之后
         *       advance_days_min–advance_days_max 天内
         *     - 403 NOT_ELIGIBLE：违约次数达到上限，details 为原因列表
         *     - 400 ROOM_NOT_BOOKABLE：教室停用或不允许整教室预约
         *     - 403 DEPT_RESTRICTED：院系教室只接受本院系申请人
         *     - 400 ATTENDEES_EXCEED_CAPACITY：参加人数超过教室容量
         *     - 400 OUTSIDE_OPEN_HOURS：时段不在教室当天的开放时间内（也因此不能跨天）
         *     - 409 APPROVAL_FLOW_NOT_FOUND：没有适用于该教室的审批流
         *     - 400 APPLICANT_DEPT_REQUIRED：审批流含院系级审批而申请人不属于任何院系
         *     - 409 APPLICATION_TIME_CONFLICT：与该教室其他 pending/approved 申请时段重叠
         *     - 404 NOT_FOUND（教室不存在）、502 UPSTREAM_UNAVAILABLE / UPSTREAM_ERROR：来自 M1
         */
        post: operations["submit_api_v1_room_applications_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/room/applications/{application_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 申请详情（含审批记录）
         * @description 申请人本人、审批过该申请的人、能审批其中任一级的人（权限码与院系范围）可以查看，
         *     其他人 404 NOT_FOUND。
         */
        get: operations["detail_api_v1_room_applications__application_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/room/applications/{application_id}/approve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 审批通过
         * @description 非最后一级：进入下一级并刷新 deadline_at，通知申请人与下一级审批人。
         *     最后一级：调用 M1 POST /internal/v1/blocks 占用教室（原因为申请用途），成功后才改为 approved。错误码：
         *
         *     - 404 NOT_FOUND：看不到该申请
         *     - 409 APPLICATION_STATE_CONFLICT：申请已不在审批中，或被并发修改
         *     - 409 APPLICATION_EXPIRED：已到当前级别截止时间或申请时段已开始（等待自动撤销）
         *     - 403 NOT_YOUR_TURN：审批自己的申请、没有当前级别的权限码、院系级而不同院系、已审批过该申请的其他级别
         *     - 502 UPSTREAM_UNAVAILABLE / UPSTREAM_ERROR 或 M1 的业务错误（原样返回，如 409 ROOM_UNDER_MAINTENANCE
         *       教室正在维修）：占用失败，申请保持 pending，可重试
         */
        post: operations["approve_api_v1_room_applications__application_id__approve_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/room/applications/{application_id}/reject": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 驳回
         * @description 任一级驳回 → rejected，通知申请人（含级别与意见）。错误码：
         *
         *     - 404 NOT_FOUND：看不到该申请
         *     - 409 APPLICATION_STATE_CONFLICT：申请已不在审批中，或被并发修改
         *     - 409 APPLICATION_EXPIRED：已到当前级别截止时间或申请时段已开始（等待自动撤销）
         *     - 403 NOT_YOUR_TURN：审批自己的申请、没有当前级别的权限码、院系级而不同院系、已审批过该申请的其他级别
         *     - 409 OCCUPY_IN_PROGRESS：最终审批正在向 M1 申请占用教室（请求后 1 分钟内），稍后再试
         */
        post: operations["reject_api_v1_room_applications__application_id__reject_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/room/applications/{application_id}/withdraw": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 撤回或取消申请
         * @description pending → withdrawn，通知当前级别审批人；approved 且未开始 → 先经 M1 释放教室，成功后 cancelled，
         *     通知审批通过过该申请的人。错误码：
         *
         *     - 404 NOT_FOUND：看不到该申请；403 FORBIDDEN：不是申请人
         *     - 409 APPLICATION_STATE_CONFLICT：已结束、已开始的已通过申请，或并发修改
         *     - 409 OCCUPY_IN_PROGRESS：撤回 pending 申请时，最终审批正在向 M1 申请占用教室（请求后 1 分钟内），稍后再试
         *     - 502 UPSTREAM_UNAVAILABLE / UPSTREAM_ERROR：取消时 M1 释放失败，申请保持 approved，可重试
         */
        post: operations["withdraw_api_v1_room_applications__application_id__withdraw_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/room/applications/mine": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 我的申请
         * @description 按提交时间倒序。
         */
        get: operations["mine_api_v1_room_applications_mine_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/room/approvals/todo": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 我的待审批
         * @description 当前用户此刻能通过或驳回的申请（与审批时的检查是同一组条件），按截止时间排序。
         *     affected_reservations 逐条向 M1 查询，失败时为空。
         */
        get: operations["todo_api_v1_room_approvals_todo_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/room/eligibility": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 检查我是否有资格申请整教室
         * @description 门槛：拥有 room:apply 权限，且近 violation_window_days 天在 M1 的违约次数 < max_violations。
         *
         *     M1 不可用时 502 UPSTREAM_UNAVAILABLE。
         */
        get: operations["eligibility_api_v1_room_eligibility_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/room/flows": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** 审批流配置 */
        get: operations["get_flows_api_v1_room_flows_get"];
        /**
         * 更新审批流配置
         * @description 整体替换，只影响之后提交的申请（在途申请使用提交时的快照）。
         *     至少一条；每级 approver_perm 须与 scope 对应（dept → room:approve，school → room:approve_school），
         *     否则 422 VALIDATION_ERROR；名称重复 409 DUPLICATE_FLOW_NAME。
         */
        put: operations["put_flows_api_v1_room_flows_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/room/settings": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** 申请参数 */
        get: operations["get_settings_api_v1_room_settings_get"];
        /**
         * 更新申请参数
         * @description advance_days_max 小于 advance_days_min 等校验失败时 422 VALIDATION_ERROR。
         */
        put: operations["put_settings_api_v1_room_settings_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** 存活检查 */
        get: operations["health_health_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ready": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** 就绪检查：数据库可用 */
        get: operations["ready_ready_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/version": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** 当前运行版本 */
        get: operations["version_version_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** Application */
        Application: {
            applicant: components["schemas"]["UserBrief"];
            /** Attendees */
            attendees: number;
            /** Current Level */
            current_level: number;
            /**
             * Deadline At
             * Format: date-time
             * @description 当前级别审批截止时间；到截止时间或申请开始时仍未审批完成则自动撤销
             */
            deadline_at: string;
            /**
             * End At
             * Format: date-time
             */
            end_at: string;
            /** Id */
            id: number;
            /** Purpose */
            purpose: string;
            /** Records */
            records: components["schemas"]["ApprovalRecordOut"][];
            /** Room Id */
            room_id: number;
            /**
             * Room Name
             * @description 提交时的教室名称快照（楼宇 名称）
             */
            room_name: string;
            /**
             * Start At
             * Format: date-time
             */
            start_at: string;
            /**
             * Status
             * @enum {string}
             */
            status: "pending" | "approved" | "rejected" | "withdrawn" | "expired" | "cancelled";
            /** Total Levels */
            total_levels: number;
        };
        /** ApplicationCreate */
        ApplicationCreate: {
            /**
             * Attendees
             * @description 不超过教室容量
             */
            attendees: number;
            /**
             * End At
             * Format: date-time
             */
            end_at: string;
            /**
             * Purpose
             * @example 班级读书会
             */
            purpose: string;
            /** Room Id */
            room_id: number;
            /**
             * Start At
             * Format: date-time
             */
            start_at: string;
        };
        /** ApplicationForApprover */
        ApplicationForApprover: {
            /**
             * Affected Reservations
             * @description 批准后将被取消的个人座位预约数；查询 M1 失败时为空（不影响待办列表）
             */
            affected_reservations: number | null;
            applicant: components["schemas"]["UserBrief"];
            /** Attendees */
            attendees: number;
            /** Current Level */
            current_level: number;
            /**
             * Deadline At
             * Format: date-time
             * @description 当前级别审批截止时间；到截止时间或申请开始时仍未审批完成则自动撤销
             */
            deadline_at: string;
            /**
             * End At
             * Format: date-time
             */
            end_at: string;
            /** Id */
            id: number;
            /** Purpose */
            purpose: string;
            /** Records */
            records: components["schemas"]["ApprovalRecordOut"][];
            /** Room Id */
            room_id: number;
            /**
             * Room Name
             * @description 提交时的教室名称快照（楼宇 名称）
             */
            room_name: string;
            /**
             * Start At
             * Format: date-time
             */
            start_at: string;
            /**
             * Status
             * @enum {string}
             */
            status: "pending" | "approved" | "rejected" | "withdrawn" | "expired" | "cancelled";
            /** Total Levels */
            total_levels: number;
        };
        /** ApprovalAction */
        ApprovalAction: {
            /** Comment */
            comment?: string | null;
        };
        /** ApprovalFlow */
        ApprovalFlow: {
            /** Dept Scoped */
            dept_scoped?: boolean | null;
            /** Levels */
            levels: components["schemas"]["FlowLevel"][];
            /** Name */
            name: string;
            /**
             * Priority
             * @default 0
             */
            priority: number;
            /** Room Type */
            room_type?: ("classroom" | "library" | "other") | null;
        };
        /** ApprovalRecordOut */
        ApprovalRecordOut: {
            /**
             * Action
             * @enum {string}
             */
            action: "approve" | "reject" | "expire" | "withdraw" | "cancel";
            /** @description 系统动作（如超时）为空 */
            approver: components["schemas"]["UserBrief"] | null;
            /**
             * At
             * Format: date-time
             */
            at: string;
            /** Comment */
            comment: string | null;
            /** Level */
            level: number;
        };
        /** Eligibility */
        Eligibility: {
            /** Eligible */
            eligible: boolean;
            /**
             * Reasons
             * @description 不满足的原因，例如 近 30 天违约 3 次，违约达到 3 次不能申请
             */
            reasons: string[];
        };
        /** ErrorBody */
        ErrorBody: {
            /** Code */
            code: string;
            /** Details */
            details?: unknown;
            /** Message */
            message: string;
            /** Request Id */
            request_id?: string | null;
        };
        /** FlowLevel */
        FlowLevel: {
            /**
             * Approver Perm
             * @description 审批人需具备的权限码，须与 scope 对应：dept → room:approve，school → room:approve_school
             * @default room:approve
             * @enum {string}
             */
            approver_perm: "room:approve" | "room:approve_school";
            /** Level */
            level: number;
            /**
             * Scope
             * @description dept：申请人所在院系的审批人；school：全校的学校级审批人
             * @enum {string}
             */
            scope: "dept" | "school";
            /**
             * Timeout Hours
             * @default 48
             */
            timeout_hours: number;
        };
        /** Page[Application] */
        Page_Application_: {
            /** Items */
            items: components["schemas"]["Application"][];
            /** Page */
            page: number;
            /** Size */
            size: number;
            /** Total */
            total: number;
        };
        /** Page[ApplicationForApprover] */
        Page_ApplicationForApprover_: {
            /** Items */
            items: components["schemas"]["ApplicationForApprover"][];
            /** Page */
            page: number;
            /** Size */
            size: number;
            /** Total */
            total: number;
        };
        /** RoomSettings */
        RoomSettings: {
            /**
             * Advance Days Max
             * @description 开始日期最晚是今天之后第几天（业务时区自然日）
             * @default 30
             */
            advance_days_max: number;
            /**
             * Advance Days Min
             * @description 开始日期最早是今天之后第几天（业务时区自然日，0 表示当天，且须晚于现在）
             * @default 1
             */
            advance_days_min: number;
            /**
             * Max Violations
             * @description 近 violation_window_days 天违约达到该次数不能申请
             * @default 3
             */
            max_violations: number;
            /**
             * Violation Window Days
             * @default 30
             */
            violation_window_days: number;
        };
        /** UserBrief */
        UserBrief: {
            /** Dept Id */
            dept_id: number | null;
            /** Id */
            id: number;
            /** Name */
            name: string;
            /** Username */
            username: string;
        };
        /** VersionInfo */
        VersionInfo: {
            /** Env */
            env: string;
            /** Git Sha */
            git_sha: string;
            /** Service */
            service: string;
            /** Version */
            version: string;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    submit_api_v1_room_applications_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ApplicationCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Application"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    detail_api_v1_room_applications__application_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                application_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Application"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    approve_api_v1_room_applications__application_id__approve_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                application_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ApprovalAction"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Application"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    reject_api_v1_room_applications__application_id__reject_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                application_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ApprovalAction"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Application"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    withdraw_api_v1_room_applications__application_id__withdraw_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                application_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Application"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    mine_api_v1_room_applications_mine_get: {
        parameters: {
            query?: {
                /** @description 页码，从 1 开始 */
                page?: number;
                /** @description 每页条数 */
                size?: number;
                status?: ("pending" | "approved" | "rejected" | "withdrawn" | "expired" | "cancelled") | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Page_Application_"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    todo_api_v1_room_approvals_todo_get: {
        parameters: {
            query?: {
                /** @description 页码，从 1 开始 */
                page?: number;
                /** @description 每页条数 */
                size?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Page_ApplicationForApprover_"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    eligibility_api_v1_room_eligibility_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Eligibility"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    get_flows_api_v1_room_flows_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApprovalFlow"][];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    put_flows_api_v1_room_flows_put: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ApprovalFlow"][];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApprovalFlow"][];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    get_settings_api_v1_room_settings_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RoomSettings"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    put_settings_api_v1_room_settings_put: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RoomSettings"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RoomSettings"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    health_health_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string;
                    };
                };
            };
        };
    };
    ready_ready_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
        };
    };
    version_version_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VersionInfo"];
                };
            };
        };
    };
}
