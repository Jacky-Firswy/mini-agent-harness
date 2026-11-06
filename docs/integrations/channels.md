# 渠道与网关

## 问题：Agent 要被"叫起来"

用户可能从很多地方找 Agent：

- 桌面窗口里打字
- 手机上的 Telegram
- 团队的 Slack 频道
- 企业微信

**这些入口的协议、认证、消息格式全都不同。**

`integrations/channels/` + `integrations/gateway/` 就是解决这件事的。

## 五个渠道

`ARCHITECTURE.md` 第 4.4 节列出的：

> Telegram, Discord, Slack, WeCom, WeChat

（`lib.rs` 的模块注释里写的是 "Telegram, Discord, **Feishu**, WeCom, Weixin" —— 出现了飞书。两处列举略有差异，可能是文档更新不同步，也可能飞书和微信在企业场景下有重叠。）

每个渠道一个子目录。

## 网关做什么

> The gateway routes messages between them and the agent.

翻译：**网关在这些渠道和 Agent 之间路由消息。**

`ARCHITECTURE.md` 还提了一个具体模块：

> The merge-batch logic lives in `integrations::gateway::message_merge`.

**"合并批次"（merge-batch）** —— 这个细节说明了一个真实的用户行为问题。

## 为什么需要"合并批次"

想象这个场景：你在 Telegram 上想给 Agent 一个任务，但一句话说不完，于是连发三条：

```text
"帮我改一下登录页"
"就是那个按钮颜色"
"改成蓝色"
```

**如果不做合并**，会变成：

- 第 1 条触发一个回合 → Agent 开始分析登录页
- 第 2 条触发另一个回合 → Agent 困惑"什么按钮"
- 第 3 条又触发一个 → 三个回合互相打架

**结果：三次 API 调用、三份混乱的上下文、用户看到三条不相关的回复。**

`message_merge` 做的就是：**在一个短时间窗口内收到的多条消息，合并成一条再交给 Agent。**

这在桌面窗口里不明显（人打字快、发送有间隔），但在手机上非常常见。

**这是一个"从真实使用中长出来"的功能**，不是设计时能想到的。

## 消息总线的不对称设计

回到 [事件流](../core/event-stream.md) 里讲的：

| 方向 | 通道 | 容量 |
|---|---|---|
| 入站（渠道 → 内核） | `mpsc`（多对一） | 256 |
| 出站（内核 → 渠道） | `broadcast`（一对多） | 1000 |

在这里补充一个关键点：**`mpsc` 的"多对一"意味着所有渠道共享一个入口。**

```text
Telegram ─┐
Discord  ─┤
Slack    ─┼──► MessageBus.inbound (mpsc, 256) ──► Agent 循环
WeCom    ─┤
WeChat   ─┤
tauri    ─┘
```

**好处**：Agent 循环只从一个地方读消息，不用关心来源。

**坏处**：一个渠道涌入大量消息，会挤占其他渠道的队列容量。256 是共享的。

!!! warning "⚙️ 这是推断，不是源码原文"
    "256 是共享的"这一点是从 `mpsc` 单通道的性质推断的。源码没有说明是否为每个渠道独立分配容量。

## `InboundMessage` 的设计细节

见 [事件流](../core/event-stream.md) 里有完整字段表。这里只补充最重要的一点：

```rust
pub fn session_key(&self) -> String {
    if let Some(ref override_key) = self.session_key_override {
        return override_key.clone();
    }
    format!("{}:{}", self.channel, self.chat_id)
}
```

**默认会话 key = `{渠道}:{聊天id}`。**

所以：

| 来源 | 会话 key |
|---|---|
| 桌面窗口 A | `tauri:window-a` |
| Telegram 私聊 12345 | `telegram:12345` |
| Slack 频道 general | `slack:general` |

**每个入口默认是独立会话。**

那如果用户想让桌面和 Telegram 共享同一个会话上下文？→ 用 `session_key_override` 显式指定。

**这是一个很克制的设计**：默认隔离（安全、可预测），需要时才显式打通。

## 一个容易忽略的点：`media` 字段

```rust
pub media: Vec<String>,
```

**附件是"路径"列表，不是二进制内容。**

为什么？因为消息总线上传输的是轻量引用，不是大块数据。这和 [工具系统](../core/tools.md) 里"大结果存别处，历史里只留引用"是**同一个原则**。

## 渠道 vs 界面：本质上是同一种东西

这是本章最后一个洞察，也是理解整个架构的关键。

看 `InboundMessage` 的 `channel` 字段注释：

```rust
/// Source channel (e.g., "telegram", "discord", "cli", "tauri", "system").
```

**注意列表里有 `"tauri"`（桌面界面）。**

也就是说：**桌面界面在架构上和 Telegram 是同一类东西 —— 都是一个"渠道"。**

这是一个非常干净的设计：

```text
Telegram ─┐
Slack    ─┼──► 消息总线 ──► Agent 内核 ──► 事件流 ──► 各渠道
tauri    ─┤
cli      ─┘
```

**内核完全不知道"用户是在窗口里打字还是在手机上发消息"。**

这就是我在 [Agent 内核](../core/agent-kernel.md) 里说的"内核只认数据，不认像素"落到实处的样子。

**对你的启发**：如果你以后给 `mini-agent-harness` 加一个 Web 界面，**不要**让 `loop.py` 知道 WebSocket 的存在。而是加一个 `web` 渠道，走同样的总线。这样你的 CLI 和 Web 界面可以同时用。

---

!!! quote "📝 我的批注 · 2026-11-06 · v0.1"
    留白。
