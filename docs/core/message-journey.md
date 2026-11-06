# 一条消息的旅程

## 为什么这一章最值得读

因为**看懂一条消息怎么走，就看懂了整个系统。**

后面所有章节 —— 工具、记忆、渠道、界面 —— 都是在给这条路径加东西。路径记住了，加东西的时候你才知道该插在哪。

## 完整链路

`ARCHITECTURE.md` 给了这张图。下面每一行都是一个真实的函数或类型。

```text
① state::commands::session::agent_send_message       ← Tauri 命令入口
     ↓
② state::session_runtime::SessionRuntime             ← 进程级注册表
     ↓
③ core::session::AgentSession                       ← 单会话状态
     ↓
④ core::session::turn::entry::process_message       ← 一次 LLM 往返
     ↓
⑤ core::turn_executor::execute_turn                 ← 驱动循环
     ↓                    ↓
⑥ core::providers::*    ⑦ core::session::turn::processor
     （模型 HTTP）           （UnifiedMessageProcessor）
                              ↓
                         ⑧ core::tools::*
                              ↓
                         ⑨ integrations / intelligence
```

九个停靠点。逐个讲。

---

## ① Tauri 命令入口

```rust
state::commands::session::agent_send_message
```

**这是前端能看到的第一个函数。**

前端（TypeScript）通过 Tauri 的 IPC 机制调用 Rust 函数。这种"能被前端调用的函数"叫 **Tauri command**，用 `#[tauri::command]` 标注。

这一步做什么：

- 接收前端传来的参数（会话 id、消息文本、附件等）
- 做一些**边界校验**（这个会话存在吗？你登录了吗？）
- 然后转交给下一层

**为什么单独有一层？**

因为**这一层是唯一需要懂"前端长什么样"的地方**。它之后的所有层，都不许知道前端的事。

这也是那两条 "downward-only" 规矩里 `state/` 那条的实际含义：`state` 可以调下面任何东西，但下面的东西一旦反过来 import `state`，就意味着内核开始依赖"有一个具体的界面存在"，那就完蛋了。

!!! note "和你 harness 的对应"
    你的 `harness/main.py` 里 `cmd_chat()` 就扮演这个角色 —— 它接收命令行输入，然后转给 `run_turn()`。

    区别是：你的入口是命令行，ORG2 的入口是 Tauri IPC。**但两者都是"边界层"，都不该写业务逻辑。**

---

## ② 进程级注册表

```rust
state::session_runtime::SessionRuntime
```

**这一步容易被跳过，但它解决了一个真问题。**

问题是什么？**同一个会话可能同时被多个地方访问。**

想象：你在桌面窗口里看着会话 A，同时你的手机通过 `mobile-remote` 也在看会话 A，同时后台一个定时任务正在给会话 A 追加消息。

如果每个入口各自 `new` 一个 `AgentSession`，那就有三份互不相干的状态 —— 桌面看到的和手机看到的不一样，定时任务写的东西其他人看不见。

**`SessionRuntime` 就是解决办法：一个进程内唯一的注册表，把 `session_id` 映射到唯一的那个 `AgentSession` 实例。**

`ARCHITECTURE.md` 里对这个角色的描述只有几个字：

> Process-wide registry

但它的存在意义很重：**它保证了"一个会话在内存里只有一个实例"。**

这和我上一轮跟你说的那条主线完全一致 —— **同一份事实只能有一个副本**。

### 顺带提一个相关设计

`ARCHITECTURE.md` 说会话的生命周期是：

> dropped when the user closes the tab (background sessions outlive their tab via `state::session_runtime`)

翻译：用户关掉标签页时，会话对象会被丢弃；**但后台会话能活得比它的标签页更久**，靠的就是这个 runtime。

这就是为什么"你关了窗口，Agent 还在跑"是可能的。

---

## ③ 单会话状态

```rust
core::session::AgentSession
```

从这里开始，进入 `core/` 层。

`AgentSession` 持有**一个对话的全部状态**。原文列举了它持有的东西：

> Owns one conversation. Holds the message history, model selection, scratchpad directory, cancel flag, and a hook into the bus for streaming events.

翻译：

| 它持有 | 用途 |
|---|---|
| 消息历史 | 要发给模型的内容 |
| 模型选择 | 这个会话用哪个模型 |
| 临时目录（scratchpad） | 中间产物放哪 |
| **取消标志** | 用户点"停止"时，循环能感知到 |
| **事件总线的钩子** | 往界面推流式事件 |

**"取消标志"这一项值得单独注意。** 一个长跑的任务怎么被中断？不是 kill 进程，而是设一个标志，让循环在每个检查点自己退出。这比我下一章讲的"回合执行器"要早得多就有这个需求。

`ARCHITECTURE.md` 还列了 `AgentSession` 的 18 个子模块。我把它们整理成下表（这是本书记得最细的一张表之一）：

| 子模块 | 放什么 |
|---|---|
| `turn/` | 一轮 `用户 → 工具 → 助手`，一个回合的核心 |
| `compaction/` | 上下文窗口收缩（模型摘要 + 会话记忆） |
| `persistence/` | `agent_sessions` 表和消息行的 SQLite 增删改查 |
| `prompt/` | 系统提示词组装（soul + context + learnings） |
| `recovery.rs` | 应用启动时从磁盘重新水合一个会话 |
| `wingman/` | 浮动"副驾"伴随窗口的状态 |
| `plan_mode/` | 计划模式的待定计划文件管理 |
| `types/` | `SessionStatus`、`SessionCategory`、`AgentExecMode` 等 |
| `exec_modes.rs` | `AgentExecMode` 的策略层 + 系统提示词后缀 |
| `file_registry.rs` | 追踪 Agent 读过 / 改过哪些文件 |
| `gateway_pipeline.rs` | 交接给消息网关 |
| `launch.rs` | Tauri 创建命令用的一次性会话启动器 |
| `overrides.rs` | 来自 SessionCreator 的每会话配置覆盖 |
| `story_init.rs` | 首次运行的项目初始化钩子 |
| `scheduler.rs` | 按 cron 风格的会话侧触发器 |
| `session_id.rs` | ID 生成 + 版本后缀辅助 |
| `workspace.rs` | 为工具调用解析"当前活跃仓库"路径 |

**先别急着记。** 只要抓住一个感觉：**"会话"不只是聊天记录，它是一整台机器的状态。**

对比一下你的 `harness/session.py`：你存了消息列表和事件日志。ORG2 存了消息、模型选择、工作目录、取消状态、文件清单、计划、触发器……

这不是"设计得更复杂"，而是**每一项都对应一个真实场景**：

- `file_registry.rs` 存在，是因为要回答"这个 AI 到底改了我哪些文件"
- `workspace.rs` 存在，是因为工具有相对路径，得有地方解析
- `recovery.rs` 存在，是因为应用会崩、会重启，会话不能丢

---

## ④ 一次 LLM 往返

```rust
core::session::turn::entry::process_message
```

注意原文的注释：

> One LLM round-trip

**是"一次"，不是"一个回合"。**

这两者的区别是全书一个关键概念：

| 术语 | 含义 |
|---|---|
| **LLM 往返**（round-trip） | 发一次请求给模型，拿到一次响应 |
| **回合**（turn） | 用户说一句话 到 模型彻底停下来。**一个回合里可能包含多次 LLM 往返** |

举例：

```text
回合开始
  ├─ 往返 1：模型说"我要读 a.py"     → 执行工具 → 把结果加进历史
  ├─ 往返 2：模型说"我要改 a.py"     → 执行工具 → 把结果加进历史
  ├─ 往返 3：模型说"改完了，解释如下…" → 没有工具调用 → 回合结束
回合结束
```

一个回合，三次往返。这就是为什么第 ⑤ 步的 `execute_turn` 是个**循环**，而不是一次调用。

!!! note "这一层为什么夹在中间"
    `turn/` 这一层负责"一次往返里要做哪些准备工作" —— 比如这一章开头的核心那句话：

    > `core::session::turn::entry` constructs `SkillsLoader` and `HookExecutor`.

    也就是：**在每回合开始时，加载技能和执行钩子。**

    这句话看起来平平无奇，其实是 `core ↔ intelligence` 那个双向依赖的**具体发生地点** —— core 在这里主动去够 intelligence。

---

## ⑤ 驱动循环

```rust
core::turn_executor::execute_turn
```

**这是整个系统的心脏。**

`ARCHITECTURE.md` 描述它做三件事：

1. 通过 `core::providers::*` 流式拉取 LLM 响应
2. 把工具调用块交给 `UnifiedMessageProcessor`
3. 重新流式拉取，循环，**直到模型给出 stop_reason**

第三点里的 **stop_reason** 是关键。这是模型 API 返回的一个字段，告诉你怎么停的。常见值：

| stop_reason | 意思 |
|---|---|
| `end_turn` / `stop` | 自然说完了 |
| `tool_use` / `tool_calls` | 我要调工具，你执行完再叫我 |
| **`length`** | **我被 token 上限截断了，话没说完** |
| `max_tokens` | 同上 |

**第三个值是很多玩具实现会漏掉的。**

你的 `mini-agent-harness` 现在是这样的：模型输出太长被截断，就报错，用户看到一段残句。ORG2 专门有一个文件 `length_recovery.rs` 来处理它 —— 检测到 `stop_reason = "length"` 之后，自动续写。

这个文件只有 4,648 字节，是全章最值得你抄的一个。详见 [回合执行器](turn-executor.md)。

---

## ⑥ 模型 HTTP 客户端

```rust
core::providers::*
```

**这一层只做一件事：把统一格式的请求，翻译成各家模型 API 的格式。**

为什么要"统一格式"？因为不同厂商的接口差异比你想的大：

| 厂商 | 接口形态 |
|---|---|
| Anthropic | Messages API（原生） |
| OpenAI | Chat Completions（大量厂商模仿这个格式） |
| OpenAI 新版 | Responses API（GPT-5.4+ 的工具调用必须用它） |
| ChatGPT / Codex | OAuth 登录后走 ChatGPT 后端 |

所以 `providers/` 下有四个驱动目录，外加一个共享转换层。详见 [Provider 层](providers.md)。

**一个很重要的细节**：这一层是"无状态"的。它不知道会话、不知道历史、不知道工具策略。**你喂它什么消息，它就发什么。** 这种纯粹性让它能被单独测试。

---

## ⑦ 统一消息处理器

```rust
core::session::turn::processor  →  UnifiedMessageProcessor
```

这个类名字里的 **"Unified"（统一）** 说明了一件事：**在它之前，消息有多个来源、多种形态；过了它，就是统一的了。**

它要处理的差异包括：

- 模型回复里的"文本块"和"工具调用块"交错出现
- 有些厂商把思考过程（thinking）也单独返回
- 流式响应是碎片，需要拼装
- 工具调用参数是 JSON 字符串，需要解析（而且可能不合法）

**为什么要把"统一"这件事单独抽一层？**

因为如果不抽，这段转换逻辑会散落在循环体、工具执行、持久化三处，三份实现会慢慢分叉 —— 这正是 ORG2 在 6 月吃的那个苦头（一天内四次修流式取消，见 [建造史](../history/stages.md)）。

---

## ⑧ 工具分发与执行

```rust
core::tools::*
```

到这一步，模型的"意图"变成了真实动作。

这里要做的事比想象中多：

1. **查表**：这个名字的工具存在吗？（`registry.rs`）
2. **查权限**：这个工具现在允许用吗？（`policy.rs`）
3. **校验参数**：JSON 合法吗？字段齐吗？（`params.rs`）
4. **执行**
5. **把结果转成模型能读的格式**（`result.rs`）
6. **落库**：结果可能很大，要不要单独存？（`tool_result_storage.rs`）

第 6 点单独说一下：**一个工具可能返回几万行输出**（比如跑一次全项目的 `grep`）。如果整个塞进对话历史，下一轮请求直接就爆了上下文窗口。

所以 `tool_result_storage.rs`（5,718 字节）做的事是：**大结果存到别处，历史里只留一个引用。**

这是一个很实际的设计，详见 [工具系统](tools.md)。

---

## ⑨ 外部副作用

```rust
integrations / intelligence
```

最后一步：工具真正去碰外面的世界。

- `integrations`：发一条 Slack 消息、读一个网页、调一个外部 CLI
- `intelligence`：查记忆、加载技能、跑一个 hook

**这两层是所有"不可回滚"操作的所在地。**

所以权限控制（`tools/policy.rs`）必须发生在第 ⑧ 步，**在执行之前**，而不是在这里事后检查。

---

## 顺带：什么不在这条链上

有两个东西贯穿全程，但不在上面九步里：

### 持久化

> Anything that **persists** goes through `foundation::persistence` (SQLite + file storage).

任何要落盘的东西，都走 `foundation::persistence`。

**注意措辞是"anything"** —— 不是"会话结束才存"，而是任何需要持久化的时刻都走它。

### 事件总线

> Anything that crosses an **async boundary** goes through `foundation::bus` (broadcast channels for UI/automation listeners).

任何要跨**异步边界**的东西，都走 `foundation::bus`。

这条更微妙。"异步边界"指什么？指"发出去了，但不关心谁在听、什么时候听"。

界面就是一个典型的异步消费者：内核推一个事件出去，界面可能在听，也可能用户关掉了窗口没人在听。**内核不该因此失败。**

这个设计的实体就是下一章的 [事件流](event-stream.md)。

---

## 完整路径的另一种画法

如果上面九个步骤还是抽象，用"寄快递"类比一次：

| 步骤 | 类比 |
|---|---|
| ① Tauri 命令 | 快递员上门取件（唯一和"你"接触的环节） |
| ② SessionRuntime | 分拣中心（确保同一个收件人的包裹走同一条线） |
| ③ AgentSession | 这个收件人的档案袋 |
| ④ process_message | 打包一次（一次装车） |
| ⑤ execute_turn | 运输调度（可能要跑好几趟） |
| ⑥ providers | 实际承运的航空公司 |
| ⑦ processor | 海关（把各国格式统一） |
| ⑧ tools | 收件人开门取货 |
| ⑨ integrations | 收件人真的用了这个东西 |

---

## 本章要点

1. 九个停靠点，记住顺序比记住名字重要
2. ① 是唯一的边界层，之后所有层都不知道"前端"存在
3. ② 保证"一个会话在内存里只有一个实例"
4. ③ 会话不只是聊天记录，是一台机器的状态
5. **④ 是"一次往返"，⑤ 是"一个回合"** —— 一个回合含多次往返
6. ⑤ 里最容易漏的是 `stop_reason = "length"`
7. ⑥ 无状态，⑧ 有权限，⑨ 有副作用
8. 持久化和事件总线贯穿全程，不占某一步

<p class="src-path">源码：src-tauri/crates/agent-core/src/ARCHITECTURE.md 第 1 节；各层目录树</p>

---

!!! quote "📝 我的批注 · 2026-11-06 · v0.1"
    留白。建议在这里画出你自己 harness 的九步对应图。
