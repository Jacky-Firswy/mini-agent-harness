# 五层架构规则速查

> 写代码前扫一眼。全部取自 `agent-core/src/ARCHITECTURE.md` 原文。

## 层表

| 层 | 路径 | 放什么 |
|---|---|---|
| 3 | `state/` | Tauri 状态、命令处理器 |
| 2b | `integrations/` | 外部 I/O：渠道、网关、自动化 |
| 2a | `intelligence/` | 记忆、技能、MCP、钩子、策略 |
| 1 | `core/` | provider、会话、工具、回合执行器 |
| 0 | `foundation/` | 数据库、总线、安全、文件 I/O |

## 四条硬规矩

### 1. 顶层只出不进

> `state` / `integrations` may import anything below them; **nothing may import them**.

`state` 和 `integrations` 可以 import 下面任何东西，**但下面的东西绝不能 import 它们**。

### 2. 底层只进不出

> `foundation` may import **nothing else** inside `agent_core`; everything else may import it.

### 3. `core ↔ intelligence` 故意双向

> `intelligence` is a _capability layer_ injected into the turn loop, not an outer orchestrator.

让它双向，但**两个方向都要窄**：

- `core → intelligence`：只调构造函数和运行时入口（`SkillsLoader::new`、`HookExecutor::load`、`MemoryManager::record`）
- `intelligence → core`：只依赖稳定身份/枚举（`SessionId`、`AgentExecMode`、`MessageRole`），**绝不碰会话内部**

### 4. 不许用"共享类型 crate"解环

> Don't try to break the cycle by adding a new "shared types" crate.

## 三条禁令

```text
❌ Never push downward into foundation/ to escape a missing dep — refactor instead.
❌ Never compare spec.name == "anthropic"; always == provider_id::ANTHROPIC.
❌ Don't break the core↔intelligence cycle with a "shared types" crate.
```

## 新模块该放哪

问一句：**谁 import 我？**

| 情况 | 放哪 |
|---|---|
| 只有 TS 通过 Tauri 调用 | `state/` |
| 为任何 Agent 代理外部 I/O | `integrations/` |
| 实现回合循环里用的可插拔能力 | `intelligence/` |
| 属于核心引擎 | `core/` |
| 基础设施（谁都能用） | `foundation/`（谨慎！） |

## 加一个新工具

三步（原文）：

1. 在 `tools/impls/<area>/<name>.rs` 实现 `Tool`
2. 在该分区的 `mod.rs` 注册
3. 如果不是 always-on，加一条 policy 条目

**`Tool` trait 的唯一事实来源是 `tools/traits.rs`。**

## 代码规范（散见于文档）

| 规矩 | 出处 |
|---|---|
| `#[allow(dead_code)]` 只允许两种情况，其余删除 | 文档 |
| 前端单文件 **700 行**上限，CI 检查改动文件 | 文档 |
| 大文件必须拆（`run_session` 1780 行被拆） | 提交史 |
| 策略常量单独成文件（便于审阅） | `backoff.rs` 注释 |
| 工具名、provider 名必须用常量 | `names.rs`、`provider_id` |

## 最重要的那句话

> Goal: **a new engineer can ship a non-trivial change in their first day.**
> If something here is wrong or missing, **fix it in the same PR as your code change.**

翻译：**目标是新工程师第一天就能提交一个不平凡的改动。**

而且：**如果这份文档有错或缺失，在你改代码的同一个 PR 里把它改掉。**

**这条规矩本身比任何一条架构规则都值得学。** 它把"文档维护"变成了代码提交的一部分，而不是一件"以后有空再做"的事。

---

!!! quote "📝 我的批注 · 2026-11-06 · v0.1"
    留白。
