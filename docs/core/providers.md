# Provider 层

## 这一层为什么不能"统一成一套"

直觉上，既然所有模型都是"发消息、收回复"，那写一套代码支持所有厂商不就行了？

**不行。因为各家的差异不是格式差异，是语义差异。**

一个例子就能说明：OpenAI 的 `Chat Completions` 里，工具调用参数是**一段 JSON 字符串**；而 Anthropic 的 `tool_use` block 里，参数是**结构化的对象**。

再举一个：Anthropic 的 `prompt_tokens` **不包含**缓存读取的部分（见 [回合执行器](turn-executor.md) 里的 `cache_hit_rate`）。OpenAI 的语义不一样。

**这些差异没法用一个"适配层"抹平** —— 一厢情愿地去抹平，最后一定会得到一个到处是 `if` 的怪物。

## 四个驱动 + 一个共享层

`ARCHITECTURE.md` 第 3.4 节列出了全部：

```text
core/providers/
├── anthropic_native/    原生 Anthropic Messages API（Claude 首选）
├── openai_compat/       OpenAI Chat Completions 格式
├── openai_responses/    OpenAI Responses API（GPT-5.4+ 工具调用必须用）
├── chatgpt_codex/       Codex OAuth 的 ChatGPT 后端变体
└── responses_common/    OpenAI Responses 和 Codex 共用的转换器
```

### 逐个说明

**`anthropic_native/`** —— 原文说 "preferred for Claude"（Claude 的首选）。

为什么不直接用兼容层？因为 Anthropic 的原生 API 有兼容层拿不到的能力（比如 thinking、cache control 的细粒度控制）。

**`openai_compat/`** —— 这个覆盖面最广。原文列了：

> DeepSeek, Groq, Gemini, OpenRouter, Azure, etc.

**注意 Gemini 也在这个列表里** —— 说明 Google 提供了 OpenAI 兼容接口。

**这是对普通开发者最实用的一个驱动**：只要一个服务号称"兼容 OpenAI 格式"，就能接进来。

!!! note "你的 harness 用的就是这一路"
    你的 `OpenAICompatProvider` 对应 `openai_compat/`，默认指向 `https://api.deepseek.com/v1`。

    **所以你已经理解了这条路径的核心逻辑。**

**`openai_responses/`** —— 原文：

> required for GPT-5.4+ tool use

翻译：**GPT-5.4 及以后的工具调用，必须用 Responses API。**

这句话包含一个很硬的事实：**旧的 Chat Completions 协议在新模型上不支持工具调用。** 所以它不是"可选的新接口"，是"不升级就用不了"。

**`chatgpt_codex/`** —— Codex OAuth 的变体。

这个的存在对应 README 那句 "bring-your-own keys **and existing subscriptions**"（自带密钥**和已有订阅**）。

意思是：如果你有 ChatGPT Plus/Pro 订阅，可以用 OAuth 登录直接走你的订阅额度，而不是另外买 API Key。

**这对用户是实打实的省钱** —— 订阅已经付过了。

**`responses_common/`** —— 共享转换器，被 `openai_responses/` 和 `chatgpt_codex/` 使用。

**为什么要抽出来？** 因为这两个走的是**同一套协议**，只是认证方式不同。协议转换写两遍必然分叉。

## 工厂：一个函数决定一切

```rust
providers::factory::create_provider_with_reliability
```

所有 provider 的创建都走这一个函数。名字里的 `_with_reliability` 说明它**顺带把重试包装也做上了**（即 `ReliableProvider`）。

**这是"单一入口"模式的经典应用**：

- 好处一：所有 provider 初始化逻辑集中，不会有的地方忘了加超时
- 好处二：要加一个新的降级策略，改一处
- 好处三：测试可以直接打这个入口

## 那条最有名的硬规矩

`ARCHITECTURE.md` 用加粗写了这一条：

> **Never compare `spec.name == "anthropic"`; always `== provider_id::ANTHROPIC`.**

翻译：**永远不要用 `spec.name == "anthropic"` 这种字符串比较，永远用 `== provider_id::ANTHROPIC`。**

**为什么文档要专门为这件事加粗？** 因为这是一个一定会犯、而且犯了不会报错的错误。

### 字符串比较会怎么害你

假设代码里写：

```rust
if spec.name == "anthropic" { /* 用原生驱动 */ }
```

然后有人加了一个 provider，名字叫 `"Anthropic"`（大写 A）。

**编译通过，测试可能也通过，但这个分支永远不成立了。** 于是它静默地走了兼容驱动，行为不对，但没人知道为什么。

更隐蔽的情况：从配置文件读进来的名字带空格（`"anthropic "`）、或者显示名和内部 id 不一样。

### 常量的好处

```rust
if spec.id == provider_id::ANTHROPIC { /* ... */ }
```

- 拼错 → **编译报错**
- 想改名字 → **改一处**
- 想知道有哪些 provider → **看常量定义就够了**

**这条规矩的本质是：把"运行时的字符串契约"变成"编译期的类型契约"。**

这和工具系统里 `names.rs`（工具名常量，473 字节）是**同一条纪律的两次应用**。当你发现同一个原则在两个地方出现，说明它是这个团队的底层信念，不是偶然。

## 模型 → 上下文窗口表

原文：

> The model → context-window table and the model-name normalizer (`sonnet-4.5` → `claude-sonnet-4.5`) also live in `providers::registry`.

两件事：

**1. 模型 → 上下文窗口的映射表。**

为什么要这张表？因为要做 [回合执行器](turn-executor.md) 里的上下文压缩、要算 token 预算、要决定工具结果能塞多少。

**不知道窗口大小，就没法做任何预算决策。**

**2. 模型名归一化。**

用户可能写 `sonnet-4.5`，但 API 要的是 `claude-sonnet-4.5`。

这个"友好名 → 真实名"的转换看起来琐碎，但**不做的话用户每次手打模型名都会失败**。

!!! warning "⚙️ 这是推断，不是源码原文"
    归一化函数的具体实现方式（是查表还是拼规则）我没读到。原文只给了这一个例子。

## `ReliableProvider`：重试的第一道防线

见 [回合执行器](turn-executor.md) 里"重试的第一道防线其实不在这里"一节。这里补充层次关系：

```text
AgentSession
  └─ turn_executor          ← 第二道：整轮/续传
       └─ ReliableProvider   ← 第一道：单次 HTTP 请求
            └─ 具体驱动（anthropic_native / openai_compat / ...）
```

**为什么 `ReliableProvider` 在最里层？**

因为它对上层透明 —— 上层只管"给我一个响应"，不知道底层重试了几次。

**这个"透明重试"是有代价的**：上层无法知道"这次成功了但重试了 5 次"。所以 `usage_accumulator.rs` 需要单独记账。

## 一个容易忽略的细节：驱动是无状态的

我在 [一条消息的旅程](message-journey.md) 里提过，这里展开：

**provider 不知道**：
- 这是哪个会话
- 对话历史有多长
- 工具策略是什么
- 用户有没有点取消

它只知道：**给我一批消息和一个工具列表，我发出去，把响应还给你。**

**这种纯粹性带来三个好处**：

1. **可单独测试** —— 不需要构造整个会话
2. **可替换** —— 换一个 provider 不影响上层
3. **可并行** —— 无状态则无锁

**这也解释了为什么"模型选择"在 `AgentSession` 里而不是在 provider 里** —— provider 只是执行者，不是决策者。

## 和你的 harness 对照

| 概念 | 你的实现 | ORG2 |
|---|---|---|
| 驱动数量 | 1 个（`OpenAICompatProvider`） | 4 个 + 1 共享层 |
| 工厂 | `build_provider()` | `create_provider_with_reliability()` |
| 重试 | 内建在 `chat()` 里，3 次 | 抽到 `ReliableProvider` |
| 退避 | `2 ** attempt` | 按错误类型分 5 类，±25% 抖动 |
| provider 标识 | ❌ 无（只有一个） | ✅ `provider_id::*` 常量 |
| 模型窗口表 | ❌ 无 | ✅ `providers::registry` |
| 模型名归一化 | ❌ 无 | ✅ 有 |

### 你现在缺的两个实际问题

**问题一：没有窗口表，就没法做预算。**

你的 `MAX_OUTPUT_CHARS = 8000` 是个固定值。但如果模型窗口是 100 万 token，8000 太保守；如果是 8000 token 的小模型，又太激进。

**加一张小表就能解决**：

```python
CONTEXT_WINDOWS = {
    "deepseek-chat": 128_000,
    "gpt-4o": 128_000,
    "claude-sonnet-4.5": 200_000,
}
```

**问题二：字符串比较的隐患。**

你的代码里如果以后要判断"用的是哪个模型"，请现在就养成用常量的习惯。

---

## 本章要点

1. 各厂商的差异是**语义差异**，不是格式差异，硬抹平会得到 `if` 怪物
2. 四个驱动：Anthropic 原生、OpenAI 兼容、OpenAI Responses、Codex OAuth
3. `openai_responses` 不是可选项 —— GPT-5.4+ 的工具调用必须用它
4. `chatgpt_codex` 让"已有订阅"能直接用，对用户是真省钱
5. 所有 provider 走同一个工厂入口
6. **永远不要字符串比较 provider 名**，用 `provider_id::*` 常量
7. 模型窗口表和名称归一化都在 `providers::registry`
8. `ReliableProvider` 是最内层的透明重试
9. 驱动是无状态的，所以可测试、可替换、可并行

<p class="src-path">源码：src-tauri/crates/agent-core/src/core/providers/；ARCHITECTURE.md 第 3.4 节</p>

---

!!! quote "📝 我的批注 · 2026-11-06 · v0.1"
    留白。
