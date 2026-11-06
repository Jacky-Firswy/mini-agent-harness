# 会话与状态

## 会话不只是聊天记录

这是本章最重要的一句话。

`AgentSession` 持有**一个对话运转所需的全部状态**：

| 状态 | 为什么必须在这里 |
|---|---|
| 消息历史 | 要发给模型 |
| 模型选择 | 不同会话可能用不同模型 |
| scratchpad 目录 | 中间产物放哪 |
| **取消标志** | 用户点"停止"时循环要能感知 |
| 事件总线钩子 | 往界面推流式事件 |
| 文件注册表 | 这个会话碰过哪些文件 |
| 工作目录 | 工具的相对路径以谁为基准 |

**对比你的 `harness/session.py`**：只有消息列表和 JSONL 事件日志。这不怪你 —— 你的 harness 没有界面、没有多端、没有文件变更追踪，就不需要这些。

## 18 个子模块

`ARCHITECTURE.md` 第 3.1 节列出的完整清单。按"负责哪一类状态"重排：

### 对话本体

| 子模块 | 职责 |
|---|---|
| `turn/` | 一轮 `用户 → 工具 → 助手`，回合的心脏 |
| `types/` | `SessionStatus`、`SessionCategory`、`AgentExecMode` |
| `exec_modes.rs` | 执行模式的策略层 + 系统提示词后缀 |

### 上下文管理

| 子模块 | 职责 |
|---|---|
| `compaction/` | 上下文窗口收缩（模型摘要 + 会话记忆） |
| `prompt/` | 系统提示词组装（soul + context + learnings） |
| `model_context/`（在 core 层） | 上下文窗口、裁剪 |

**`compaction/` 是你现在最缺的那块。** 你的 README 承认"聊得很长会撞上限然后报错"，对应的就是这里。

它做两件事：

1. **模型摘要** —— 让模型把旧对话总结成一段
2. **会话记忆** —— 把重要事实存进记忆系统（见 [记忆系统](../intelligence/memory.md)）

### 持久化与恢复

| 子模块 | 职责 |
|---|---|
| `persistence/` | `agent_sessions` 表和消息行的 SQLite 增删改查 |
| `recovery.rs` | 应用启动时从磁盘重新水合会话 |
| `session_id.rs` | ID 生成 + 版本后缀 |

**`recovery.rs` 的存在说明一件事：应用会崩。**

不是"可能会崩"，是"一定会崩"。所以每次启动都要能从中断处恢复。

### 工作区与文件

| 子模块 | 职责 |
|---|---|
| `workspace.rs` | 为工具调用解析"当前活跃仓库"路径 |
| `file_registry.rs` | 追踪 Agent 读过 / 改过哪些文件 |

**`workspace.rs`** 解决的问题：工具有相对路径（`src/main.rs`），相对谁？

如果 Agent 同时开着三个项目，这个答案必须是"当前会话绑定的那个"。否则工具会写错仓库 —— **这是会造成真实破坏的错误。**

### 交互形态

| 子模块 | 职责 |
|---|---|
| `plan_mode/` | 计划模式的待定计划文件管理 |
| `wingman/` | 浮动"副驾"伴随窗口的状态 |
| `launch.rs` | Tauri 创建命令用的一次性会话启动器 |
| `overrides.rs` | 来自 `SessionCreator` 的每会话配置覆盖 |
| `story_init.rs` | 首次运行的项目初始化钩子 |
| `scheduler.rs` | 按 cron 风格的会话侧触发器 |
| `gateway_pipeline.rs` | 交接给消息网关 |

**`plan_mode/` 值得单独说。** 计划模式的产物是"一份待确认的计划文件" —— 它不是对话消息，是一件**有独立生命周期的事物**（生成 → 等待确认 → 执行或丢弃）。所以需要自己的文件管理。

**`scheduler.rs`** 说明会话能自己"醒来"。这跟 [自动化触发](../integrations/automation.md) 是两套机制：一个是会话内部的定时，一个是外部的规则触发。

## 生命周期

`ARCHITECTURE.md` 原话：

> Lifecycle: created by `session::launch::*`, persisted to `agent_sessions` table via `core::session::persistence::crud`, dropped when the user closes the tab (background sessions outlive their tab via `state::session_runtime`).

拆开：

```text
创建  ← session::launch::*
  ↓
运行  ← 内存中的 AgentSession
  ↓  持续写入 agent_sessions 表
关闭标签页 → 对象被丢弃
  ↓
（但后台会话能活得更久，靠 state::session_runtime）
```

**"background sessions outlive their tab"** 这句话很重要 —— 用户关掉窗口，任务继续跑。这需要一个进程级的持有者，就是 [一条消息的旅程](message-journey.md) 第 ② 步的 `SessionRuntime`。

## 一个模式：同一事实，多个时间尺度

会话相关的东西里，有三套"文件记录"：

| 模块 | 时间尺度 |
|---|---|
| `turn_executor/file_tracker.rs` | 一个回合 |
| `core/session/file_registry.rs` | 一个会话 |
| `tools/file_history/` | 长期（跨会话） |

**为什么不合并成一个？**

因为它们回答不同问题：

- "这一轮改了什么" → 用于生成本轮摘要
- "这个会话总共碰了哪些文件" → 用于会话结束时的改动概览
- "这个文件历史上长什么样" → 用于回滚

**合并成一个必然要加参数区分，那就等于没合并。**

---

!!! quote "📝 我的批注 · 2026-11-06 · v0.1"
    留白。
