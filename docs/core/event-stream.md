# 事件流

## 什么是"事件流"

先给定义，再讲为什么。

> **事件流 = 系统在做事情的过程中，不断往外吐出的"发生了什么"的记录。**

举个例子，模型正在回你一段话：

```text
事件1：{类型: "文本增量", 内容: "这个", 会话: "abc"}
事件2：{类型: "文本增量", 内容: "函数", 会话: "abc"}
事件3：{类型: "文本增量", 内容: "的作用", 会话: "abc"}
...
事件99：{类型: "文本完成", 内容: "这个函数的作用是…", 会话: "abc"}
```

界面上你看到文字一个个蹦出来，就是因为它一边收到这些事件，一边往屏幕上贴。

**关键问题来了**：事件是**碎片**。碎片怎么变成界面上那段完整的话？这就要引出本章的核心。

## 两个方案的对比

`foundation/streaming.rs` 开头的注释，是整个文件里最有价值的部分。它直接把旧方案和新方案并列给你看：

```text
Instead of:
  Rust → delta → WebSocket → TS accumulator → Jotai → UI

We now have:
  Rust → delta → StreamingBuffer → 完整事件 → EventStore → WebSocket → UI
```

先解释这里出现的每个名词，零基础也能读：

| 名词 | 是什么 |
|---|---|
| **Rust** | 后端（内核跑在这里） |
| **delta** | 增量，也就是一小块文本碎片 |
| **WebSocket** | 一条双向长连接，后端可以主动往前端推数据 |
| **TS accumulator** | 用 TypeScript 写的"累加器"—— 在前端把碎片拼起来 |
| **Jotai** | 一个前端状态管理库，可以理解为"前端的全局变量容器" |
| **UI** | 你看到的界面 |
| **StreamingBuffer** | 新加的缓冲器，在 Rust 这边把碎片拼起来 |
| **完整事件** | 拼好之后的整块内容 |
| **EventStore** | 事件仓库，存完整事件的地方 |

## 为什么必须删掉"TS 累加器"

这是本章最重要的一段推理。

旧方案里，**拼装碎片这件事发生在前端**。看起来没什么问题，实际有四个致命缺陷：

### 缺陷一：刷新页面，半句话就没了

累加器是内存里的一个字符串变量。用户按 F5，变量清零。

后端还在继续发 delta，但累加器是空的。于是界面上从半截开始显示，前面那部分**永远找不回来了**。

### 缺陷二：断线重连，内容对不上

WebSocket 断了 3 秒。这 3 秒里的 delta 全丢了。

重连之后，累加器从断点继续拼，拼出来的句子是残缺的。而数据库里存的是完整的。**两边不一致，而且没人知道哪个是对的。**

### 缺陷三：多端同时看，各拼各的

桌面窗口和手机端各有一个累加器，各自收到一部分 delta，拼出来的结果不一样。

### 缺陷四：没法测试

要测"累加逻辑对不对"，得启动整个前端。而后端部分的逻辑，反而一行都测不到。

### 一句话总结

> `streaming.rs` 的注释原话：**Eliminates frontend delta accumulation, providing a single source of truth.**
>
> 消除前端的增量累加，提供**单一真相**。

**"单一真相"（single source of truth）** —— 这个词请记住，它是 ORG2 全书最核心的一条设计理念。我上一轮跟你讲"三条主线"的时候说的第一场仗，打的就是它。

## `StreamingBuffer` 怎么工作

现在看实现。它的接口很短：

```rust
pub fn append_message_delta(&self, session_id: &str, content: &str) -> bool
pub fn append_thinking_delta(&self, session_id: &str, content: &str) -> bool
pub fn complete_message(&self, session_id: &str) -> Option<SessionEvent>
pub fn complete_thinking(&self, session_id: &str) -> Option<SessionEvent>
pub fn flush_expired(&self) -> Vec<SessionEvent>
pub fn clear_session(&self, session_id: &str)
```

四个要点：

### 要点一：按"类型"分开缓冲

注意 `Message` 和 `Thinking` 是两个独立的流。

**为什么？** 因为模型可能同时在做两件事：一边"想"（thinking），一边"说"（message）。这两个内容要分别拼装，否则会搅在一起。

```rust
pub enum StreamType {
    Message,
    Thinking,
}
```

### 要点二：5 秒无活动就自动收尾

```rust
const DEFAULT_TIMEOUT_MS: u64 = 5000;
```

**为什么需要超时？**

因为不是所有情况下都有明确的"我说完了"信号。模型可能因为网络问题、或者被取消，突然就不发了。这时候缓冲区里会一直挂着一堆没发出去的碎片。

超时机制保证：**5 秒没新内容，就把攒的东西当作一个完整事件发出去。**

`flush_expired()` 就是干这个的，注释说"每秒调一次"。

### 要点三：500KB 硬上限

```rust
const MAX_CONTENT_LENGTH: usize = 500_000;
```

单个流最多攒 500KB 文本。超了就从前面砍掉。

**注意它砍的方式很讲究**：

```rust
let excess = self.content.len() - MAX_CONTENT_LENGTH;
let start = self.content[excess..]
    .find('\n')                    // 从超出点往后找第一个换行
    .map(|i| excess + i + 1)       // 保留换行之后的内容
    .unwrap_or(excess);            // 找不到换行就硬砍
self.content = self.content[start..].to_string();
```

**先找换行再砍**，而不是直接在中间切一刀。

为什么？因为如果切在多字节字符（比如中文）中间，会产生乱码字节。找换行是最简单的"安全切点"策略。

!!! warning "⚙️ 这是推断，不是源码原文"
    上面关于"避免切坏多字节字符"的解释是我的推断。源码注释只说 "preserve line boundaries"（保留行边界），没有说原因。

    不过这个推断是有旁证的 —— ORG2 的架构审计文档里提过 "UTF-8 截断被重写了 10 次以上、有一处会 panic"，说明字节边界切断确实是他们踩过很多次的坑。

### 要点四：分片计数器 —— 最容易忽略的细节

这段代码我想单独讲，因为它是**"产品级代码"和"玩具代码"的真实分界线**。

```rust
segment_counters: Arc<Mutex<HashMap<BufferKey, u64>>>,
```

注释原文：

> Monotonic segment counter per (session, stream_type) so every flushed segment within a turn gets a distinct event id. Without this, a turn that interleaves `text → tool → text` would flush two segments with the same id (`stream-msg-{session}`) and the frontend's upsert would overwrite the first segment's text with the second.

翻译并展开：

**场景**：一个回合里，模型先说话，然后调工具，然后继续说。

```text
"我先看看这个文件"        ← 第一段文本
   ↓
[调用 read_file 工具]
   ↓
"看完了，问题是第 42 行"   ← 第二段文本
```

**机制**：第一段文本结束时，缓冲区清空并生成一个事件。第二段文本结束时，再生成一个事件。

**如果事件 id 只按 `stream-msg-{session_id}` 生成**，那两段的 id **完全一样**。

**后果**：前端拿到两个 id 相同的事件，会执行 `upsert`（有则更新，无则插入）。第二个事件会**覆盖**第一个。

**用户看到的现象**：第一段话凭空消失了，只剩下第二段。

!!! note "这个 bug 有多难发现"
    它只在"文本 → 工具 → 文本"这种交替模式下出现。如果你测试时只让它说一段话，永远测不到。

    而且现象是"文字消失"，不是报错 —— 用户会以为是自己看错了。

**修复**：给每个 (会话, 流类型) 配一个单调递增的计数器。

```rust
let seq = {
    let mut counters = self.segment_counters.lock().unwrap();
    let entry = counters.entry(key).or_insert(0);
    *entry += 1;
    *entry
};
let event_id = stream_event_id(stream_type, session_id, seq);
```

现在两段的 id 分别是 `stream-msg-abc-1-{uuid}` 和 `stream-msg-abc-2-{uuid}`，不会撞车。

**注意注释里还有一句关键技术细节**：

> The counter is kept alive across multiple turns for the same session so that IDs remain unique per (session, stream_type) pair.

计数器**跨回合保留**，不是每回合清零。否则第二个回合的 seq 又从 1 开始，还是会撞。

内存什么时候释放？`clear_session()` 时（会话结束时）。注释明确写了：

> Entries are purged by `clear_session()` when the session ends.

**这是一个典型的"内存泄漏 vs 正确性"权衡**：计数器和会话同生命周期，不会无限增长，但保证 id 唯一。

## `SessionEvent` 长什么样

拼装完成的完整事件，就是 `SessionEvent`。它有 **24 个字段**。我只列关键的：

| 字段 | 类型 | 作用 |
|---|---|---|
| `id` | String | 唯一标识（就是上面讲的分片 id） |
| `chunk_id` | Option\<String\> | 分片标识 |
| `session_id` | String | 属于哪个会话 |
| `created_at` | String | RFC3339 时间戳 |
| `function_name` | String | 函数名（`assistant` / `thinking` / 工具名） |
| `ui_canonical` | String | 界面上的规范名（`agent_message` / `thinking`） |
| `action_type` | String | 动作类型（`assistant` / `llm_thinking`） |
| `args` | JSON | 参数 |
| `result` | JSON | 结果 |
| `source` | enum | 来源（`EventSource::Assistant` 等） |
| `display_text` | String | 界面上显示的文字 |
| `display_status` | enum | 显示状态（`Completed` 等） |
| `display_variant` | enum | 显示样式（`Message` / `Thinking`） |
| `activity_status` | enum | 活动状态（`ActivityStatus::Agent`） |
| `is_delta` | Option\<bool\> | **是不是增量** |
| `thread_id` / `process_id` / `call_id` | Option | 各种关联 id |
| `file_path` / `command` | Option | 涉及的文件 / 命令 |
| `repo_id` / `repo_path` | Option | 仓库信息 |
| `extracted` | Option | 提取出的结构化信息 |
| `payload_refs` | Vec | 大负载的引用（不直接存内容） |
| `last_extract_at` | Option | 上次提取时间 |

### 三个设计点值得注意

**1. `is_delta` 字段。**

拼装完成的事件里，`is_delta` 是 `Some(false)`。这个字段的存在说明系统**能同时处理"增量"和"完整"两种形态**。界面可以选择只认完整事件，但底层协议兼容两种。

**2. `display_text` 和 `result` 分开。**

为什么同一个内容存两遍？

因为它们是给**不同消费者**看的：
- `display_text` 是给界面直接渲染的
- `result` 是给程序解析的结构化数据

如果只有 `result`，界面每次都要解析 JSON；如果只有 `display_text`，程序没法处理。

**3. `payload_refs`。**

大内容的引用列表。这和 `tool_result_storage.rs` 是同一个思路：**大东西存别处，事件里只放指针。**

否则一条事件几百 KB，存进数据库会把库撑爆。

### `recompute_extracted()`

`to_event()` 的最后一行：

```rust
event.recompute_extracted();
```

这个方法是"重新计算提取内容"。具体逻辑我没读，但从命名能看出：**事件的派生字段是可以从原始字段重算的。**

这是一个好习惯 —— 派生数据不当作事实来源，随时能从原始数据重建。

## 顺带讲清楚：事件流 ≠ 消息总线

这两个概念经常被混为一谈，但在这个代码库里是**两个不同层次的东西**。

| | 事件流 | 消息总线 |
|---|---|---|
| 位置 | `foundation/streaming.rs` | `foundation/bus/` |
| 解决什么 | 把碎片拼成完整事件 | 把消息从 A 送到 B |
| 方向 | 内核 → 界面 / 其他监听者 | 多渠道 ↔ 内核 |
| 关键结构 | `StreamingBuffer` | `MessageBus<I, O>` |

**关系是：事件流负责"攒"，消息总线负责"送"。**

拼好的 `SessionEvent` 通过总线的广播能力送出去。

## 消息总线：一个不对称的设计

`foundation/bus/mod.rs` 的注释第一句就点明了：

> Uses tokio channels: `mpsc` for inbound (many-to-one) and `broadcast` for outbound (one-to-many).

两种通道，两个方向：

| 方向 | 通道类型 | 容量 | 语义 |
|---|---|---|---|
| **入站**（渠道 → 内核） | `mpsc` | 256 | 多生产者，单消费者 |
| **出站**（内核 → 渠道） | `broadcast` | 1000 | 单生产者，多消费者 |

```rust
const INBOUND_CAPACITY: usize = 256;
const OUTBOUND_CAPACITY: usize = 1000;
```

**为什么入站用小容量、出站用大容量？**

逻辑是：

- **入站**（用户发来的消息）：你不希望它堆积。256 条排队已经很多了，说明系统处理不过来了。**堆积起来只会让延迟越来越大**，不如早点暴露问题。
- **出站**（内核推出去的事件）：事件是高频的（想想流式文本），而且可以有多个消费者（界面 + 调试 WebSocket + 自动化监听）。1000 的余量更大，避免频繁丢事件。

!!! warning "⚙️ 这是推断，不是源码原文"
    上面两个容量值的**设计动机**是我的推断。源码只给了数字，没给理由。

### `InboundMessage` 的关键字段

```rust
pub struct InboundMessage {
    pub channel: String,           // 来源渠道："telegram" / "discord" / "tauri" / "cli" / "system"
    pub sender_id: String,         // 发送者
    pub chat_id: String,           // 会话标识
    pub content: String,           // 文本
    pub timestamp: DateTime<Utc>,  // 时间
    pub media: Vec<String>,        // 附件路径
    pub metadata: HashMap<String, Value>,  // 渠道特有的元数据
    pub session_key_override: Option<String>,  // 覆盖会话键
}
```

**最值得注意的是最后一个字段。**

`session_key_override` 的注释：

> When set, this value is used instead of `{channel}:{chat_id}`. Used by channel/gateway dispatch so Tauri frontend events have a matching session_id.

默认情况下，会话 key 是 `{channel}:{chat_id}`，比如 `telegram:12345`。

但有个问题：**如果你在桌面窗口里和 Agent 聊天，然后切换到 Telegram 继续聊，这两个是不同的会话（`tauri:xxx` vs `telegram:12345`），历史不共享。**

`session_key_override` 就是解决办法 —— 允许显式指定会话 key，把两个入口绑到同一个会话上。

### 出站：`OutboundMessage`

```rust
pub struct OutboundMessage {
    pub channel: String,
    pub chat_id: String,
    pub content: String,
    pub reply_to: Option<String>,   // 回复的是哪条
    pub media: Vec<String>,         // 附件
    pub metadata: HashMap<String, Value>,
}
```

比入站少了 `sender_id`（出站不需要知道"谁发的"，只有"发给谁"）、`timestamp`（不重要）、`session_key_override`（不需要）。

多了 `reply_to`。

**这个差异本身就是设计**:入站要"识别身份"，出站要"定位目标"。

## 一个很聪明的解耦技巧：IoC 函数指针

这段是全章技术含量最高的部分。

问题：**内核需要往界面推事件。但界面在 `app` 层（更上面）。按依赖规矩，内核不能往上 import。**

怎么办？

`bus/mod.rs` 的答案：

```rust
type BroadcastFn = fn(String);
static BROADCAST: OnceLock<BroadcastFn> = OnceLock::new();

pub fn register_broadcast(broadcast_fn: BroadcastFn) {
    let _ = BROADCAST.set(broadcast_fn);
}
```

**内核只定义一个"空的插槽"（`OnceLock`），启动时由上层把真正的函数塞进来。**

注释解释得很清楚：

> The actual broadcaster lives in `api::websocket_handler` (the `app` layer). We register a function pointer at startup so this module — and any future extracted `agent-core` crate — has no compile-time back-edge into `app`.

翻译：真正的广播器住在 `app` 层的 `api::websocket_handler`。我们在启动时注册一个函数指针，这样本模块（以及未来可能被单独抽出来的 `agent-core` crate）**在编译期没有一条反向依赖指向 `app`**。

这个手法叫 **IoC（控制反转）**。日常见到的 IoC 是"依赖注入"（把对象传进来），这里是它的轻量版 —— **只传函数指针**。

**好处**：内核可以被单独编译、单独测试，不需要拖着整个界面层。

还有个配套设计：

```rust
pub fn frontend_subscriber_count() -> usize {
    SUBSCRIBER_COUNT.get().map(|f| f()).unwrap_or(0)
}
```

**问"现在有几个前端连着"这件事，也要通过插槽**。没注册时返回 0，注释说这是"安全的默认值"。

**为什么要问这个？** 因为如果没人在听（比如你关了窗口），系统可能选择不推送、或者改为攒起来。这个判断让内核对"有没有观众"保持敏感，但不依赖观众是谁。

## `broadcast_event` helper

最后一块拼图。发送事件的统一入口：

```rust
pub fn broadcast_event<T: serde::Serialize>(event_type: &'static str, payload: T) {
    #[derive(serde::Serialize)]
    struct EventEnvelope<T: serde::Serialize> {
        r#type: &'static str,
        payload: T,
    }
    // ... 序列化后交给注册的广播函数
}
```

它把所有事件包装成统一信封：

```json
{ "type": "某个事件类型", "payload": { ... } }
```

**这个信封设计的好处**：前端拿到消息，先看 `type` 决定用哪个组件渲染，再看 `payload` 取数据。**不需要猜**。

如果失败呢？源码写了：

```rust
None => tracing::warn!("[bus] broadcast handler not registered; dropping event"),
```

没注册就**记一条警告然后丢弃**，不 panic。

**这个选择很重要**：事件是"尽力而为"的，不是"必须送达"的。丢了不影响正确性（因为真相在数据库里），只影响实时性。

## 整章串起来

一条消息的完整生命周期，从"碎片"到"你看到"：

```text
模型 API 吐出一堆 delta
        ↓
StreamingBuffer.append_message_delta()   ← 按类型攒
        ↓
（5 秒无活动 / 收到结束信号）
        ↓
StreamingBuffer.complete_message()       ← 变成一个完整 SessionEvent
        ↓  带着唯一的分片 id
EventStore.upsert(event)                 ← 存进真相
        ↓
broadcast_event(type, payload)           ← 包成 {type, payload}
        ↓
BROADCAST 插槽（启动时注册的函数指针）
        ↓
WebSocket / Tauri IPC Channel
        ↓
前端：按 type 选组件，按 payload 渲染
```

**注意这条链上，界面是最后一个环节，而且可以缺席。** 界面不在的时候，前面全部正常工作，数据照样落库。

这就是"内核无界面"这个设计落到实处的样子。

---

## 本章要点

1. 事件流 = 系统不断吐出的"发生了什么"记录，本质是碎片
2. 旧方案在前端拼装碎片，导致刷新丢失、断线不一致、多端不同步、无法测试
3. 新方案在 Rust 侧用 `StreamingBuffer` 拼装，实现"单一真相"
4. 缓冲按 Message / Thinking 分开；5 秒超时自动收尾；500KB 上限按换行切
5. **分片计数器**解决了"文本→工具→文本"导致事件 id 撞车、前一段消失的隐蔽 bug
6. `SessionEvent` 有 24 个字段，`display_text` 给界面、`result` 给程序、`payload_refs` 存指针
7. 事件流负责"攒"，消息总线负责"送"，是两个层次
8. 总线入站用 mpsc（256）、出站用 broadcast（1000）
9. IoC 函数指针让内核不必反向依赖界面层
10. `broadcast_event` 统一信封 `{type, payload}`，发送失败只记警告

<p class="src-path">源码：src-tauri/crates/agent-core/src/foundation/streaming.rs（20,303 B）、src-tauri/crates/agent-core/src/foundation/bus/mod.rs、foundation/bus/events.rs</p>

---

!!! quote "📝 我的批注 · 2026-11-06 · v0.1"
    留白。
