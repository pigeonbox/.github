# PigeonBox 质量看板（维护约定）

> 看板：<https://github.com/orgs/pigeonbox/projects/1>（公开，Projects v2）
> 同步脚本：[`scripts/sync-board.py`](../scripts/sync-board.py)（幂等，可重复跑）
> 来源 issue：pigeonbox/pigeonbox#366（2026-11-14 生态技术评审 §九）

## 这张板回答什么

单仓 issue 数量不代表产品质量。看板提供**跨仓统一视图**，回答三个问题：

1. **跨仓阻塞关系**：一个修复要动几个仓、卡在哪个 PR —— 按「仓」视图 + 内置
   Linked pull requests 字段看；
2. **已发布版本的缺陷数量**：按列车号归档 —— 「按列车」视图（Train 字段）；
3. **真机验证覆盖率**：哪些平台/版本真机过、哪些还悬着 —— 平台条目的
   Triage 状态 + hub#240 生态债清单（双向链接，看板是活视图，清单是总览）。

## 字段

| 字段 | 类型 | 取值 | 说明 |
|---|---|---|---|
| Category | 单选 | Security / Correctness / Reliability / Platform / Product / Community | 六分类（issue 明确要求） |
| Triage | 单选 | 已验证缺陷 / 待确认问题 / 未来功能提案 | 三态区分 |
| Train | 文本 | 发版列车号（如 `5.8.0`） | **发布流程回填**；按列车视图用它切 |
| Status | 内置单选 | Todo / In Progress / Done | 默认 Todo |
| Repository | 内置 | 自动 | 入板 issue 自带，按仓视图用它切 |

## 视图

| 视图 | 布局 | 过滤器 | 说明 |
|---|---|---|---|
| 总览 | 表格 | — | 全量 |
| 按分类 | 看板 | — | **看板列=Status；分类分组需在 UI 设 Column by=Category**（Projects API 的 `UpdateProjectV2ViewInput` 没有 groupBy 字段，脚本只能声明期望，漂移靠人看） |
| 按列车 | 表格 | `train:*` | 填了列车号才出现 |
| 按仓 | 表格 | `repository:*` | 按适配仓/组件仓切 |
| 待确认 | 表格 | `triage:"待确认问题"` | |
| 未来提案 | 表格 | `triage:"未来功能提案"` | |

## 维护约定

- **谁负责归档**：发布 owner（每趟列车收车时）——
  1. 新开 issue 入板：`python3 scripts/sync-board.py --apply`（脚本按标题/标签自动打
     Category/Triage，未知形态默认 Platform/待确认问题，人工在看板上纠偏）；
  2. 涉及平台的条目回填 Train 字段（本轮列车号）；
  3. 真机验过的条目把 Triage 从「待确认问题」改成「已验证缺陷/已验证」并附证据链接。
- **每周巡检**（可并入现有 issue 清零轮）：跑一次脚本（幂等），看「待确认」视图里
  是否有超过 7 天未分类的条目。
- **关闭的 issue**：Projects v2 会自动把 item 置 Done 态（Status 内置字段），
  脚本只同步 open issue，不重复拉回。
- **hub#240 生态债**：清单继续做文本总览；看板是它的**活视图**。新验收结果优先写
  看板/对应 issue，两边不各维护一份（清单每季度与看板对账一次）。

## 手工初始化/修复

```bash
# 需要 gh 已登录且 token 有 project 权限（read:project + project）
python3 scripts/sync-board.py            # dry-run：打印将建的项目/字段/视图与入板清单
python3 scripts/sync-board.py --apply    # 落地（幂等：复用已有项目/字段/视图）
```

脚本的设计取舍：

- **项目名固定**「PigeonBox 质量看板」，按名复用——改名视为新建（防止误改既有板）；
- **字段/视图按名判存在**，缺则补、有则跳过（视图过滤器漂移会被改回固定值）；
- **Category/Triage 映射是启发式**（标题前缀 + label），映射表在 `category_of()` /
  `triage_of()`，人工纠偏比改脚本更常见——脚本只在入板时打标，不回写 issue。