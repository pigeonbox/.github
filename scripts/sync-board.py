#!/usr/bin/env python3
"""pigeonbox 公开质量看板同步（pigeonbox#366）。

Projects v2 不会自动跟进 org 的 issue，本脚本把「跨仓质量视图」补齐：

  - 建/复用公开项目「PigeonBox 质量看板」；
  - 字段：Category（Security/Correctness/Reliability/Platform/Product/Community）、
    Triage（已验证缺陷/待确认问题/未来功能提案）、Repo（仓名）、Train（列车号，发版时回填）；
  - 视图：总览 / 按分类（看板）/ 按列车 / 按仓 / 待确认 / 未来提案；
  - 把 org 全部 open issue 入板并按标题/标签打标（幂等：重复跑只更新）。

用法：
  python3 scripts/sync-board.py            # dry-run（只打印计划）
  python3 scripts/sync-board.py --apply    # 落地（建项目/字段/视图/入板）

环境：gh CLI 已登录（token 需 project 权限）。ORG 默认 pigeonbox。
维护约定见 docs/PROJECT-BOARD.md。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

ORG = os.environ.get("ORG", "pigeonbox")
PROJECT_TITLE = os.environ.get("PROJECT_TITLE", "PigeonBox 质量看板")

CATEGORIES = [
    ("Security", "RED"),
    ("Correctness", "ORANGE"),
    ("Reliability", "YELLOW"),
    ("Platform", "GREEN"),
    ("Product", "BLUE"),
    ("Community", "PURPLE"),
]
TRIAGE = [
    ("已验证缺陷", "RED"),
    ("待确认问题", "YELLOW"),
    ("未来功能提案", "GRAY"),
]


def gql(query: str, variables: dict | None = None) -> dict:
    body = json.dumps({"query": query, "variables": variables or {}})
    p = subprocess.run(
        ["gh", "api", "graphql", "--input", "-"],
        input=body, capture_output=True, text=True,
    )
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or p.stdout.strip())
    data = json.loads(p.stdout)
    if data.get("errors"):
        raise RuntimeError(json.dumps(data["errors"], ensure_ascii=False))
    return data["data"]


def rest(path: str) -> dict:
    p = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or p.stdout.strip())
    return json.loads(p.stdout)


def org_id() -> str:
    d = gql('query($org:String!){organization(login:$org){id}}', {"org": ORG})
    return d["organization"]["id"]


FIELDS_Q = """
query($org:String!){
  organization(login:$org){
    projectsV2(first:50){
      nodes{
        id number title url public
        fields(first:50){
          nodes{
            __typename
            ... on ProjectV2FieldCommon{ id name }
            ... on ProjectV2SingleSelectField{ id name options{ id name } }
          }
        }
      }
    }
  }
}
"""


def find_project() -> dict | None:
    d = gql(FIELDS_Q, {"org": ORG})
    for p in d["organization"]["projectsV2"]["nodes"]:
        if p["title"] == PROJECT_TITLE:
            return p
    return None


def ensure_project(apply: bool) -> dict:
    p = find_project()
    if p:
        print(f"= 复用项目 #{p['number']} {p['title']} {p['url']}")
        return p
    print(f"+ 创建项目 {PROJECT_TITLE}（public）")
    if not apply:
        return {"id": "DRY", "number": 0, "url": "(dry-run)", "fields": {"nodes": []}}
    d = gql(
        "mutation($input:CreateProjectV2Input!){createProjectV2(input:$input){projectV2{id number url}}}",
        {"input": {"ownerId": org_id(), "title": PROJECT_TITLE}},
    )
    proj = d["createProjectV2"]["projectV2"]
    # public 不在 CreateProjectV2Input 里（只在 UpdateProjectV2Input）⇒ 建完再置公开。
    gql(
        """mutation($input:UpdateProjectV2Input!){updateProjectV2(input:$input){projectV2{id public url}}}""",
        {"input": {"projectId": proj["id"], "public": True}},
    )
    print(f"+ 已创建并置公开 {proj['url']}")
    return {"id": proj["id"], "number": proj["number"], "url": proj["url"], "fields": {"nodes": []}}


def field_map(project: dict) -> dict[str, dict]:
    out = {}
    for f in project["fields"]["nodes"]:
        out[f["name"]] = f
    return out


def ensure_single_select(project: dict, name: str, options: list[tuple[str, str]], apply: bool) -> dict:
    fields = field_map(project)
    if name in fields:
        have = {o["name"]: o["id"] for o in fields[name].get("options") or []}
        missing = [n for n, _ in options if n not in have]
        if not missing:
            print(f"= 字段 {name} 已存在（{len(have)} 项）")
            return fields[name]
        print(f"+ 字段 {name} 补选项: {missing}")
        if not apply:
            return fields[name]
        # 追加选项：updateProjectV2Field 需要全量 options（现有 + 新）。
        opts = [{"name": n, "color": c, "description": ""} for n, c in options]
        d = gql(
            """mutation($input:UpdateProjectV2FieldInput!){updateProjectV2Field(input:$input){
                 projectV2Field{ ... on ProjectV2SingleSelectField{ id name options{ id name } } } }}""",
            {"input": {"fieldId": fields[name]["id"], "singleSelectOptions": opts}},
        )
        return d["updateProjectV2Field"]["projectV2Field"]
    print(f"+ 创建字段 {name}: {[n for n, _ in options]}")
    if not apply:
        return {"id": "DRY-" + name, "name": name, "options": [{"name": n, "id": "DRY"} for n, _ in options]}
    opts = [{"name": n, "color": c, "description": ""} for n, c in options]
    d = gql(
        """mutation($input:CreateProjectV2FieldInput!){createProjectV2Field(input:$input){
             projectV2Field{ ... on ProjectV2SingleSelectField{ id name options{ id name } } } }}""",
        {"input": {"projectId": project["id"], "dataType": "SINGLE_SELECT", "name": name,
                   "singleSelectOptions": opts}},
    )
    return d["createProjectV2Field"]["projectV2Field"]


def ensure_text(project: dict, name: str, apply: bool) -> dict:
    fields = field_map(project)
    if name in fields:
        print(f"= 字段 {name} 已存在")
        return fields[name]
    print(f"+ 创建文本字段 {name}")
    if not apply:
        return {"id": "DRY-" + name, "name": name}
    d = gql(
        """mutation($input:CreateProjectV2FieldInput!){createProjectV2Field(input:$input){
             projectV2Field{ ... on ProjectV2FieldCommon{ id name } } }}""",
        {"input": {"projectId": project["id"], "dataType": "TEXT", "name": name}},
    )
    return d["createProjectV2Field"]["projectV2Field"]


VIEWS = [
    # (名称, 布局, 过滤器或空, 说明)
    ("总览", "TABLE_LAYOUT", "", ""),
    ("按分类", "BOARD_LAYOUT", "", "看板列=Status；分类分组在 UI 里设 Column by=Category"),
    ("按列车", "TABLE_LAYOUT", "train:*", "发版列车号（发布流程回填）"),
    ("按仓", "TABLE_LAYOUT", "repository:*", "按适配仓/组件仓切（内置 Repository 字段）"),
    ("待确认", "TABLE_LAYOUT", 'triage:"待确认问题"', ""),
    ("未来提案", "TABLE_LAYOUT", 'triage:"未来功能提案"', ""),
]


def ensure_views(project: dict, apply: bool) -> None:
    if not apply:
        for name, layout, filt, note in VIEWS:
            print(f"+ 创建视图 {name}（{layout}）{('· ' + note) if note else ''}")
        return
    q = """query($id:ID!){node(id:$id){ ... on ProjectV2{ views(first:50){ nodes{ id name filter } } } }}"""
    d = gql(q, {"id": project["id"]})
    have = {v["name"]: v for v in d["node"]["views"]["nodes"]}
    for name, layout, filt, note in VIEWS:
        if name in have:
            v = have[name]
            want = filt
            if (v.get("filter") or "") != want:
                print(f"~ 视图 {name} 过滤器: {v.get('filter')!r} → {want!r}")
                if apply:
                    gql(
                        """mutation($input:UpdateProjectV2ViewInput!){updateProjectV2View(input:$input){
                             projectV2View{ id name filter } }}""",
                        {"input": {"viewId": v["id"], "filter": want}},
                    )
            else:
                print(f"= 视图 {name} 已存在")
            continue
        print(f"+ 创建视图 {name}（{layout}）{('· ' + note) if note else ''}")
        if not apply:
            continue
        d2 = gql(
            """mutation($input:CreateProjectV2ViewInput!){createProjectV2View(input:$input){
                 projectV2View{ id name } }}""",
            {"input": {"projectId": project["id"], "name": name, "layout": layout}},
        )
        vid = d2["createProjectV2View"]["projectV2View"]["id"]
        if filt:
            try:
                gql(
                    """mutation($input:UpdateProjectV2ViewInput!){updateProjectV2View(input:$input){
                         projectV2View{ id name filter } }}""",
                    {"input": {"viewId": vid, "filter": filt}},
                )
            except RuntimeError as e:
                print(f"  ⚠ 过滤器 {filt!r} 被拒（该视图留空过滤，UI 手设）: {e}")


def category_of(title: str, labels: list[str]) -> str:
    t = title
    # 顺序有意义：先按「标题的显式类别前缀/标签」判，再按关键词。
    if "security" in labels or "【安全" in t:
        return "Security"
    if "已修关" in t or "缺陷" in t or "正确性" in t or ("bug" in labels and "架构" not in t):
        return "Correctness"
    if any(k in t for k in ("生态", "看板", "台账", "社区")):
        return "Community"
    if any(k in t for k in ("发布", "CI", "测试", "验收", "K8s", "可靠", "演练", "供应链", "列车")):
        return "Reliability"
    if any(k in t for k in ("平台", "架构", "跨平台", "兼容", "适配")):
        return "Platform"
    if any(k in t for k in ("产品", "治理", "策略", "SDK", "Passkey", "WebAuthn")):
        return "Product"
    return "Platform"


def triage_of(title: str, labels: list[str]) -> str:
    if any(k in title for k in ("展望", "需拍板")):
        return "未来功能提案"
    if "bug" in labels or "缺陷" in title:
        return "已验证缺陷"
    return "待确认问题"


def open_issues() -> list[dict]:
    out, page = [], 1
    while True:
        d = rest(f"search/issues?q=org:{ORG}+is:issue+is:open&per_page=100&page={page}")
        items = d.get("items", [])
        out.extend(items)
        if len(items) < 100:
            return out
        page += 1


def sync_items(project: dict, fields: dict[str, dict], apply: bool) -> None:
    issues = open_issues()
    print(f"· org open issue {len(issues)} 条")
    if not apply:
        for iss in issues:
            labels = [l["name"] for l in iss.get("labels") or []]
            repo = iss["repository_url"].rsplit("/", 1)[-1]
            print(f"  add: {repo}#{iss['number']} → {category_of(iss['title'], labels)} / {triage_of(iss['title'], labels)}")
        return
    # 现有 item ↔ content 映射。
    q = """query($id:ID!){node(id:$id){ ... on ProjectV2{ items(first:100){
             nodes{ id content{ __typename ... on Issue{ id number title } } } } } }}"""
    d = gql(q, {"id": project["id"]})
    existing = {}
    for it in d["node"]["items"]["nodes"]:
        c = it.get("content") or {}
        if c.get("__typename") == "Issue":
            existing[c["id"]] = it["id"]

    cat_field = fields.get("Category") or {}
    tri_field = fields.get("Triage") or {}
    cat_opts = {o["name"]: o["id"] for o in (cat_field.get("options") or [])}
    tri_opts = {o["name"]: o["id"] for o in (tri_field.get("options") or [])}

    def set_single(item_id: str, field: dict, option_id: str) -> None:
        gql(
            """mutation($input:UpdateProjectV2ItemFieldValueInput!){
                 updateProjectV2ItemFieldValue(input:$input){ projectV2Item{ id } }}""",
            {"input": {"projectId": project["id"], "itemId": item_id,
                       "fieldId": field["id"], "value": {"singleSelectOptionId": option_id}}},
        )

    def set_text(item_id: str, field: dict, text: str) -> None:
        gql(
            """mutation($input:UpdateProjectV2ItemFieldValueInput!){
                 updateProjectV2ItemFieldValue(input:$input){ projectV2Item{ id } }}""",
            {"input": {"projectId": project["id"], "itemId": item_id,
                       "fieldId": field["id"], "value": {"text": text}}},
        )

    added = updated = 0
    for iss in issues:
        labels = [l["name"] for l in iss.get("labels") or []]
        cat = category_of(iss["title"], labels)
        tri = triage_of(iss["title"], labels)
        repo = iss["repository_url"].rsplit("/", 1)[-1]
        node_id = iss["node_id"]
        action = "update" if node_id in existing else "add"
        print(f"  {action}: {repo}#{iss['number']} → {cat} / {tri}")
        if not apply:
            continue
        item_id = existing.get(node_id)
        if item_id is None:
            d2 = gql(
                """mutation($input:AddProjectV2ItemByIdInput!){addProjectV2ItemById(input:$input){
                     item{ id } }}""",
                {"input": {"projectId": project["id"], "contentId": node_id}},
            )
            item_id = d2["addProjectV2ItemById"]["item"]["id"]
            added += 1
        else:
            updated += 1
        if cat in cat_opts:
            set_single(item_id, cat_field, cat_opts[cat])
        if tri in tri_opts:
            set_single(item_id, tri_field, tri_opts[tri])
    print(f"· 入板完成：新增 {added} / 更新 {updated}")


def main() -> None:
    ap = argparse.ArgumentParser(description="pigeonbox 公开质量看板同步（#366）")
    ap.add_argument("--apply", action="store_true", help="真正落地（缺省 dry-run）")
    args = ap.parse_args()
    apply = args.apply
    print(f"== {ORG} / {PROJECT_TITLE} {'（apply）' if apply else '（dry-run）'}")
    project = ensure_project(apply)
    if apply and not project.get("fields", {}).get("nodes"):
        project = find_project() or project
    fields = field_map(project) if apply else {}
    for name, opts in (("Category", CATEGORIES), ("Triage", TRIAGE)):
        f = ensure_single_select(project, name, opts, apply)
        if apply:
            fields[name] = f
    for name in ("Train",):
        f = ensure_text(project, name, apply)
        if apply:
            fields[name] = f
    if apply:
        project = find_project() or project
        fields = field_map(project)
    ensure_views(project, apply)
    sync_items(project, fields, apply)
    if apply:
        print(f"→ 看板: {project['url']}")
    else:
        print("（dry-run 结束；加 --apply 落地）")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)