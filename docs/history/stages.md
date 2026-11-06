# 五个阶段

## 先纠正一个常见误解

很多人以为 ORG2 是"从零写起来的"。

**不是。**

第一个提交是：

```text
chore(repo): initial commit          2026-06-01  Harry He
Seed the repository with the initial ORGII codebase, including the
Tauri/Rust backend, frontend modules, e2e harness, blackboard PoC,
and baseline tooling configuration.
```

**一条提交，导入约 130 万行代码。**

而且初始提交里就已经有：

- 一份 18,759 字节的 `ARCHITECTURE.md`（五层架构、单向依赖、`provider_id` 规范全都在）
- 43 个 Rust crate
- 完整的 IDE 前端
- 四种 provider 驱动
- 记忆五子系统、MCP 桥、五个聊天渠道

**所以真实的建造史不是"如何从零写一个 Agent"，而是"一个已有的代码库，如何用 4.5 个月、7,273 次提交，被重做成另一个产品"。**

这反而更值得学 —— 绝大多数真实项目都是这样长出来的。

## 五阶段总览

| 阶段 | 时间 | 在解决什么 |
|---|---|---|
| ① 种子 | 06-01 | 把既有 ORGII 代码库搬进来 |
| ② 能装 | 06-01 → 06-20 | 从"能跑"到"别人能装上" |
| ③ 补内核 | 06-20 → 07-12 | Agent 能力对齐 + 性能 |
| ④ 平台化 | 07-12 → 08-25 | 从 IDE 变成"记录系统" |
| ⑤ 收口 | 08-25 → 10-11 | v2.0 发布 + 稳定性 |

## 阶段②：分发是道坎

转折点很清晰：06-11 起突然密集的 CI 提交。

```text
ci: add Windows x64 build + Azure Trusted Signing job
fix: re-sign sidecar binaries inside .app bundle to pass notarization
```

**为什么这个顺序值得记住？**

因为签名和公证是**分发**的门槛，不是功能门槛。

在 06-11 之前，它只是"开发者自己机器上能跑的 demo"。之后，才是"别人能下载安装的产品"。

> **先让代码跑通，再让产品装得上，中间隔着的是工程苦活。**

## 阶段③：一天修四次同一个问题

06-06 一天之内连着四条：

```text
fix(chat): harden streaming cancellation and read paths
make live streaming cancellation durable
coalesce live stream writes on cancel
stop restore-driven session patch loops
```

**一天修四次同一个问题。**

原因不难推：流式输出的每一块要同时写进数据库、更新界面状态、还要支持中途取消，三个地方各写一份，就一定会对不上。

**这个坑一直痛到 10 月** —— v2.0.10 里还有 `fix(session-continuation): recover image history and settled turns (#2168)`。

**这正是 [事件流](../core/event-stream.md) 那一章 `StreamingBuffer` 存在的理由** —— 把"多个副本"变成"单一真相"。

## 阶段④：改一行 README 比加十个功能重要

07-12 到 07-19 短短一周：

```text
feat(kanban): add Data Sources tab with unified external CLI detection
feat(orgtrack): FTS5 content search + cross-machine project identity
feat(orgtrack): usage/behavior triggers + check command
feat(orgtrack): exec hooks — act when a trigger fires
```

外部 CLI 从"手动导入的配置"变成了"可扫描、可信任、可触发的数据源"。

然后 07-25：

```text
docs(readme): reposition as system of record for agent-built software
```

**改一行 README 的定位说明，比加十个功能更能说明这个项目变了什么。**

它不再是"更快的 Cursor"，而是"Agent 造软件的记录系统"。详见 [ORG2 到底是个什么系统](../guide/what-is-org2.md)。

## 三条贯穿始终的主线

7,273 个提交看着杂乱，其实反复在打三场仗。

### 第一场：状态一致性

从 6 月的流式取消，到 8 月的 `fix(chat): keep post-abort messages through stale replays and races`，到 10 月的长历史导航。

**同一个根源：同一份事实存在多个副本**（数据库、UI state、重放日志），就必然不一致。

### 第二场：文件太大

```text
07-19  refactor(cli): decompose run_session god-function into phase modules
       （一个约 1780 行的函数拆成三段，session.rs 从 2245 行降到 1540 行）
08-23  refactor(modules): modularize seven oversized WorkStation and MainApp files
09-13  一批 refactor/modularize-*（#1705–#1723）
```

**为什么反复做？** 因为超过两千行的文件，**人和 AI 都改不动了**。

### 第三场：架构审计

`docs/` 里有一整排 `architecture-audit-2026-MM-DD` 目录。

最早那份 `2026-06-13/GLOBAL.md` 的结论是：

> 问题是一类一类出现的**模式**，不是一次性的 bug

具体发现：

- UTF-8 截断被重写了 10 次以上，有一处会 panic
- 模型能力检测散落在 6 个地方
- 文档声称有守卫测试，"that test does not exist"

**审计的关注点也在漂移**：

| 时间 | 关注点 |
|---|---|
| 6 月 | 整库体检（为了开源） |
| 7 月 | 前端大文件专题 |
| 9 月 | 单个功能 |

**说明项目长大后，检查从"季度体检"变成了"跟着 PR 走的防回归"。**

## 种子阶段真正"没有"的三样

这样看才不是"什么都做完了"：

| 缺什么 | 证据 |
|---|---|
| 架构审计制度 | 根目录**没有 `docs/`**。最早的 audit 是 06-10/06-13 |
| 可分发性 | `Info.plist`、`entitlements.plist`、`icons/` 在，但签名公证的 CI 是 06-11 之后 |
| 定位 | README 还叫 "self-evolving agentic development framework" |

**结论**：公开后补的是**分发 → 定位 → 稳定性**，不是内核架构。

**内核和架构，种子阶段就已经定型了。**

## 一个存疑点

`mobile-remote`、`mobile-pwa`、`orgii-mobile-relay`、`orgii-protocol` 在种子提交里就有目录。

但我看到 release notes 把"扫码配对手机"当成 v2.0.2（09-14）的新能力。

**目录存在 ≠ 功能可用。** 我没读这几个 crate 的内容，不知道当时是空壳、半成品、还是已能用。

!!! warning "⚙️ 这是存疑，不是结论"
    "更像是一次重做或补齐，而不是从零开始" —— 这是我的推断，没有证据确认。

## 许可证提醒

ORG2 是 **AGPL-3.0**。你的 `mini-agent-harness` 是 **MIT**。

这两者不冲突（你没抄它代码）。

**但如果你以后想直接复制 ORG2 的某段实现**，AGPL 的传染性会要求你也开源（而且如果做成网络服务，必须提供源码）。

**在抄之前想清楚。**

## 数据来源

- 提交信息、日期、PR 号：GitHub API 和 commits 页面
- `YORG-AI/ORGII → org2AI/ORG2` 重定向：实际访问确认
- 版本节奏：releases 页（v2.0.0 于 09-14、v2.0.10 于 10-09）
- 架构原则和审计结论：直接引用文档原文

**局限**：7,273 个提交里我实际采样了约 400~600 条（按时间窗切片 + 抽样），**不是全量**。"哪个阶段做了什么"是可靠的，"某天具体改了什么"是抽样而非穷举。阶段划分和因果解释是**推断**。

---

!!! quote "📝 我的批注 · 2026-11-06 · v0.1"
    留白。
