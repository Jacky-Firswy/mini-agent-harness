# 工具系统

## 工具是 Agent 唯一能"动手"的地方

模型自己什么都做不了。它只能输出文字。

**它想让世界发生变化，唯一的方式是说"请帮我执行这个工具"。**

所以工具系统的设计质量，直接决定了 Agent 的能力边界和安全性。

`core/tools/` 目录有 18 个顶层文件 + 3 个子目录，约 100KB 源码。这不是因为它复杂，而是因为**"让模型安全地动手"本身就是很难的事**。

## 目录全景

| 文件 / 目录 | 大小 | 职责 |
|---|---|---|
| `traits.rs` | 12,842 B | `Tool` trait —— **单一事实来源** |
| `registry.rs` | 16,890 B | 工具注册表 |
| `defaults.rs` | 14,143 B | 默认工具集 |
| `policy.rs` | 11,489 B | `ResolvedToolPolicy`（白名单 / 黑名单 / 审批门） |
| `ui_metadata.rs` | 9,675 B | 工具在界面上怎么显示 |
| `types.rs`（builtin） | 6,745 B | 内置工具的类型 |
| `result.rs` | 5,958 B | 工具结果的统一格式 |
| `metadata.rs` | 5,552 B | 工具的元数据 |
| `params.rs` | 5,514 B | 参数校验 |
| `categories.rs` | 4,206 B | 工具分类 |
| `interactive.rs` | 3,051 B | 需要用户交互的工具 |
| `error.rs` | 946 B | 错误类型 |
| `names.rs` | 473 B | 工具名常量 |
| `builtin_tools/` | — | 内置工具（含 `projection.rs`、`table/`） |
| `file_history/` | — | 文件变更历史 |
| `registration/` | — | 注册流程 |
| `impls/` | — | **十一个能力分区的具体实现** |

## 核心抽象：`Tool` trait

`ARCHITECTURE.md` 原话：

> Adding a new tool: implement `Tool` in `tools/impls/<area>/<name>.rs`, register it in the area's `mod.rs`, add a policy entry if it's not always-on. The single source of truth for the trait is `tools/traits.rs`.

翻译成三步：

1. 在 `tools/impls/<分区>/<名字>.rs` 实现 `Tool`
2. 在该分区的 `mod.rs` 里注册
3. 如果不是"永远允许"的工具，加一条策略条目

**注意"single source of truth for the trait"这句话** —— 又是那个词。这里的意思是：`Tool` 这个 trait 只在一个地方定义，不许别处再定义个长得像的。

`Tool` trait 至少要提供这些信息（从多个文件的存在反推）：

| 需要什么 | 谁在用 |
|---|---|
| 名字 | `names.rs`、registry |
| 描述（给模型看） | 模型决定要不要调它 |
| 参数 schema（JSON Schema） | 模型填参数、`params.rs` 校验 |
| 执行逻辑 | 实际干活 |
| 分类 | `categories.rs` |
| UI 元数据 | `ui_metadata.rs` |
| 是否交互式 | `interactive.rs` |

### "给模型看的说明" 和 "给人看的说明" 必须分开

这是 `ui_metadata.rs`（9,675 字节）存在的理由。

同一个工具需要两套描述：

| 面向 | 目的 | 风格要求 |
|---|---|---|
| **模型** | 让它判断"我该不该用这个" | 精确、简洁、说清边界 |
| **人** | 让用户知道"它刚才干了什么" | 友好、可读、带细节 |

**为什么不能共用一套？**

因为优化目标相反：

- 给模型的描述**要短**，因为每个工具的描述都会占上下文窗口。10 个工具 × 500 字 = 5000 字，还没开始干活就花了。
- 给人的描述**要详细**，因为用户要知道"它到底改了哪一行"。

如果共用，要么模型被冗余信息干扰，要么用户看到一堆生硬的机器语言。

## 十一个能力分区

`impls/` 下分了十一个目录。这个分类方式本身就是一份"能力清单"：

| 分区 | 大概管什么 |
|---|---|
| `coding` | 读写文件、搜索、执行命令 |
| `web` | 联网抓取、搜索 |
| `desktop` | 操作桌面（截图、点击） |
| `database` | 查数据库 |
| `comms` | 发消息（Slack / Telegram 等） |
| `orchestration` | **编排其他 Agent** |
| `agent_def` | 定义 / 管理 Agent |
| `plan_mode` | 计划模式 |
| `project` | 项目管理 |
| `nodes` | 节点（分布式执行） |
| `meta` | 元操作（查工具、查自己） |

**这个分区不是按技术分的，是按"能力域"分的。** 好处是一个新工具的位置不用犹豫 —— 问一句"它是哪一类能力"就定了。

### 最特殊的那个：`orchestration::agent`

`ARCHITECTURE.md` 专门为它写了一句：

> The "subagent" tool (`tools::impls::orchestration::agent`) is special — it boots a child `AgentSession` from inside a parent's tool call. See its module docs before changing it.

翻译：**"子 Agent"工具很特殊 —— 它会在父 Agent 的一次工具调用里，启动一个子 `AgentSession`。改它之前先看它的模块文档。**

**这是整个工具系统里最危险的一块。**

为什么？因为在工具执行内部启动一个新的 Agent 会话，意味着：

- 递归。子 Agent 也可能调工具，也可能再开子 Agent
- 状态叠加。父和子的取消、权限、超时怎么算
- 死锁风险。父子互相等待

**"See its module docs before changing it"** 这句警告，等价于在说"这块代码有你看不见的坑"。

## 策略：`ResolvedToolPolicy`

`policy.rs` 有 11,489 字节，是工具系统里第二大的文件。它管三件事：

| 机制 | 作用 |
|---|---|
| **白名单**（allowlist） | 只允许这些 |
| **黑名单**（denylist） | 禁止这些 |
| **审批门**（approval gates） | 这些需要用户点确认 |

**"Resolved"（已解析）这个词很关键。** 它说明策略是**多层叠加后算出来的结果**，不是单一配置。

想想有哪些层：

- 全局默认（`defaults.rs`）
- 单个会话的覆盖（`overrides.rs`）
- 执行模式（`exec_modes.rs`）—— 比如"计划模式"下不许写文件
- Agent 定义自带的策略

**这些层冲突时谁赢？** 这就是 `ResolvedToolPolicy` 要解决的问题。

### 为什么"审批门"是必需品

因为**工具调用是不可回滚的**。

删了一个文件，模型说"抱歉我删错了"—— 文件不会回来。

所以高危操作必须在**执行之前**问人。这个"之前"很关键：事后检查毫无意义。

## 大结果处理：`MAX_TOOL_OUTPUT_CHARS`

这个常量放在 `backoff.rs` 里（不是工具模块里）：

```rust
pub(crate) const MAX_TOOL_OUTPUT_CHARS: usize = 100_000;
```

**10 万字符。**

超过怎么办？两个文件配合：

- `result.rs`（5,958 B）：结果统一格式
- `tool_result_storage.rs`（在 `turn_executor/` 里，5,718 B）：大结果落库，历史里只留引用

### 为什么这个设计必须存在

算一笔账：

```text
上下文窗口：200,000 token（约 60 万汉字）
一次 grep 全项目：可能 50 万字符
```

**一次工具调用就能把窗口吃光。**

而且更糟：这个结果会**留在历史里**，之后每一轮请求都会重新发送它。也就是说，你花了 10 万 token 的窗口，还每一轮都在为它付钱。

所以：

```text
工具返回 50 万字符
      ↓
超过 10 万上限
      ↓
完整内容存进数据库 / 文件
      ↓
对话历史里只放：「结果已存至 xxx，前 200 行如下…」
      ↓
模型的窗口只被少量内容占用
```

**注意 `SessionEvent` 里的 `payload_refs` 字段**（见 [事件流](event-stream.md)）—— 就是这个机制在事件层的对应物。

**这是"指针"思想的经典应用**：不搬内容，搬地址。

## `file_history/`：为什么工具系统要管文件历史

这个目录放在 `tools/` 下而不是别处，说明**文件变更是工具系统的责任**。

理由很直接：**只有工具能改文件**（Agent 的所有写入都经过工具）。所以"记录文件改了什么"这个职责，天然属于工具系统。

配套的是 `core/session/file_registry.rs`（追踪 Agent 读/改过哪些文件）和 `turn_executor/file_tracker.rs`（记录本回合碰过哪些文件）。

**三个地方都在记文件，为什么？**

| 模块 | 记什么 | 生命周期 |
|---|---|---|
| `turn_executor/file_tracker.rs` | 本回合碰了哪些 | 一个回合 |
| `core/session/file_registry.rs` | 整个会话碰了哪些 | 一个会话 |
| `tools/file_history/` | 文件内容的历史版本 | 长期 |

**不同的时间尺度，不同的用途。** 这个"同一事实在多个时间尺度上各有视图"的模式，在 ORG2 里反复出现。

## 工具名的常量管理

`names.rs` 只有 473 字节 —— 小到容易被跳过，但它很重要。

它存的是工具名的**常量**。

**为什么不能直接写字符串？**

因为工具名在至少四个地方出现：
- 注册表
- 策略配置
- 模型返回的调用请求（字符串匹配）
- 日志 / 界面

**任何一处拼错，都不会编译报错，只会在运行时静默失败**（"找不到这个工具"）。

所以统一成常量。这和 Provider 层那条"永远不要 `spec.name == "anthropic"`"是同一条纪律 —— 见 [Provider 层](providers.md)。

`error.rs` 只有 946 字节，也是同一个思路：**错误类型集中定义，方便穷举匹配**。

## 参数校验：`params.rs`

模型返回的工具参数是**一个 JSON 字符串**，而且**不保证合法**。

可能的情况：

- JSON 语法错误（少括号、多逗号）
- 字段缺失
- 类型错误（要求整数，给了字符串）
- 路径不合法

`params.rs`（5,514 B）在**执行之前**做校验。

**为什么必须在执行之前？** 因为工具执行可能已经产生了副作用。比如一个"写文件"的工具，参数解析到一半才发现路径为空，如果已经创建了目录吗？—— 顺序很重要。

## 和你的 harness 对照

你的 `harness/tools.py` 有 8.5KB，四个工具（读、写、列目录、跑命令）。对照一下：

| 概念 | 你的实现 | ORG2 对应 |
|---|---|---|
| 工具抽象 | `@dataclass Tool` | `Tool` trait（`traits.rs`） |
| schema 生成 | `Tool.schema()` | `traits.rs` + `params.rs` |
| 注册表 | `ToolRegistry` | `registry.rs` |
| 执行入口 | `execute(name, raw_args)` | `registry.rs` + `policy.rs` |
| 参数解析失败 | `try/except json.JSONDecodeError` | `params.rs` |
| 沙箱 | `_sandbox()` + `is_relative_to` | `foundation/security/` |
| 输出截断 | `_truncate(text, 8000)` | `MAX_TOOL_OUTPUT_CHARS = 100_000` |
| **权限策略** | ❌ **无** | ✅ 白名单/黑名单/审批门 |
| **UI 元数据** | ❌ 无 | ✅ `ui_metadata.rs` |
| **分类** | ❌ 无 | ✅ 十一分区 |
| **文件历史** | ❌ 无 | ✅ `file_history/` |

### 你的一个很好的决定

你的 `ToolRegistry.execute()` **永远返回字符串，从不抛异常**。

这个设计看起来保守，实际上非常对 —— 因为它保证了**工具失败不会打断 Agent 循环**。模型会收到一条"执行失败：xxx"的结果，然后自己决定怎么办。

**ORG2 的做法本质上一样**：`result.rs` 把工具结果统一成一种格式，成功失败都走同一条路。

### 你该补的第一件事

**权限策略**。哪怕只是最简单的：

```python
DANGEROUS_TOOLS = {"run_shell", "write_file"}

if tool.name in DANGEROUS_TOOLS:
    print(f"即将执行：{tool.name}，参数：{args}")
    if input("允许？(y/n) ").lower() != "y":
        return "用户拒绝了这次操作。"
```

**二十行代码，但它是"玩具"和"能给别人用"的分界线。**

---

## 本章要点

1. 工具是 Agent 唯一的"动手"通道
2. 加工具三步：实现 trait → 注册 → 加策略
3. **给模型的说明要短，给人的说明要详细** —— 优化目标相反，必须分开
4. 十一分区按"能力域"分，不按技术分
5. `orchestration::agent` 最危险 —— 它在工具调用里启动子 Agent
6. `ResolvedToolPolicy` 是多层策略叠加的结果；审批门是必需品，因为工具不可回滚
7. 10 万字符上限 + 大结果转存 = 用指针代替内容
8. 工具名必须用常量，字符串字面量会静默失败
9. 参数校验必须在执行之前，因为执行有副作用
10. 你的 `execute()` 永不抛异常是个好设计，值得保留

<p class="src-path">源码：src-tauri/crates/agent-core/src/core/tools/ 全目录；ARCHITECTURE.md 第 3.3 节</p>

---

!!! quote "📝 我的批注 · 2026-11-06 · v0.1"
    留白。
