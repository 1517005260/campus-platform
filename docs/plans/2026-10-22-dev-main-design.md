# dev 开发与 owner 审核 main

用户确认：有写权限的协作者都可向 `dev` 提交代码；任何人可发起 `dev → main` 的 PR，项目 owner `1517005260` 负责最终审核处理。规则只保留实现这一点所必需的部分。

## 规则

- `dev`（`protect-dev`）：长期开发分支，允许直接提交和合并，不要求 PR；只禁止删除和强推。
- `main`（`protect-main`）：禁止删除和强推；必须通过 PR 更新，只允许 merge commit；`update` 规则禁止所有人更新 main，只对仓库管理员角色在 PR 中放行。个人仓库中只有 owner 是管理员，因此只有 owner 能合并。
- 不设必需状态检查，也不设来源检查工作流：只有 owner 能合并，CI 结果和 PR 来源由 owner 合并前确认。不要求批准数，owner 自己发起的 PR 也可以直接合并。
- 关闭自动合并与合并后自动删除分支，保留 dev 长期分支。

## 同步与验证

`python3 scripts/configure_branches.py 1517005260/campus-platform` 创建缺失的 dev 分支，并幂等同步两条规则及合并设置；只使用 `gh api`。

验证：读取远端规则，确认 main 的绕过名单只有管理员角色且模式为 `pull_request`。没有第二个真实协作者账号时，不声称做过跨账号实际合并测试。

每次发布合并后，下一轮开发前将 main 的合并提交同步回 dev：先 fetch，再在 dev 上 `git merge --ff-only origin/main`；若 dev 已继续开发，则按正常流程合并 main，冲突由人处理。
