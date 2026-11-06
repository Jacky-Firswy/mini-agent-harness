# Agent 内核

## 先说结论

**"内核"是一个没有界面的循环体。** 它只做四件事：

1. 把对话历史发到一个模型 API
2. 看模型是否要求调用工具
3. 如果要求，执行工具，把结果追加进历史
4. 回到第 1 步，直到模型不再要求工具

就这样。整个 `agent-core` 包（几十万行）都是在这个循环上加肉。

## 为什么必须"没有界面"

这是第一个设计理念，值得停下来想清楚。

假设内核直接操作界面：它知道有一个叫"发送按钮"的东西，知道消息要显示在一个叫"气泡"的组件里。会发生什么？

**第一，你没法从别的入口叫它。** 如果消息是从 Telegram 来的，没有"气泡组件"，内核就废了。

**第二，你没法测试它。** 测试需要启动整个界面。

**第三，也是最重要的：你会开始相信界面里的状态是真实的。** 而界面的状态是易失的 —— 用户切个标签页、刷新一下、断个网，就没了。

所以 ORG2 的做法是：**内核只认数据，不认像素。**

内核这边的原话（`ARCHITECTURE.md` 第 1 节）：

> `agent_core` is the headless brain of an AI coding agent. It runs inside the Tauri Rust process, has no UI of its own, and exposes everything to the frontend via Tauri commands in `state/commands/`.

翻译：`agent_core` 是一个 AI 编程 Agent 的**无头大脑**。它跑在 Tauri 的 Rust 进程里，自身没有界面，所有能力通过 `state/commands/` 里的 Tauri 命令暴露给前端。

!!! success "🆕 版本补充 · v0.2 · 2026-11-07 · 把上面三条理由串起来"
    上面三条只有论断，没有展开。这里补一个统一的视角。

    ### 不是"专注"，是"没有那条依赖边"

    最容易犯的误读是把这件事理解成：「内核**知道**界面的存在，只是**选择不去理会**它」。

    如果真是这样，那内核里写一句 `if (界面有焦点) { ... }` 就该是允许的，只要"别太依赖"就行。

    **事实恰恰相反。** 那一行代码永远写不进去 —— Rust 里跨 crate 使用必须先声明依赖，没声明就是编译错误。`foundation/bus/mod.rs` 的注释说得很死：

    > has no compile-time back-edge into `app`

    编译期没有一条反向依赖指向界面层。

    所以准确的说法不是"内核不去看界面"，而是：**内核不认识界面。它甚至没有能力认识。**

    "专注"这个框架骗人的地方在于 —— 程序不会分心。它没有注意力可以被干扰。真正在防的不是"分心"，而是**依赖传染**：内核一旦依赖界面，那么"所有使用内核的地方"就等于依赖了界面。

    这也正是下文「依赖方向：一条硬规矩」里那句话的意思：一个底层工具为了图方便直接去读上层状态，明天你要把它搬走，就会发现**它拖着一整条依赖链**。

    ### 三条理由其实是同一条

    它们都在说同一件事：**内核不得依赖任何消费者。**

    | 书里的理由 | 在防的"消费者" |
    |---|---|
    | ① 从别的入口叫不了它 | 消费者**种类多**：桌面、Telegram、CLI |
    | ② 没法测试它 | 消费者**可以没有人** |
    | ③ 会相信界面里的状态 | 消费者**手里的状态不可信** |

    测试本身也是一种"消费者"—— 它要驱动内核，但不显示任何东西。

    ### 三条各自的补充

    **① 比"可包装"更强：内核是可剥离的。** 源码注释提到 "any future extracted `agent-core` crate"，他们把「将来把内核整个抽成独立 crate」当成明确的设计目标。这不是弹性，是**可剥离**。

    **② 主体要反过来：不是"内核去执行测试"，是"测试去执行内核"。** 这个区别不是抠字眼 —— 之所以测试能调用内核，是因为**内核是个库，不是个应用**。如果内核自己带界面（自己是个能双击运行的程序），测试就没法把它当函数调。

    **③ 是三条里最准的：独立存在。** 书里的原话是「内核只认数据，不认像素」，以及事件流那章的「界面是最后一个环节，**而且可以缺席**」。**"可以缺席"是对"独立存在"最严格的定义** —— 不是"界面在的时候也能工作"，而是"界面不在，它照样跑完，数据照样落库"。

    ### 一句修正后的总结

    > 内核不依赖任何界面，**不是因为它忽略界面，而是因为它根本不该有指向界面的依赖边**。这样它才能被多种入口调用、能被测试直接驱动、能在界面缺席时正常工作 —— 而这三件事都不是"更专注"带来的，是"没有那条依赖边"带来的。

    ### 顺带纠正一个可能的误解

    "没有界面"**不等于**"不做界面测试"。ORG2 有三个专门做测试的 crate（`e2e-test`、`test-runner`、`test-helpers`），见 [测试与自进化](../data/testing.md)。

    准确的层级是：内核逻辑**可以脱离界面测**，E2E 再叠在上面测"用户真的看到了吗"。如果内核和界面焊死，第一层就没了，只剩又慢又脆的 E2E。

## 五层结构

`agent-core/src/ARCHITECTURE.md` 里给了一张表。我原样搬过来：

| 层 | 路径 | 放什么 |
|---|---|---|
| 3 | `state/` | Tauri 管理的状态、命令处理器（TS 能看到的 API 表面） |
| 2b | `integrations/` | 外部 I/O —— 聊天渠道、网关、自动化触发 |
| 2a | `intelligence/` | 记忆、技能、MCP、插件、钩子（可插拔的 Agent 能力） |
| 1 | `core/` | Agent 逻辑 —— provider、会话、工具、回合执行器、定义 |
| 0 | `foundation/` | 基础设施 —— 数据库、总线、安全、文件 I/O、节点控制 |

!!! note "一个小的自相矛盾"
    `lib.rs` 的模块注释里写的是 "**4-layer** hierarchy"，而 `ARCHITECTURE.md` 的表格有 **5 行**。

    为什么？因为 `lib.rs` 把 2a 和 2b 算成同一层（都叫 "Layer 2"），而 `ARCHITECTURE.md` 把它们拆成 2a / 2b 并列。

    两种说法都对，只是颗粒度不同。**记住 2a 和 2b 是并列关系**（互相不依赖），这点很重要。

### 依赖方向：一条硬规矩

`ARCHITECTURE.md` 原文：

> **Strict downward-only dependency** is enforced for two pairs:
> - `state` / `integrations` may import anything below them; nothing may import them.
> - `foundation` may import nothing else inside `agent_core`; everything else may import it.

翻译成人话：

- **最上面那层是"只出不进"**：`state` 和 `integrations` 可以 import 下面任何东西，但下面的东西**绝不能**反过来 import 它们。
- **最下面那层是"只进不出"**：`foundation` 不 import 上面任何东西，但上面谁都能 import 它。

为什么这条规矩这么重要？

**因为它是唯一能防止"面条化"的机制。** 没有这条规矩，代码会自然地长成这样：一个底层工具为了图方便，直接去读上层的一个全局状态。今天没事，明天你要把这个工具搬到别的地方用，就会发现它拖着一整条依赖链。

### 一个故意的例外：`core ↔ intelligence` 是双向的

这条非常反直觉，值得单独讲。

正常的单向依赖里，`intelligence/`（在 `core/` 上面）应该能 import `core/`，反过来不行。但 ORG2 明确写了：**这两个之间是双向的，而且是故意的。**

原文理由：

> This is intentional — `intelligence` is a _capability layer_ injected into the turn loop, not an outer orchestrator.

翻译：**`intelligence` 是一个"注入进回合循环里的能力层"，不是一个"外层的编排者"。**

这个区别很微妙，但决定了整个架构：

- 如果 intelligence 是**外层编排者**，那流程是：intelligence 决定要不要调 core。→ 单向依赖，core 不知道 intelligence 存在。
- 但实际上是：**core 的回合循环主动去加载 intelligence 的能力**。`core::session::turn::entry` 在每回合开始时构造 `SkillsLoader` 和 `HookExecutor`。

所以 core 必须能调 intelligence（`SkillsLoader::new`、`HookExecutor::load`、`MemoryManager::record`）。而 intelligence 又必须能读 `SessionId`、`AgentExecMode`、`MessageRole` 这些 core 的类型，才能知道"我现在是给哪个会话干活"。

于是就成了环。

### 关于这个环，文档给了两条禁令

这是全书我见过的最有价值的工程建议之一。原文：

> Don't try to break the cycle by adding a new "shared types" crate; instead, keep both directions narrow:
> - `core → intelligence`: only call constructors and run-time entry points
> - `intelligence → core`: only depend on stable identity / enum types, never on session internals

翻译：

**禁令一：不要想着加一个"共享类型 crate"来解这个环。**

这是所有程序员的第一反应 —— 既然 A 依赖 B、B 又依赖 A，那就把公共类型抽出来放到 C，让 A 和 B 都依赖 C。听起来很美，实际上只是把环变成了三个节点，而且那个 C 会迅速变成一个什么都往里塞的垃圾桶。

**禁令二：让两个方向都保持"窄"。**

- `core → intelligence`：只允许调**构造函数**和**运行时入口**。也就是"我给你材料，你干活"，不许窥探它的内部。
- `intelligence → core`：只允许依赖**稳定的身份类型和枚举**。也就是 `SessionId`、`AgentExecMode`、`MessageRole` 这种，**绝不允许碰会话内部结构**。

**为什么这个建议值钱**：它承认了"环有时是不可避免的"，然后给出了比"消灭环"更实际的解法 —— **限制环上每个方向的带宽**。

还有一条补充禁令：

> Never push downward into `foundation/` to escape a missing dep — refactor instead.

**永远不要为了绕过一个缺失的依赖，把东西往下塞进 `foundation/`。去重构。**

这条治的是另一种常见病：某个模块缺个东西，图省事就往最底层扔，反正底层谁都能用。结果 `foundation/` 变成了垃圾场。

## 目录实证

上面讲的是原则。下面是 `agent-core/src/` 实际有什么（初始提交，逐目录核实）。

### 顶层的零散文件

| 文件 | 大小 | 干什么 |
|---|---|---|
| `ARCHITECTURE.md` | 18,759 B | 给新工程师的地图 |
| `lib.rs` | 2,307 B | 模块声明 + 重导出 |
| `lifecycle.rs` | 27,041 B | 应用生命周期（启动/关闭/恢复） |
| `debug.rs` | 5,626 B | 对外暴露的 HTTP 调试接口 |
| `test_support.rs` | 10,422 B | 测试辅助 |

`lifecycle.rs` 有 27KB，比很多项目的整个源码都大。它管的是"应用从启动到关闭"的全过程 —— 恢复未完成的会话、注册总线、初始化数据库、关闭时优雅收尾。这些事都很枯燥，但漏一件就会出诡异 bug。

### `foundation/`（第 0 层）

```
bus/               事件总线
flow_awareness/    流程感知
nodes/             节点控制
persistence/       持久化（SQLite）
security/          安全
tool_infra/        工具基础设施
utils/             工具函数
mod.rs
db_bridge.rs          2,688 B
session_bridge.rs    13,048 B
streaming.rs         20,303 B   ← 事件流的实体，见专门章节
```

`lib.rs` 里的重导出说明这一层暴露什么：

```rust
pub use foundation::{bus, flow_awareness, nodes, persistence, security, tool_infra, utils};
```

注意 `streaming.rs` **不在**重导出列表里。它是个具体实现，不是给上层用的抽象。

### `core/`（第 1 层）

```
config/           配置
coordination/     协调（多 Agent 时用）
definitions/      Agent 定义
interaction/      与用户交互
model_context/    模型上下文（窗口、裁剪）
providers/        模型接入
session/          会话
tools/            工具
turn_executor/    回合执行器
tests/
side_query.rs     4,386 B
mod.rs              414 B
```

`core/mod.rs` 只有 414 字节 —— 它就是个纯声明文件，把九个模块列出来。**保持入口文件极简，是这个代码库的一个习惯。**

### `intelligence/`（第 2a 层）

```
external_import/   外部导入
hooks/             钩子
mcp/               Model Context Protocol
memory/            记忆
policies/          策略（自主性权限）
skills/            技能
mod.rs              289 B
```

### `integrations/`（第 2b 层）

`automation`（自动化触发）、`channels`（聊天渠道）、`gateway`（网关）。

### `state/`（第 3 层）+ 两个独立模块

`state/` 是 Tauri 命令层。另外 `lib.rs` 里还声明了两个「独立模块」：

```rust
// Standalone modules
pub mod init;
pub mod lifecycle;
pub mod orchestrator_notify;
```

`orchestrator_notify` 是"编排者通知" —— 多 Agent 场景下，子 Agent 完事了要通知编排者。它不属于任何一层，是个横切关注点。

## 一个容易忽略的设计：规范化重导出

`lib.rs` 的最后一段：

```rust
// Canonical re-exports: flatten sub-layer modules to `agent_core::` for ergonomic imports
pub use self::core::{
    config, coordination, definitions, interaction, model_context, providers, session, tools,
    turn_executor,
};
```

注释说得很直白：**把子层的模块「摊平」到 `agent_core::` 这个命名空间下，让 import 写起来舒服。**

效果是：别处可以写

```rust
use agent_core::tools::registry::ToolRegistry;
```

而不必写

```rust
use agent_core::core::tools::registry::ToolRegistry;
```

看起来是小事，但 `core::tools::` 这种双层命名实际上很别扭。这是个很小但很体现"用起来顺不顺手"的细节。

## 和你的 harness 对照

| 概念 | 你的 `mini-agent-harness` | ORG2 |
|---|---|---|
| 内核入口 | `harness/loop.py` 的 `run_turn()` | `core/turn_executor/mod.rs` 的 `execute_turn()` |
| 每回合状态 | `Session` 对象传参 | `AgentSession` 持有 |
| 工具 | `ToolRegistry` | `tools/registry.rs` + `policy.rs` |
| 模型调用 | `OpenAICompatProvider.chat()` | `providers/` 四个驱动 |
| 事件 | `Bus.publish()` 直接打印 | `StreamingBuffer` → `SessionEvent` → WebSocket |
| 配置 | `config.py` 常量 | `core/config/` |
| 持久化 | JSONL 文件 | SQLite |

**最大的一处差异**：你的 `Bus` 是"发布即打印"，而 ORG2 的事件要先**攒成完整事件**再发。这个区别看起来小，实际上是"能不能有界面"的分水岭。详见 [事件流](event-stream.md)。

---

## 本章要点

1. 内核 = 没有界面的循环体，只认数据不认像素
2. 五层：`state` / `integrations` / `intelligence` / `core` / `foundation`
3. 两条硬规矩：顶层只出不进，底层只进不出
4. `core ↔ intelligence` 故意双向，理由是 intelligence 是"注入的能力"不是"外层编排"
5. 不要加"共享类型 crate"解环；让两个方向保持窄
6. 不要往 `foundation/` 里塞东西绕过依赖；去重构
7. "没有界面"不是"忽略界面"，而是**没有指向界面的依赖边**；三条理由防的是同一个东西——内核不得依赖任何消费者（见本章 🆕 补充）

<p class="src-path">源码：src-tauri/crates/agent-core/src/lib.rs、ARCHITECTURE.md、以及各层目录树</p>

---

!!! quote "📝 我的批注 · 2026-11-06 · v0.1"
    留白。
