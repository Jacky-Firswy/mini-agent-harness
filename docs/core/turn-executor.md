# 回合执行器

## 什么是"回合"

先把三个概念钉死，不然后面会绕。

| 概念 | 定义 | 例子 |
|---|---|---|
| **回合**（turn） | 用户说一句话，到模型彻底停下 | "帮我修这个 bug" → 一直到它说"改好了" |
| **往返**（round-trip） | 发一次请求，收一次响应 | 模型说"我要读文件" |
| **步**（step / iteration） | 循环体转一圈 | 读文件 → 拿结果 → 再问模型 |

**一个回合 = 多次往返 = 多次步。** 三者是包含关系。

`core/turn_executor/` 整个目录（约 130KB 源码），全是为了让"一个回合"能**正确、稳定、可恢复**地跑完。

## 为什么这一个循环要拆成 13 个文件

先看全景：

| 文件 / 目录 | 大小 | 职责 |
|---|---|---|
| `mod.rs` | 28,953 B | `execute_turn` 入口 + 循环体 |
| `streaming_executor.rs` | 18,374 B | 把 provider 的事件流接进循环 |
| `stream_error_recovery.rs` | 12,156 B | 流中途断线后恢复 |
| `types.rs` | 14,247 B | `TurnConfig`、`TurnInput`、`TurnOutcome` |
| `file_tracker.rs` | 7,963 B | 记录本回合碰过哪些文件 |
| `backoff.rs` | 7,216 B | 分错误类型的重试时机 |
| `stream_normalizer.rs` | 7,076 B | 不同 provider 的流格式归一 |
| `tool_result_storage.rs` | 5,718 B | 工具结果落库 |
| `screenshot.rs` | 4,872 B | 往对话注入视觉块 |
| **`length_recovery.rs`** | **4,648 B** | **被截断后恢复** |
| `usage_accumulator.rs` | 3,740 B | token / 成本记账 |
| `tool_execution/` | — | 工具调用分发 + 并行批次处理 |
| `helpers/` | — | `message_accessor`、`message_writer`、`permission`、`truncate` |

**这不是过度设计。** 每一行都对应一个真实会出的事故。本章只挑最值钱的三个讲透：**被截断**、**断线重试**、**无限循环防护**。

---

## 第一件事：模型被截断了怎么办

这是你这 600 行项目最该抄的一段。

### 问题

模型输出是有 token 上限的。写到一半被截断，API 返回：

```json
{ "stop_reason": "length" }
```

**大部分玩具实现在这里就崩了** —— 要么报错，要么把半句话当完整答案返回给用户。

`length_recovery.rs` 的解法是**两级恢复**。文件开头的注释直接把这设计交代清楚了：

> When the model truncates its output because it ran out of `max_tokens` we apply a two-tier recovery, mirroring claude_code's `runPromptCatchingMaxTokensError` in `utils/context.ts`

**注意这个"mirroring claude_code"** —— 它是明确参考了 Anthropic 官方 Claude Code 的实现。这本身是个值得学的工程态度：**别人已经踩过的坑，直接抄答案，不要自己重新发明。**

### Tier 1：静默抬高上限

**触发条件**：这是本回合第一次截断，且当前 `max_tokens` 小于 `ESCALATED_MAX_TOKENS`。

```rust
const ESCALATED_MAX_TOKENS: u32 = 64_000;
```

**动作**：

1. 把 `max_tokens` 一次性抬到 **64,000**
2. 把已经收到的残缺回复**先塞进历史**（`add_assistant_message`）
3. 再追加一条 `"Continue."` 的用户消息
4. **不告诉用户任何事**
5. `continue` —— 重新跑这一轮

**为什么叫"静默"？** 因为如果只是模型"刚好写超了一点点"，抬高上限重跑一次就完事了，用户完全没必要知道。

**这个分支只允许触发一次**，用 `tier1_escalated` 这个布尔值控制（传的是 `&mut bool`，函数内部置 true）。

!!! note "一个很细但很重要的动作"
    源码注释：

    > Roll back the partial assistant message so the escalated retry starts clean (no duplicate partial content in the transcript).

    翻译：**把残缺的助手消息回滚掉，让抬高后的重试从干净状态开始，避免对话记录里出现重复的半截内容。**

    注意它实际做的是 `add_assistant_message(...)` —— 把部分内容加进去，然后 `Continue.` 让它接着写。

    为什么这么做而不是"删掉重来"？因为删掉重来会浪费已经生成的 token（要重新付钱），而"加进去 + Continue"能让模型从断点接着写。

### Tier 2：显式续写 + 告诉用户

**触发条件**：Tier 1 已经用过了，或者当前就是 64,000 还截断，且 `output_recovery_count < MAX_OUTPUT_RECOVERY_ATTEMPTS`。

```rust
const MAX_OUTPUT_RECOVERY_ATTEMPTS: u32 = 3;
```

**动作**：

1. 同样把残缺回复塞进历史
2. 追加一条**措辞非常讲究**的续写指令
3. **这次给用户一个可见提示**
4. `continue`

那条续写指令的原文值得逐句看：

> `"Output token limit hit. Resume directly — no apology, no recap of what you were doing. Pick up mid-thought if that is where the cut happened. Break remaining work into smaller pieces."`

翻译加解读：

| 指令片段 | 在防什么 |
|---|---|
| `Resume directly` | 别客套，直接接着说 |
| `no apology` | **防止模型说"抱歉我刚才被打断了"**，浪费 token |
| `no recap of what you were doing` | **防止它复述一遍已经说过的内容**，浪费更多 token |
| `Pick up mid-thought if that is where the cut happened` | 明确允许从句子中间接上 |
| `Break remaining work into smaller pieces` | **主动要求它把活拆小**，避免马上又被截断 |

**这五条全都是在跟模型"谈判"。** 这是一个非常被低估的技能 —— 写 Agent 大量时间不是在写逻辑，是在**写能约束住模型行为的提示词**。

同时给用户的可见提示：

```rust
handler.on_message_delta(session_id, "\n\n[Output truncated — auto-continuing...]\n\n");
```

**为什么要告诉用户？** 因为这时候可能已经续写了三次，用户看到的内容是拼接的。**如果不标记，用户会以为自己看到的是模型一次说完的。**

### Tier 3：放弃

三次都用完了，返回 `LengthRecoveryOutcome::Terminal`。调用方把当前内容当作最终结果，结束循环。

### 完整流程图

```text
收到 stop_reason = "length"
        │
        ├─ Tier1 没用过 且 max_tokens < 64000 ?
        │     └─ 是 → 抬到 64000，加 "Continue."，静默重跑
        │
        ├─ output_recovery_count < 3 ?
        │     └─ 是 → 计数+1，加长指令，显示 "[Output truncated…]"，重跑
        │
        └─ 都不满足 → Terminal，结束
```

### 为什么这个设计值得学

**它把"失败"分成了三种可操作的状态**，而不是笼统的"出错了"：

1. 可能是配置太小 → 那就调大试试
2. 配置已经很大了还截断 → 那就分段做
3. 分段也做不完 → 交给用户

**这三种情况需要的处理完全不同**，混在一起处理必然有一种是错的。

---

## 第二件事：断线和限流怎么重试

`backoff.rs` 的文件注释开头就说了它为什么独立成文件：

> Kept in its own file so the policy is auditable at a glance without scrolling through the 800-line agent loop.

翻译：**单独放一个文件，这样策略能一眼审阅，不用在 800 行的 Agent 循环里翻找。**

这句话本身就是一个设计理念：**把"策略"从"流程"里抽出来。**

### 五类错误，五套预算

先看 `StreamErrorKind` 的五种值，以及各自的重试预算：

| 错误类型 | 含义 | 重试上限 | 退避倍数 |
|---|---|---|---|
| `Overloaded` | 上游明说"我满负荷了" | **3** | **×4** |
| `IdleTimeout` | 90 秒没有任何数据帧 | 10 | ×2 |
| `ConnectionError` | 连接断了 | 10 | ×1 |
| `ProviderError` | 通用 5xx 之类 | 10 | ×1 |
| `Unknown` | 未知 | 10 | ×1 |

```rust
const MAX_STREAM_ERROR_RETRIES: u32 = 10;
const MAX_OVERLOADED_RETRIES: u32 = 3;
```

**为什么 `Overloaded` 只有 3 次，比其他的少这么多？**

源码给了三条理由，我原样翻译：

> 1. 上游已经明确告诉你"我满容量了" —— 你敲得再快也没用，而且会让网关缓存反复失效
> 2. 容量雪崩期间，每次重试会造成 3-10 倍的网关放大
> 3. 放弃后用户几秒后手动重试往往能成功，因为雪崩已经过去了

**这三条是纯粹的运维经验。** 特别是第 2 条 —— "gateway amplification"（网关放大）这个概念，是说一次用户重试在后端可能变成十次请求。在雪崩期间，你的"重试"本身就是雪崩的一部分。

### 退避曲线

```rust
const STREAM_BACKOFF_BASE_MS: u64 = 500;
const STREAM_BACKOFF_MAX_MS: u64 = 32_000;
```

计算方式：

```text
delay = 500ms × 2^(attempt-1) × 类型倍数
```

再加上 **±25% 的抖动**。

**`Overloaded` 配上 ×4 倍数，实际效果是 2 秒 / 4 秒 / 8 秒**，而不是普通指数退避的 500ms / 1s / 2s。

源码注释解释了为什么：

> With `MAX_OVERLOADED_RETRIES = 3` and the fact that capacity cascades need time to cool, we want a 2s / 4s / 8s spread rather than the 500ms / 1s / 2s the plain exponential would give.

翻译：**容量雪崩需要时间冷却**，所以我们要 2/4/8 秒的间隔，而不是 0.5/1/2 秒。

### 为什么必须有抖动（jitter）

**这是分布式系统的经典问题：惊群效应（thundering herd）。**

想象 1000 个会话同时遇到限流。如果所有会话都用**完全相同**的退避时间（比如都是 2 秒），那 2 秒后这 1000 个请求会**同时**再打过去 —— 服务器又被打垮，然后再退避 4 秒，再同时打过去……

**抖动**就是给每个请求加一点随机偏移，让它们错开。

比较有意思的是它的实现方式 —— **不引入 `rand` 库**：

```rust
let jitter_pct = ((attempt as u64).wrapping_mul(7919).wrapping_add(raw)) % 50;
let jitter = raw.saturating_mul(jitter_pct) / 200;
```

注释解释：

> Deterministic pseudo-jitter seeded from (attempt, raw) — we don't pull in `rand` just for this and tokio's runtime already adds natural variance.

翻译：**用 (attempt, raw) 做种子生成确定性的伪抖动 —— 不为了这个就引入 `rand` 库，而且 tokio 运行时本身就带来了自然方差。**

**这是一个很省的决定**：抖动不需要密码学强度，只要"不同会话不同"就够了。用公式算出来的值就够了，不需要额外依赖。

### 一个测试友好设计

```rust
#[cfg(test)]
static TEST_BACKOFF_OVERRIDE_MS: AtomicU64 = AtomicU64::new(0);
```

测试时可以把退避强制设成 5ms，让原本要跑 30 秒的完整重试路径 **在 100ms 内跑完**。

而且注意这两个细节：

- `#[cfg(test)]` —— 生产二进制里根本不存在这个变量
- `#[cfg(not(test))] fn test_backoff_override_ms() -> u64 { 0 }` —— 非测试编译时直接内联返回 0，**零运行时开销**

**这是"可测试性"的教科书做法**：不改生产逻辑，只加一个测试期开关，而且保证生产构建里它不存在。

### 用户能看见倒计时

```rust
const BACKOFF_HEARTBEAT_INTERVAL_MS: u64 = 5_000;
```

如果退避时间超过 5 秒，就把一次长睡眠拆成多个 5 秒的片段，**每段发一个心跳事件**，让界面底部能显示倒计时。

注释说得很直白：

> so the frontend footer can update its countdown

**这个细节非常"产品"**：技术上完全可以一次性 sleep 8 秒，但用户会以为程序卡死了。拆成心跳，用户就知道"它在等，而且还要等多久"。

---

## 第三件事：怎么防止无限循环

Agent 循环最经典的死法：**模型反复调同一个工具，永远不停。**

`backoff.rs` 里有两个硬闸门：

```rust
const MAX_REPEAT_STREAK: u32 = 3;        // 相同工具调用签名最多重复 3 次
const MAX_CONSECUTIVE_ERRORS: u32 = 8;   // 连续工具错误最多 8 次
```

### 第一道：重复调用检测

"相同签名"是什么意思？大概是指 `(工具名, 参数)` 的组合。

如果模型连续 3 次用**完全一样的参数**调**完全一样的工具**，那基本可以断定它卡住了 —— 因为一个正常的推理不会做三次一模一样的事。

这种情况直接 `break`。

### 第二道：连续错误

工具连续失败 8 次，也停。

**为什么要 8 次而不是 2 次？** 因为有些工具会连续报错但模型能自己纠正（比如路径写错，试几次就对了）。8 次给了足够的自纠空间，又不至于无限。

### 第三道（隐含）：回合步数上限

你的 `mini-agent-harness` 里有 `MAX_STEPS = 25`，ORG2 的对应物在 `TurnConfig` 里。原理一样。

**为什么这一步必须做？** 因为没有上限的循环意味着：
- 一个 bug 能烧掉用户几百美元 API 费用
- 界面永远转圈
- 日志无限增长

**这是"必须有的保险"，不是"可选优化"。**

---

## 其余六个文件在管什么

### `usage_accumulator.rs` —— 记账

跨整个回合累加 token 和成本。

里面有个很实用的函数：

```rust
pub(super) fn cache_hit_rate(cache_read: i64, billable_input: i64) -> f64 {
    let denom = cache_read.saturating_add(billable_input).max(0) as f64;
    if denom <= 0.0 { 0.0 } else { (cache_read.max(0) as f64) / denom }
}
```

注释解释了一个容易搞错的细节：

> Note: Anthropic reports `prompt_tokens` excluding `cache_read`, so the denominator is `cache_read + prompt_tokens` — the total effective input the LLM saw on this call.

翻译：**Anthropic 报的 `prompt_tokens` 里不含缓存读取的部分**，所以分母要用 `cache_read + prompt_tokens` —— 这才是模型这次实际看到的全部输入。

还补了一句为什么这个数字重要：

> at 90% the prompt is ~10% of normal price

**90% 的缓存命中率意味着提示词只花正常价格的 10%。** 这是省钱的关键指标。

`saturating_add` 和 `.max(0)` 的用法值得注意 —— **防御负数**。这种"不该发生但万一发生"的防御，在计费相关代码里是必须的。

### `file_tracker.rs` —— 记录碰过哪些文件

一个回合里 Agent 可能读写几十个文件。这个模块负责记下来。

**为什么需要？** 因为要回答两个产品问题：

1. 这次改动涉及哪些文件？（用来生成 diff 摘要、用于代码审查）
2. 我要回滚的话，回滚哪些？

### `screenshot.rs` —— 视觉注入

往对话里插入视觉块（图片）。

注释里提到两个来源：`parent screenshots`（父会话的截图）和 `OS Agent context`（操作系统 Agent 的上下文）。

**这说明 ORG2 支持"看屏幕"** —— Agent 能看到你的桌面，然后基于截图操作。这就是 README 提到的 Computer Use。

### `stream_normalizer.rs` —— 格式归一

四个 provider 的流式事件格式各不相同，这里统一。

**为什么单独一个文件？** 因为格式差异的代码最容易膨胀，也最容易出错。单独隔离便于测试。

### `tool_result_storage.rs` —— 大结果落库

配套的常量在 `backoff.rs` 里：

```rust
pub(crate) const MAX_TOOL_OUTPUT_CHARS: usize = 100_000;
```

**10 万字符**。超过就截断（或转存）。

**这个限制你必须理解为什么存在**：上下文窗口是有限的。假设窗口 20 万 token，一个工具返回 10 万字符（约 3 万 token），几个工具就把窗口吃满了。

**注意这个限制在 `backoff.rs` 里，不在工具模块里。** 这个放置位置说明它属于"回合策略"，不是"工具实现"。

### `types.rs` —— 三个核心类型

- `TurnConfig`：这个回合的配置（上限、模型、超时等）
- `TurnInput`：输入（会话、用户消息）
- `TurnOutcome`：输出（最终内容、为什么结束、用了多少 token）

**把输入、配置、输出分成三个类型**，而不是一个大的结构体到处传，是个好习惯 —— 每一层只看它需要的。

---

## 重试的第一道防线其实不在这里

`ARCHITECTURE.md` 里还有一句关键的话：

> The retry / fallback wrapper around the LLM call lives in `core::providers::reliable::ReliableProvider`.

翻译：**LLM 调用外层的重试/降级包装，在 `core::providers::reliable::ReliableProvider` 里。**

所以重试是**两层**的：

| 层 | 管什么 |
|---|---|
| `ReliableProvider`（provider 层） | 单次 HTTP 请求失败、限流、超时 |
| `turn_executor`（回合层） | 流半途断开、整轮失败 |

**为什么分两层？** 因为它们的粒度和语义不同：

- provider 层重试：**从头再发一次这个请求**，对上层透明
- 回合层重试：**从断点续上**，需要知道已经收到了哪些内容

混在一起做，就会分不清"该重发整轮"还是"该续上"。

---

## 和你的 harness 对照

| 能力 | 你的 600 行版本 | ORG2 |
|---|---|---|
| 循环上限 | `MAX_STEPS = 25` ✅ | ✅ 有 |
| 单次请求重试 | 3 次，`2**attempt` 退避 ✅ | ✅ 更细 |
| 抖动 | ❌ 无 | ✅ ±25% |
| 按错误类型区分 | ❌ 无 | ✅ 5 类 |
| 截断恢复 | ❌ **无**（会直接报错） | ✅ 两级 |
| 断线续传 | ❌ 无 | ✅ 有 |
| token 记账 | ❌ 无 | ✅ 有 |
| 重复调用检测 | ❌ 无 | ✅ 3 次 |
| 连续错误上限 | ❌ 无 | ✅ 8 次 |

**最该先补的两个**：

1. **截断恢复**（`length_recovery.rs` 只有 4.6KB，逻辑清晰，可控）
2. **重复调用检测**（几十行代码，但能防止烧钱）

**你现在 README 里承认的那个限制** —— "无上下文压缩：聊得很长会撞上模型的上下文上限，然后报错" —— 正好是这两件事要解决的。

---

## 本章要点

1. **回合 ⊃ 往返 ⊃ 步**，三者是包含关系
2. 13 个文件不是过度设计，每个对应一类真实事故
3. 截断恢复是两级的：静默抬高上限 → 显式续写 → 放弃
4. 续写提示词的五条约束，全是在防模型浪费 token
5. 五类错误五套预算；`Overloaded` 只给 3 次，因为重试本身会加剧雪崩
6. 抖动防惊群；用确定性公式算，不引入 `rand`
7. 测试期开关用 `#[cfg(test)]`，生产构建零开销
8. 退避超 5 秒就拆心跳，让界面能显示倒计时
9. 三道防死循环闸门：重复调用 3 次、连续错误 8 次、步数上限
10. 重试分两层：provider 层重发，回合层续上

<p class="src-path">源码：src-tauri/crates/agent-core/src/core/turn_executor/ 全目录（backoff.rs、length_recovery.rs 已通读）</p>

---

!!! quote "📝 我的批注 · 2026-11-06 · v0.1"
    留白。
