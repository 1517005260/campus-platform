#!/usr/bin/env bash
# 一次性配置 GitHub 仓库：标签、main 分支保护、test/production 环境与审批人。
# 可重复执行。网页上只需手动做两件事：创建 Organization、申请学生包（私有仓库需要 Pro/Team 才能用分支保护和环境审批）。
#
# 用法：scripts/github_setup.sh <owner/repo> [生产审批人 GitHub 用户名，空格分隔]
#   例：scripts/github_setup.sh campus-team/campus-platform member-e member-c
# 首次提交时成员尚未加入：可以先不传审批人运行，成员加入、替换 CODEOWNERS 占位符后再运行一次。
set -euo pipefail
cd "$(dirname "$0")"

REPO="$1"
shift
APPROVERS=("$@")

# CODEOWNERS 中的占位符要换成真实用户名后，Code Owners 审核才会生效
if grep -q '@member-' ../.github/CODEOWNERS; then
  echo "提示：.github/CODEOWNERS 仍是 @member-x 占位符，成员加入并替换后 Code Owners 审核才生效" >&2
fi

echo "== 标签"
gh label create breaking-change-approved --repo "$REPO" --color B60205 --force \
  --description "跨模块接口的破坏性变更，所有调用方已确认适配"
gh label create schema-change --repo "$REPO" --color FBCA04 --force --description "包含数据库迁移"
gh label create cross-module --repo "$REPO" --color 1D76DB --force --description "涉及跨模块契约或公共库"
gh label create ethics --repo "$REPO" --color 5319E7 --force --description "工程伦理问题，结论同步到 docs/ethics-log.md"
for m in m1 m2 m3 common; do
  gh label create "module:$m" --repo "$REPO" --color C5DEF5 --force
done

# 按 name 创建或更新 ruleset，可重复执行
apply_ruleset() {
  local name existing
  name="$(jq -r .name "$1")"
  existing="$(gh api --paginate "repos/$REPO/rulesets" --jq ".[] | select(.name==\"$name\") | .id")"
  if [[ -n "$existing" ]]; then
    gh api -X PUT "repos/$REPO/rulesets/$existing" --input "$1" > /dev/null
  else
    gh api -X POST "repos/$REPO/rulesets" --input "$1" > /dev/null
  fi
}

# 环境允许部署的分支或标签：已存在时跳过，其他错误照常失败
ensure_deployment_ref() {
  local env="$1" name="$2" type="$3" found
  found="$(gh api --paginate "repos/$REPO/environments/$env/deployment-branch-policies" \
    --jq ".branch_policies[] | select(.name==\"$name\" and .type==\"$type\") | .id")"
  [[ -n "$found" ]] || gh api -X POST "repos/$REPO/environments/$env/deployment-branch-policies" \
    -f name="$name" -f type="$type" > /dev/null
}

echo "== main 分支保护（ruleset）"
apply_ruleset github/ruleset-main.json

# 两条 ruleset：创建规则对仓库管理员（发布负责人）放行；修改、删除规则没有任何人可绕过，
# 推送无法改写或删除已发布的版本标签（要例外处理只能由管理员先在仓库设置中停用该规则）
echo "== v* 标签保护（ruleset）：只有仓库管理员能创建；创建后不能修改或删除"
apply_ruleset github/ruleset-tags-create.json
apply_ruleset github/ruleset-tags-immutable.json

echo "== 环境"
# test 环境只允许 main 使用：其他分支上的工作流拿不到测试服务器密钥，也无法给镜像加 verified 标签
gh api -X PUT "repos/$REPO/environments/test" --input - > /dev/null << 'JSON'
{"deployment_branch_policy": {"protected_branches": false, "custom_branch_policies": true}}
JSON
ensure_deployment_ref test main branch

# 生产部署工作流检查仓库变量 PROD_APPROVERS_CONFIGURED：没有审批人时拒绝部署，而不是无人审批直接发布
if [[ ${#APPROVERS[@]} -eq 0 ]]; then
  echo "提示：未指定生产审批人，生产部署在配置审批人之前会被拒绝；成员加入后带上审批人再运行一次" >&2
  if gh variable list --repo "$REPO" --json name --jq '.[].name' | grep -qx PROD_APPROVERS_CONFIGURED; then
    gh variable delete PROD_APPROVERS_CONFIGURED --repo "$REPO"
  fi
else
  gh variable set PROD_APPROVERS_CONFIGURED --repo "$REPO" --body true
fi
reviewers="$(for u in ${APPROVERS[@]+"${APPROVERS[@]}"}; do gh api "users/$u" --jq '{type: "User", id: .id}'; done | jq -s .)"
jq -n --argjson r "$reviewers" '{
  reviewers: $r,
  prevent_self_review: true,
  deployment_branch_policy: { protected_branches: false, custom_branch_policies: true }
}' | gh api -X PUT "repos/$REPO/environments/production" --input - > /dev/null
# 允许部署到生产的引用：v* 标签（发布）和 main 分支（Actions 页面手动回滚到旧版本）。两者都需审批。
ensure_deployment_ref production 'v*' tag
ensure_deployment_ref production main branch

echo "== 仓库合并设置：只允许 squash，合并后删除分支"
gh api -X PATCH "repos/$REPO" -F allow_squash_merge=true -F allow_merge_commit=false \
  -F allow_rebase_merge=false -F delete_branch_on_merge=true > /dev/null

cat <<MSG
完成。接下来：
  1. 可选：scripts/gen_secrets.sh test && scripts/gen_secrets.sh production   # 用随机密钥替换默认值（首次部署前）
     单服务器方案：gh variable set TEST_ENV_FILE --body test-single-server.env --repo $REPO
  2. 在 test / production 环境下设置 secrets：DEPLOY_HOST、DEPLOY_USER、DEPLOY_SSH_KEY、
     DEPLOY_KNOWN_HOSTS（在可信网络中执行 ssh-keyscan <服务器> 并核对指纹后的输出）
  3. 在服务器上运行 deploy/server_init.sh
MSG
