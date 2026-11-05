# 需求基线与追踪

维护人：组长 `twllif`。每条需求都要有验收标准、实现位置和验证方式。做不完的需求把状态改为"延后"或"放弃"并写明原因，不要删除。

- **来源**：M1 来自任务书附件 1；M2、M3、D 由各模块组与 AI 交互细化后经组内评审确定；INT 为跨模块集成点。
- **状态**：未开始 / 桩（接口与鉴权就绪，返回假数据）/ 开发中 / 已实现 / 延后 / 放弃
- **验证**：已实现的条目写到具体测试文件或测试名；`单元` = 服务内测试；`DB` = 需要数据库的测试；`契约` = 公共库客户端对照 `contracts/openapi` 的测试；`集成` = `tests/integration` 对部署环境的测试；`演示` = 期末现场演示
- 提交信息和 PR 标题引用编号，例如 `feat(m1): ... [REQ-M1-03]`。

## M1 自习座位预约

| 编号 | 需求 | 验收标准 | 实现 | 验证 | 状态 |
|---|---|---|---|---|---|
| REQ-M1-01 | 自习室管理 | 拥有 `seat:room_manage` 的用户可登记、修改、停用自习室，设置楼宇、类型、容量、每周开放时间、所属院系；院系自习室只对本院系用户可见、可约；停用自习室或注销自习室（`is_study_room` 由 true 改为 false）后其全部座位不可预约，尚未结束的有效预约自动取消（`ADMIN_DISABLED`）、通知学生、不记违约；重新启用或重新登记不恢复已取消的预约 | `api/rooms.py`、`room_service.py`、`shared.py` | DB：`test_rooms.py`（`test_list_rooms_filters_department_and_disabled_for_students`、`test_update_room_replaces_hours_and_logs_status`、`test_disabling_room_cancels_reservations_of_all_its_seats`、`test_deregistering_study_room_cancels_like_disabling`）；`test_reservations.py::test_create_reservation_rejects_other_department` | 已实现 |
| REQ-M1-02 | 座位管理 | 可登记、停用座位；座位在教室内编号唯一；停用的座位不出现在搜索结果中；停用时该座位尚未结束的有效预约自动取消、通知学生、不记违约，之后不能签到 | `api/rooms.py`、`room_service.py`、`shared.py` | DB：`test_rooms.py`（`test_create_seat_rejects_duplicate_code`、`test_disabling_seat_cancels_unfinished_reservations_without_violation`）；`test_availability.py::test_search_excludes_disabled_seat`；`test_checkin.py::test_checkin_rejected_after_seat_disabled` | 已实现 |
| REQ-M1-03 | 按整点预约 | 起止均为整点；时长 1 至 `max_hours`（默认 4）小时，正好 `max_hours` 允许；必须在开放时间内（可以从开放时刻开始、到关闭时刻结束）；开始时刻已到不能预约；违反时返回 400 及对应错误码，结束不晚于开始返回 422；返回的时间带 `+08:00` | `api/reservations.py`、`reservation_service.py`、`shared.py` | DB：`test_reservations.py`（`test_create_reservation_accepts_exactly_max_hours`、`test_create_reservation_accepts_open_and_close_hour_edges`、`test_create_reservation_rejects_slot_starting_now`、`test_reservation_times_use_business_timezone`）；`test_api_contract.py::test_reservation_rejects_reversed_hours`；`test_stats.py::test_settings_update_affects_new_reservation` | 已实现 |
| REQ-M1-04 | 预约冲突 | 同一座位时段重叠的有效预约只能存在一个；同一用户同一时段只能有一个有效预约；并发请求也只有一个成功 | `models.py`、`reservation_service.py` | DB：`test_db_constraints.py`；`test_reservations.py`（`test_concurrent_reservations_only_one_succeeds`、`test_create_reservation_rejects_seat_overlap`、`test_create_reservation_rejects_user_overlap`、`test_create_reservation_allows_adjacent_slot`） | 已实现 |
| REQ-M1-05 | 取消预约 | 开始前可取消，取消后座位立即可被他人预约，不记违约 | `api/reservations.py`、`reservation_service.py` | DB：`test_reservations.py`（`test_cancel_reservation_records_release_and_event`、`test_cannot_cancel_started_reservation`） | 已实现 |
| REQ-M1-06 | 签到 | 每间教室每天（业务日期）一个签到码（屏幕显示码与二维码）；在开始前 15 分钟（含）至开始后 `auto_cancel_min` 分钟（不含）内输入屏幕当时显示的码签到成功，与 UTC 日期无关；码错误返回 400 `CHECKIN_CODE_INVALID` | `api/rooms.py`、`api/reservations.py`、`checkin_service.py` | DB：`test_checkin.py`（`test_checkin_succeeds_at_window_opening`、`test_checkin_rejects_just_before_window_opens`、`test_checkin_succeeds_just_before_deadline`、`test_checkin_rejects_exact_deadline`、`test_early_morning_reservation_checks_in_with_code_on_screen`、`test_midnight_reservation_checks_in_with_code_shown_before_midnight`、`test_checkin_rejects_wrong_code`） | 已实现 |
| REQ-M1-07 | 开始前提醒 | 开始前 `remind_before_min`（默认 15）分钟发送站内通知和邮件，每个预约只发一次 | `jobs.send_reminders_before` | DB：`test_jobs.py`（`test_before_reminder_*`） | 已实现 |
| REQ-M1-08 | 未签到再提醒 | 开始后 `remind_late_min`（默认 10）分钟仍未签到，再提醒一次 | `jobs.send_reminders_late` | DB：`test_jobs.py`（`test_late_reminder_*`） | 已实现 |
| REQ-M1-09 | 未签到自动取消并记违约 | 开始后 `auto_cancel_min`（默认 15）分钟仍未签到：状态变为 no_show、释放座位、通知学生、记 1 次违约；重复执行不重复记违约；已签到的不受影响 | `jobs.mark_no_shows` | DB：`test_jobs.py`（`test_not_cancelled_before_deadline`、`test_cancelled_after_deadline_with_violation_and_notification`、`test_running_twice_does_not_double_count`、`test_checked_in_reservation_untouched`） | 已实现 |
| REQ-M1-10 | 搜索座位 | 可按日期时段、楼宇、教室、插座条件搜索；只返回当前用户在该时段真正可约的座位（未被预约、未被 M2/M3 占用、座位与教室启用、院系允许、在开放时间内），与创建预约使用同一组规则；时段已开始或超过 `max_hours` 时返回与创建预约相同的错误码 | `api/rooms.py`、`availability.py`、`shared.py` | DB：`test_availability.py`（`test_search_returns_only_available_seats`、`test_search_includes_slots_touching_open_and_close_hours`、`test_search_rejects_started_slot_like_reservation`、`test_search_rejects_duration_over_max_hours`、`test_search_applies_department_rule_to_room_managers`、`test_search_excludes_disabled_seat`） | 已实现 |
| REQ-M1-11 | 历史与再次预约 | 可查看自己的历史预约；可选择一条历史记录，为同一座位预约新的时段（遵守 REQ-M1-03/04） | `api/reservations.py`、`reservation_service.py` | DB：`test_reservations.py`（`test_history_filters_and_returns_details`、`test_rebook_creates_new_reservation_for_same_seat`、`test_cannot_rebook_another_users_history`） | 已实现 |
| REQ-M1-12 | 运营统计 | 拥有 `seat:stats` 的用户可按日期范围、教室查看利用率（已签到小时数 / 有效开放座位小时数）、违约率（`no_show / (no_show + completed)`，不计 cancelled、booked）、各小时分布（ADR-012） | `api/admin.py`、`stats_service.py` | DB：`test_stats.py`（`test_usage_stats_counts_only_checked_in_and_closed_reservations`、`test_usage_stats_excludes_room_block_from_open_hours`、`test_usage_stats_does_not_merge_simultaneous_seats`） | 已实现 |
| REQ-M1-13 | 插座标记 | 座位可标记为无插座、靠近固定插座、靠近移动导轨插座；搜索可按此筛选；座位详情显示标记 | `models.Seat.outlet`、`room_service.py`、`availability.py` | DB：`test_rooms.py::test_update_seat_changes_outlet_and_logs_disable`；`test_availability.py::test_search_filters_by_outlet_and_room` | 已实现 |
| REQ-M1-14 | 系统参数 | 拥有 `seat:config` 的用户可修改 `max_hours`、提醒与自动取消的分钟数，修改后对新预约和下一轮扫描生效；`remind_late_min` 必须小于 `auto_cancel_min`，否则返回 422 | `api/admin.py`、`rules.py`、`schemas.SeatSettings` | DB：`test_stats.py`（`test_settings_defaults_and_update`、`test_settings_late_reminder_must_precede_auto_cancel`、`test_settings_update_affects_new_reservation`）；`test_jobs.py`（`test_respects_configured_deadline`、`test_before_reminder_respects_configured_window`） | 已实现 |
| REQ-M1-15 | 违约记录 | 学生可查看自己的违约记录 | `api/reservations.py`、`reservation_service.py` | DB：`test_reservations.py::test_my_violations_returns_only_current_user` | 已实现 |
| REQ-M1-16 | 每日总时长限制 | 限制每人每天的预约总时长，避免连续预约绕过单次 `max_hours` | — | — | 延后：任务书只规定单次最多 4 小时；规则与参数尚未定义，可能误伤学生（ADR-012、`docs/ethics-log.md`） |
| REQ-M1-17 | 最远预约天数 | 限制最远可提前预约的天数，保护远期资源 | — | — | 延后：任务书未要求，增加参数会扩大接口与前端契约；v1 不限制（ADR-012） |
| REQ-M1-18 | 签到码防暴力尝试 | 限制同一用户或同一预约的签到码错误次数，防止 6 位码被穷举 | — | — | 延后：需要先确定限制口径与误伤处理；作为伦理与安全风险记录（ADR-012） |
| REQ-M1-19 | 违约申诉 | 学生可对违约记录申诉，管理员可撤销误判的违约 | — | — | 延后：涉及新的角色流程与 M2 门槛口径，待需求评审（`docs/ethics-log.md` E-01） |

## D 公共层（common 服务）

| 编号 | 需求 | 验收标准 | 实现 | 验证 | 状态 |
|---|---|---|---|---|---|
| REQ-D-01 | 登录 | 用户名密码正确返回 JWT，token 含用户、院系、角色、权限码；错误返回 401 `LOGIN_FAILED`；停用用户不能登录；每个环境都有可登录的引导管理员 `admin` | `api/auth.py` | DB：`common/tests/test_auth.py`（正确登录、密码错误、停用用户）；`test_seed.py`（引导管理员） | 已实现 |
| REQ-D-02 | 角色与权限 | 拥有 `admin:role` 的用户可新建角色、修改角色名称与权限码、删除无用户的自定义角色；权限码必须存在于目录（400 `UNKNOWN_PERMISSION`）；只能增删自己拥有的权限码（403 `PERMISSION_ESCALATION`）；预置角色不可删除、不可改名，权限可调整；系统管理员角色必须保留 `admin:user`、`admin:role`；变更在用户下次登录后生效 | `api/admin.py`、`rbac.py`；前端"角色与权限" | DB：`common/tests/test_admin_roles.py`（`test_new_role_grants_its_permissions_at_next_login`、`test_unknown_permission_rejected`、`test_builtin_role_perms_editable_but_name_fixed`、`test_builtin_role_cannot_be_deleted_even_when_unused`、`test_sys_admin_keeps_admin_permissions`、`test_delete_custom_role_only_when_unused`、`test_role_admin_cannot_add_permissions_they_lack`、`test_role_admin_cannot_remove_permissions_they_lack`、`test_role_admin_cannot_create_role_with_permissions_they_lack`） | 已实现 |
| REQ-D-03 | 用户管理 | 拥有 `admin:user` 的用户可按用户名/姓名、院系、角色、状态分页查询用户，新建用户（用户名唯一 409 `USERNAME_EXISTS`，院系、角色必须存在），修改资料与院系、重置密码，停用/启用用户，设置用户角色；停用用户不能登录、不再出现在按权限查用户的结果中；不能分配或管理超出自己权限的角色（403 `PERMISSION_ESCALATION`），不能停用自己或移除自己的 `admin:user`（409 `SELF_LOCKOUT`）；变更在用户下次登录后生效，设置角色时通知该用户 | `api/admin.py`、`rbac.py`；前端"用户管理" | DB：`common/tests/test_admin_users.py`（`test_created_user_can_log_in_with_role_permissions`、`test_duplicate_username_rejected`、`test_list_filters_and_paginates`、`test_disabled_user_cannot_log_in_and_is_hidden_from_other_services`、`test_set_roles_takes_effect_at_next_login_and_notifies_user`、`test_user_manager_manages_students_and_teachers`、`test_user_manager_cannot_grant_roles_beyond_own_permissions`、`test_user_manager_cannot_strip_roles_from_more_privileged_account`、`test_user_manager_cannot_modify_more_privileged_account`、`test_cannot_disable_self`） | 已实现 |
| REQ-D-04 | 院系 | 维护院系列表（新建、改名，名称唯一 409 `DEPT_EXISTS`；不能删除，因为其他模块按 ID 引用院系）；用户归属一个院系（可为空）；演示数据使用复旦大学的真实院系名称 | `api/admin.py`、`rbac.py`、`seed.py`；前端"院系" | DB：`common/tests/test_admin_roles.py`（`test_create_and_rename_dept`、`test_dept_name_unique`）；`test_admin_users.py::test_update_profile_clears_dept_and_resets_password`；`test_seed.py::test_demo_ids_referenced_by_other_services_are_stable` | 已实现 |
| REQ-D-05 | 站内通知 | 收到 `notification.send` 消息后按模板渲染（时间按业务时区）为每个用户生成站内通知，未知模板仍落库；同一消息重复投递只生成一次；用户只能查看自己的通知（未读筛选、分页、最新在前）、查看未读数、标记已读（幂等）、全部标为已读 | `consumers.py`、`templates.py`、`notification_service.py`、`api/notifications.py`；前端顶栏铃铛与"我的通知" | DB：`common/tests/test_consumers.py`（`test_duplicate_notification_processed_once`、`test_notification_rendered_in_business_timezone`、`test_unknown_template_or_missing_params_still_stored`）；`test_notifications.py`（`test_list_only_own_newest_first`、`test_mark_read_is_idempotent_and_updates_filters`、`test_cannot_mark_someone_elses_notification`、`test_mark_all_read_only_touches_own`） | 已实现 |
| REQ-D-06 | 邮件通知 | channels 含 email 的通知通过 SMTP 发给启用且有邮箱的用户（开发、测试环境发往 Mailpit；未配置 SMTP 时只保留站内信），每条只发一次，多个 worker 不重复发送；某一封邮件自身的错误（收件人被拒、内容被拒、地址无法编码）只影响这一封，记录失败次数后重试，失败 3 次后放弃，不挡住其他邮件；服务器不可用时停止本轮、下轮重试；创建超过 24 小时仍未发出的不再补发 | `jobs.send_pending_emails`、`mailer.py` | DB：`common/tests/test_jobs.py`（`test_sends_email_once_and_marks_sent`、`test_nothing_sent_when_smtp_not_configured`、`test_message_error_skips_only_that_message`、`test_failed_message_retried_until_attempt_limit`、`test_failing_message_does_not_block_newer_ones`、`test_server_error_while_sending_stops_round`、`test_server_down_stops_round_without_counting_attempts`、`test_stale_notifications_not_emailed`、`test_row_locked_by_another_worker_is_skipped`）；单元：`test_mailer.py` | 已实现 |
| REQ-D-07 | 操作审计 | 收到 `audit.record` 后落库，保留 request_id 以关联同一次操作的多个记录；common 自身的管理操作与业务数据在同一事务里写审计，不记录密码 | `consumers.py`、`audit.py` | DB：`common/tests/test_consumers.py::test_audit_keeps_request_id`；`test_admin_users.py::test_create_writes_audit_without_password` | 已实现 |
| REQ-D-08 | 审计查询 | 拥有 `audit:read` 的用户可按操作人、模块、动作、对象、时间段 `[起, 止)`（必须带时区）分页查询审计记录，最新在前 | `api/audit.py`、`audit.py`；前端"操作审计" | DB：`common/tests/test_audit.py`（`test_filters_by_actor_module_and_target`、`test_time_range_includes_start_excludes_end`、`test_naive_time_rejected`、`test_requires_audit_read`） | 已实现 |
| REQ-D-09 | 按权限查用户 | 其他服务可按权限码（及院系）查询启用的用户，用于查找审批人、维修工 | `api/internal.py` | DB：`common/tests/test_auth.py::test_users_with_perm_filters_by_dept`；`test_admin_users.py::test_disabled_user_cannot_log_in_and_is_hidden_from_other_services` | 已实现 |

## M2 整教室预约与审批

| 编号 | 需求 | 验收标准 | 实现 | 验证 | 状态 |
|---|---|---|---|---|---|
| REQ-M2-01 | 权限门槛 | 拥有 `room:apply` 且近 `violation_window_days`（默认 30）天在 M1 的违约次数小于 `max_violations`（默认 3）才能申请；不满足时说明原因 | `api/applications.py eligibility` | DB：`m2-room/tests/test_api_contract.py`（上限边界、统计窗口、读取调整后的参数） | 部分（违约判断已实现） |
| REQ-M2-02 | 提交申请 | 只能申请 `is_whole_bookable` 的教室；时间在 `advance_days_min`–`advance_days_max` 天之后；与其他 pending/approved 申请时段不重叠；提交后进入第 1 级审批 | `api/applications.py submit` | 单元、DB | 桩 |
| REQ-M2-03 | 审批流配置 | 拥有 `room:flow_manage` 的用户可配置审批流（级数、每级审批范围 dept/school、超时时长）；修改只影响新申请 | `api/approvals.py` | DB | 桩 |
| REQ-M2-04 | 多级审批 | 审批人只能处理当前级别且在其范围内的申请；非最后一级通过进入下一级；最后一级通过后经 M1 占用教室并变为 approved；任一级驳回变为 rejected | `api/approvals.py` | 单元、DB、集成 | 桩 |
| REQ-M2-05 | 超时自动撤销 | 当前级别超过截止时间未处理，自动变为 expired 并通知申请人；与审批同时发生时只有一方生效 | `jobs.expire_overdue` | DB | 未开始 |
| REQ-M2-06 | 撤回与取消 | 审批中可撤回（withdrawn）；已通过、未开始的申请可取消（cancelled）并经 M1 释放教室 | `api/applications.py withdraw` | 单元、集成 | 桩 |
| REQ-M2-07 | 查询 | 申请人可查看自己的申请及每一级审批记录 | `api/applications.py` | 单元 | 桩 |
| REQ-M2-08 | 影响提示 | 审批人在待办中看到批准后将被取消的个人座位预约数 | `api/approvals.py todo` | 单元 | 桩 |
| REQ-M2-09 | 通知 | 提交、每级审批结果、超时、取消时通知相关人 | outbox | DB | 未开始 |

## M3 物业报修工单

| 编号 | 需求 | 验收标准 | 实现 | 验证 | 状态 |
|---|---|---|---|---|---|
| REQ-M3-01 | 上报故障 | 拥有 `repair:report` 的用户选择教室（及可选座位）、分类、描述、照片提交工单；教室必须存在于 M1（M1 返回 404 时为 400 `ROOM_NOT_FOUND`，M1 不可达为 502）；分类不在配置中为 400 `UNKNOWN_CATEGORY`；按权限码通知全部调度员（`repair:dispatch`，由 common 解析收件人，上报不依赖 common 在线） | `orders.report`、`api/orders.py` | DB：`test_orders.py`（`test_full_flow_blocks_on_start_keeps_block_on_reject_and_releases_on_accept`、`test_report_unknown_room_is_400_room_not_found`、`test_report_when_m1_unreachable_is_502`、`test_each_step_notifies_the_right_people_with_template_params`） | 已实现 |
| REQ-M3-02 | 取消工单 | 只有报修人本人、只在 submitted 状态可取消（看不到工单的人 404，看得到但不是报修人 403 `FORBIDDEN`，已派单 409 `ORDER_STATE_CONFLICT`）；通知调度员不必再派单 | `orders.cancel` | DB：`test_orders.py`（`test_cancel_only_by_reporter_before_dispatch_and_notifies_dispatchers`、`test_cancel_after_dispatch_is_rejected`） | 已实现 |
| REQ-M3-03 | 派单 | 调度员只能对 submitted 工单派单（否则 409），指定维修工（必须拥有 `repair:work`，经 common 校验，否则 400 `ASSIGNEE_NOT_WORKER`）、截止时间（必须晚于现在，否则 400 `DEADLINE_NOT_FUTURE`），并决定维修期间是否下架教室；通知维修工 | `orders.dispatch` | DB：`test_orders.py`（`test_dispatch_requires_assignee_with_repair_work`、`test_dispatch_deadline_must_be_in_future`、`test_dispatch_only_from_submitted`） | 已实现 |
| REQ-M3-04 | 维修中 | 只有被指派的维修工能开始（看不到工单 404，看得到但不是被指派人 403 `NOT_ASSIGNEE`），状态 dispatched → in_progress，通知报修人；需下架教室时先经 M1 下架，失败则状态不变；下架起点在首次尝试时固定，重试发出相同请求；不需下架时不调用 M1 | `orders.start`、`clients.block_room` | DB：`test_orders.py`（`test_only_assignee_starts_and_completes`、`test_start_and_complete_require_matching_state`、`test_m1_block_failure_keeps_order_dispatched`、`test_start_retry_after_lost_m1_response_sends_identical_request`、`test_room_not_blocked_never_calls_m1_block_or_release`）；集成：`test_m3_maintenance_blocks_and_restores_room` | 已实现 |
| REQ-M3-05 | 完工 | 只有被指派的维修工能提交完工说明，in_progress → pending_acceptance；教室在验收前保持下架；通知报修人验收 | `orders.complete` | DB：`test_orders.py`（`test_only_assignee_starts_and_completes`、`test_full_flow_blocks_on_start_keeps_block_on_reject_and_releases_on_accept`、`test_each_step_notifies_the_right_people_with_template_params`） | 已实现 |
| REQ-M3-06 | 验收与评价 | 报修人评分 1–5 并验收，工单关闭；曾下架时先经 M1 恢复教室，M1 失败时工单保持 pending_acceptance、重试可关闭；释放期间工单保持锁定，并发的验收不通过不会让已恢复教室的工单退回维修；只有报修人能验收不通过（退回 in_progress、教室保持下架、通知维修工）；不在待验收时 409 | `orders.accept`、`orders.reject` | DB：`test_orders.py`（`test_full_flow_blocks_on_start_keeps_block_on_reject_and_releases_on_accept`、`test_m1_release_failure_keeps_pending_then_retry_closes`、`test_accept_keeps_order_locked_while_releasing_room`、`test_only_reporter_may_reject`、`test_accept_by_other_reporter_is_404_like_other_endpoints`、`test_accept_only_from_pending_acceptance_and_room_stays_blocked`）；集成：`test_m3_maintenance_blocks_and_restores_room` | 已实现 |
| REQ-M3-07 | 超时升级 | 工单在 dispatched / in_progress / pending_acceptance 状态停留达到配置时长（进入该状态或上次升级时间 + timeout_hours，含该时刻）升级一级、写时间线，并按权限码通知 `notify_perm`（默认 `repair:manage`）；同一超时只升级一次，再过一个周期升级下一次；状态变化重新计时；到期条件在查询中，未到期工单再多也不会挡住到期工单；不依赖 common 在线 | `jobs.escalate_overdue` | DB：`test_jobs.py`（`test_escalates_exactly_at_timeout_and_once_per_period`、`test_escalation_notifies_manage_permission_holders`、`test_escalation_does_not_call_common`、`test_status_change_restarts_the_clock`、`test_overdue_order_found_behind_a_full_batch_of_not_due_orders`） | 已实现 |
| REQ-M3-08 | 代验收 | 完工后 `admin_accept_after_hours`（含该时刻）仍未验收时，`repair:manage` 可代为验收，`closed_by` 记录实际操作人；未到时间 403 `ADMIN_ACCEPT_TOO_EARLY` | `orders.accept` | DB：`test_orders.py::test_manager_accepts_only_after_waiting_period`（差 1 秒与正好到期两侧） | 已实现 |
| REQ-M3-09 | 查询与时间线 | 报修人查看自己的工单；调度员与管理员按状态、教室、维修工、是否升级筛选；维修工只看到派给自己的；详情含完整时间线；看不到的工单一律 404；人员姓名来自 M3 保存的快照，读接口不调用 common | `orders.list_mine`、`orders.list_orders`、`orders.detail` | DB：`test_orders.py`（`test_list_filters_and_worker_sees_only_assigned`、`test_reads_show_people_without_calling_common`、`test_snapshot_name_refreshes_when_user_acts_again`、`test_full_flow_blocks_on_start_keeps_block_on_reject_and_releases_on_accept`） | 已实现 |
| REQ-M3-10 | 报修配置 | 拥有 `repair:manage` 的用户配置分类、升级规则（每个状态最多一条，否则 422）与代验收时长；上报按配置的分类校验 | `orders.get_settings/put_settings`、`api/work.py` | DB：`test_orders.py`（`test_settings_categories_drive_report_validation`、`test_settings_reject_two_escalation_rules_for_one_status`） | 已实现 |

## 跨模块集成

| 编号 | 需求 | 验收标准 | 实现 | 验证 | 状态 |
|---|---|---|---|---|---|
| INT-01 | M3 → M1 维修下架 | 需下架的工单进入维修中后，该教室全部座位不出现在搜索结果中、不可预约；验收通过后自动恢复；一个工单号只对应一次下架：释放后用同一幂等键重发得到首次结果的重放、不会重新下架，同一幂等键换了请求内容返回 409 `IDEMPOTENCY_KEY_REUSED`，换了幂等键返回 409 `BLOCK_ALREADY_RELEASED`；M3 的下架请求按工单固定（起点保存在工单上），重试不会触发 `IDEMPOTENCY_KEY_REUSED` | M1 `internal.py`、`block_service.py`；M3 `orders.start/accept`、`clients.py` | DB：M1 `test_internal_blocks.py`（`test_create_block_cancels_overlapping_reservations_and_records_sources`、`test_open_ended_block_cancels_all_future_overlaps`、`test_release_block_is_idempotent_and_writes_unblocked_logs`、`test_reposting_released_block_follows_idempotency_then_lifecycle`）、`test_availability.py::test_search_returns_only_available_seats`；M3 `test_orders.py`（`test_full_flow_blocks_on_start_keeps_block_on_reject_and_releases_on_accept`、`test_start_retry_after_lost_m1_response_sends_identical_request`）；集成：`test_cross_module.py::test_m3_maintenance_blocks_and_restores_room` | 已实现 |
| INT-02 | M2 → M1 整室占用 | 最终审批通过后，教室在申请时段内不接受个人预约；取消后恢复；M2 只能占用和释放 `M2_OCCUPY` 来源的占用 | M1 `internal.py`、`block_service.py`、M2 `clients.py` | DB：`test_internal_blocks.py`（`test_m2_occupation_cancels_with_m2_reason`、`test_service_cannot_use_another_modules_block_source`、`test_service_cannot_release_another_modules_block`）；`test_reservations.py::test_create_reservation_rejects_room_block`；真实链路集成待联调 | 开发中（M1 侧已实现） |
| INT-03 | 写入来源追溯 | 每次座位状态变化记录来源（M1_RESERVATION / M1_ADMIN / M2_OCCUPY / M3_MAINTENANCE）和来源单号，可按座位查询 | M1 `seat_status_logs`、`availability.py` | DB：`test_internal_blocks.py`、`test_availability.py::test_status_history_returns_source_and_reference`、`test_rooms.py`（`M1_ADMIN` 停用与释放日志） | 开发中（M1 侧已实现） |
| INT-04 | 占用冲突处理 | 占用时段内已有的个人预约自动取消、通知学生（通知收件人为预约学生，时间带 `+08:00`）、不记违约；接口返回被取消的预约 | M1 `block_service.py`、`shared.release_reservation` | DB：`test_internal_blocks.py`（`test_create_block_cancels_overlapping_reservations_and_records_sources`、`test_block_only_cancels_reservations_that_overlap`） | 开发中（M1 侧已实现，待真实联调） |
| INT-05 | 违约影响申请门槛 | 见 REQ-M2-01；M1 统计 `created_at >= since` 的违约次数 | M1 `internal.py`、`block_service.py`、M2 `clients.py` | DB：`test_internal_blocks.py::test_internal_violation_count_includes_since_boundary` | 开发中（M1 侧已实现） |
| INT-06 | 跨模块操作审计 | 每次占用、释放都记审计，包含调用方服务名和 request_id | M1 `block_service.py`、Outbox → common | `test_internal_blocks.py` | 开发中（M1 侧已实现，待真实联调） |
| INT-07 | 幂等 | 同一占用请求重复调用（同一幂等键）只生效一次，返回首次结果；同一幂等键对应不同请求内容时返回 409 `IDEMPOTENCY_KEY_REUSED`；调用方的重试必须发出相同内容（M3 下架起点在首次尝试前保存；公共库 M1 客户端把时间统一换到业务时区再序列化） | `campus_common.idempotency`、M1 `internal.py`、M3 `orders.start` | DB：`test_idempotency.py`；`test_internal_blocks.py`（`test_same_idempotency_key_returns_first_result_once`、`test_concurrent_requests_with_same_key_create_one_block`、`test_concurrent_requests_with_different_keys_create_one_block`、`test_same_key_with_different_body_is_rejected`）；`test_clients_contract.py::test_m1_block_request_is_identical_for_the_same_instant_in_any_offset`；M3 `test_orders.py::test_start_retry_after_lost_m1_response_sends_identical_request` | 开发中（M1、M3 侧已实现，M2 待实现） |

## 非功能需求

| 编号 | 需求 | 验收标准 | 验证 | 状态 |
|---|---|---|---|---|
| NFR-01 | 数据隔离 | 每个服务只能访问自己的 schema，跨 schema 查询被数据库拒绝 | DB：`m1-seat/tests/test_schema_isolation.py`（CI 中各服务以自身角色运行） | 已实现 |
| NFR-02 | 消息可靠 | 业务提交后消息一定发出；路由不到的消息被留存；重复投递只处理一次；临时故障自动延迟重试，永久错误进入死信队列且可重放（ADR-010） | 单元：`libs/campus_common/tests/test_consuming*.py`、`test_retry.py`、`test_topology.py`、`test_outbox.py`；部署环境演练 | 已实现（公共库） |
| NFR-03 | 自动部署 | 合并到 main 后无人工干预部署到测试环境并运行集成测试 | 演示 | 已配置，待服务器 |
| NFR-04 | 发布与回滚 | 生产发布需审批；可回滚到任一历史版本；`/ops/<服务>/version` 显示当前版本 | 演示 | 已配置，待服务器 |
| NFR-05 | 迁移可重放 | 空库一次重放到最新；`alembic check` 无差异；种子幂等（两次执行各表行数不变） | CI：test 任务（重放、`alembic check`、回退重放、种子两次行数比对） | 已实现 |
| NFR-06 | 运维基线 | 各进程有健康检查；按依赖顺序启动；最小权限（数据库角色、消息业务账号、进程级密钥）；非 root 运行；部署前与每日备份（ADR-011） | 部署环境演练 | 已实现，待服务器 |
| NFR-07 | 发布门禁 | 只有通过测试环境集成测试的镜像能发布到生产；版本标签不可修改；部署后校验运行版本与提交 | 演示 | 已配置，待服务器 |
| NFR-08 | 传输加密 | 生产入口使用 HTTPS（TLS 证书、HTTP 跳转、HSTS） | 演示 | 延后：服务器与域名尚未确定，测试阶段经公网 IP 以 HTTP 访问（R-13） |

## 附加项

| 编号 | 需求 | 验收标准 | 状态 |
|---|---|---|---|
| EXT-01 | 自然语言业务代理（设计见 `docs/design/dsh-agent.md`） | 以 DSH 插件形式接入；覆盖 M1 查座位/预约/查历史、M2 申请/查询/撤回、M3 报修/查询/取消；只调用网关公开接口；意图不明确时追问（如"我要预约一间教室"追问时间和区域）；插件安装配置纳入流水线 | 未开始（第 10–11 周） |
