# Skills · MCP · Hooks

## 三种给 Agent 加能力的方式

这三样东西经常被混为一谈，但**它们的本质完全不同**：

| 方式 | 本质 | 侵入程度 |
|---|---|---|
| **Skills** | 一段 Markdown 提示词 | 最轻 |
| **MCP** | 一个协议，接到外部服务 | 中等 |
| **Hooks** | 拦截点，在流程中插入自己的逻辑 | 最重 |

## Skills：提示词当插件

`ARCHITECTURE.md` 原文：

> Markdown-with-frontmatter capabilities the agent can opt into.

翻译：**带 frontmatter 的 Markdown，Agent 可以选择性启用。**

"frontmatter" 是指文件开头 `---` 包起来的那段元数据，像这样：

```markdown
---
name: 写单元测试
description: 当用户要求补测试时使用
---

写测试时遵循以下约定：
1. 一个测试只验证一个行为
2. 测试名使用 `test_<被测量>_<场景>_<预期>`
...
```

**这就是全部。** 没有代码，没有协议，就是一篇文章。

### 为什么这么设计

因为**很多"能力"的本质是一套做事规范**，不需要代码。

"You are an expert at X" 这种内容，写成代码纯属浪费 —— 模型读得懂自然语言。

### 两个配套机制

原文提到：

- `skills/market.rs` —— 市场目录和本地安装流程
- `skills/builtin_data/` —— 编译进二进制的内置技能

**"market"（市场）** 说明技能可以分发、可以安装。这是个产品化设计 —— 用户可以共享自己的技能。

**"builtin_data"** 说明有些技能是硬编码进二进制的，开箱即用。

### 加载时机

回到 [一条消息的旅程](../core/message-journey.md) 第 ④ 步：

> `core::session::turn::entry` constructs `SkillsLoader` and `HookExecutor`.

**在每回合开始时加载。** 这也是 `core ↔ intelligence` 双向依赖发生的地方。

## MCP：接外部服务

`ARCHITECTURE.md` 原文：

> Model Context Protocol bridge. `manager/` owns connections; `client/` is the per-server runtime; `bridge::register_mcp_tools` adapts MCP tools into `core::tools`.

三层结构：

| 层 | 职责 |
|---|---|
| `manager/` | 拥有所有连接 |
| `client/` | 单个服务器的运行时 |
| `bridge::register_mcp_tools` | **把 MCP 工具适配成 `core::tools` 的工具** |

### 核心洞察

**MCP 的价值在于"适配"这一步。**

一个外部服务通过 MCP 暴露能力，ORG2 把它们**转换成普通的工具**。对模型来说，一个 MCP 工具和一个内置的 `read_file` 长得一模一样。

**所以模型不需要知道 MCP 是什么。**

### 一个真实的问题：工具名撞车

原文：

> Tool-name collisions with built-ins are gated at registration time (see `init::mcp_wiring::register_mcp_tools_from_app`).

翻译：**MCP 工具和内置工具重名时，在注册阶段拦截。**

**为什么会在注册阶段处理，而不是调用阶段？**

因为如果在调用阶段处理，每个调用点都要判断"这个名字是内置的还是 MCP 的"。而在注册阶段一次解决，之后所有代码都假设"名字全局唯一"。

**这是"把复杂性关在边界内"的典型手法** —— 和 [工具系统](../core/tools.md) 里"参数校验必须在执行之前"是同一个思路。

## Hooks：拦截点

原文只在记忆那一节提了一句 `intelligence/hooks/`，没有详细展开。但从名字和它的位置（在 `turn/entry` 里被构造），能推断它的用途。

!!! warning "⚙️ 这是推断，不是源码原文"
    下面关于 Hooks 的机制描述是基于 "[HookExecutor::load]" 这个调用点和目录名的推断，我没有读到 hooks 的具体实现。

Hook（钩子）的通用含义是：**在主流程的某些固定位置，允许外部插入自定义逻辑。**

常见的钩子位置：

```text
用户消息到达      ← pre-message hook
  ↓
模型请求发出前    ← pre-request hook（可以改提示词）
  ↓
模型响应收到后    ← post-response hook（可以改内容、可以拦截）
  ↓
工具调用前        ← pre-tool hook（可以拒绝）
  ↓
工具调用后        ← post-tool hook（可以改结果）
```

**Hook 和 Skill 的根本区别**：

- Skill 是"**告诉模型怎么做**"（影响模型）
- Hook 是"**绕过模型直接干预流程**"（影响系统）

所以 Hook 更强大，也更危险 —— 它能在模型不知情的情况下改变行为。

`ARCHITECTURE.md` 里 `intelligence/policies/` 和 `hooks/` 并列，说明**自主性策略**和**钩子**是一对配套物：hook 提供能力，policy 限制能力。

## 三者的选择建议

如果你要给自己的 harness 加扩展能力，按这个顺序考虑：

| 需求 | 用什么 | 理由 |
|---|---|---|
| 改变模型的行为风格 | **Skill**（一段提示词） | 零成本，改一次就生效 |
| 接入一个外部服务 | **MCP 或直接写工具** | 需要真正的 I/O |
| 强制某些事必然发生 | **Hook** | 不能依赖模型自觉 |

**最容易犯的错是"用 Skill 做 Hook 该做的事"。**

比如"每次写文件后必须跑测试" —— 写成 Skill 是"请记得跑测试"，模型有时会忘；写成 Hook 是"写文件后自动触发"，必然发生。

**判断标准：这件事能不能容忍模型偶尔不做？**

- 能容忍 → Skill
- 不能容忍 → Hook 或工具层强制

---

!!! quote "📝 我的批注 · 2026-11-06 · v0.1"
    留白。
