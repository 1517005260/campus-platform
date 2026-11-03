"""同步 dev/main 分支规则：python3 scripts/configure_branches.py owner/repo。"""

import json
import subprocess
import sys
from pathlib import Path


def api(path: str, method: str = "GET", body: dict | None = None):
    command = ["gh", "api", "-H", "X-GitHub-Api-Version: 2026-03-10", "--method", method, path]
    if body is not None:
        command += ["--input", "-"]
    result = subprocess.run(
        command,
        input=json.dumps(body) if body is not None else None,
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout) if result.stdout.strip() else None


def configure(repo: str):
    base = f"repos/{repo}"
    info = api(base)
    if info["owner"]["type"] != "User":
        # 个人仓库中只有 owner 拥有管理员角色，main 规则只对管理员放行，因此只有 owner 能合并
        raise ValueError("此配置适用于个人账号仓库；转入组织前需明确唯一的最终审核人")
    refs = api(f"{base}/git/matching-refs/heads/dev")
    if not any(ref["ref"] == "refs/heads/dev" for ref in refs):
        main = api(f"{base}/git/ref/heads/main")
        api(f"{base}/git/refs", "POST", {"ref": "refs/heads/dev", "sha": main["object"]["sha"]})

    # dev 是长期分支，不启用合并后自动删除。main 使用 merge 保留 dev 的提交祖先关系。
    api(
        base,
        "PATCH",
        {
            "allow_merge_commit": True,
            "allow_squash_merge": True,
            "allow_rebase_merge": True,
            "delete_branch_on_merge": False,
            "allow_auto_merge": False,
        },
    )
    existing = {rule["name"]: rule["id"] for rule in api(f"{base}/rulesets?per_page=100")}
    directory = Path(__file__).resolve().parent / "github"
    for filename in ["ruleset-main.json", "ruleset-main-ci.json", "ruleset-dev.json"]:
        body = json.loads((directory / filename).read_text())
        rule_id = existing.get(body["name"])
        path = f"{base}/rulesets/{rule_id}" if rule_id else f"{base}/rulesets"
        saved = api(path, "PUT" if rule_id else "POST", body)
        print(f"已同步 {saved['name']}（{saved['id']}）", flush=True)
    print(f"main 最终审核与合并人：{info['owner']['login']}；dev 允许协作者正常提交。")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("用法：python3 scripts/configure_branches.py owner/repo")
    try:
        configure(sys.argv[1])
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.stderr.strip()) from error
