# 自动化触发

## 让 Agent 自己动起来

前面所有章节都是"用户发起，系统响应"。

自动化触发反过来了：**满足某个条件，系统自己发起。**

`ARCHITECTURE.md` 第 4.5 节：

> Rule-based triggers: scheduled time, file change, etc. Look at `automation::triggers::timer::ScheduledTimeSpec` for the canonical parameter-struct pattern used to keep `spawn_*` calls readable.

三件事：

1. 规则驱动，不是 AI 驱动
2. 至少两类触发：定时、文件变化
3. `ScheduledTimeSpec` 是"参数结构体"的范式

## 触发 vs 对话：架构上的根本差别

这是本章的核心。

| | 对话 | 触发 |
|---|---|---|
| 谁发起 | 用户 | 系统 |
| 会话存在吗 | 已存在 | **可能没有** |
| 出错谁看 | 用户立刻看到 | **没人看** |
| 频率 | 人打字的速度 | 可能每分钟 |
| 成本 | 用户主动决定 | **系统自动消耗** |

**这五点差异决定了自动化必须有不同的设计。**

### 差异一：会话可能不存在

对话有明确的会话。但"每天早上 9 点检查一下依赖有没有安全更新"——**这个会话谁创建？**

所以触发系统必须能**自己创建会话**。这就是 `core::session::launch::*`（一次性会话启动器）存在的原因之一。

### 差异二：没人看着

对话出错，用户会说"重试一下"。

自动化出错呢？**没人知道。**

所以必须有：

- 失败记录（写进数据库）
- 某种通知机制（这正是 `orchestrator_notify` 模块的用途之一）

### 差异三：成本会自动累积

这是一个**必须认真对待**的问题。

假设你配了"每 5 分钟检查一次代码质量"，每个回合花 3000 token。

```text
每 5 分钟 × 24 小时 × 30 天 = 8640 个回合
8640 × 3000 token = 2592 万 token/月
```

**这不是小数目。** 所以自动化必须有：

- 频率上限
- 成本上限
- 一个"暂停所有自动化"的开关

!!! warning "⚙️ 这是推断"
    ORG2 是否实现了上述成本控制，我没有验证。这里讲的是"任何自动化系统都必须考虑"的问题，不是说 ORG2 一定做了。

## `ScheduledTimeSpec`：为什么参数要单独定义结构体

`ARCHITECTURE.md` 提到了一个具体的设计范式：

> the canonical parameter-struct pattern used to keep `spawn_*` calls readable

翻译：**参数结构体范式，用来让 `spawn_*` 系列调用保持可读。**

### 问题

假设有这样一组函数：

```rust
spawn_timer_trigger(hours, minutes, weekdays, timezone, enabled, retry, max_retry, timeout, session_id, ...)
```

十个参数。调用处是这样的：

```rust
spawn_timer_trigger(9, 0, true, "Asia/Shanghai", true, 3, 5, 300, sid)
```

**没有人能读懂这行代码。** 而且如果顺序写错（比如把 `hours` 和 `minutes` 写反），**编译器不会报错** —— 都是整数。

### 解法

```rust
struct ScheduledTimeSpec {
    hours: u8,
    minutes: u8,
    weekdays: Vec<Weekday>,
    timezone: String,
}

spawn_timer_trigger(ScheduledTimeSpec {
    hours: 9,
    minutes: 0,
    weekdays: vec![Weekday::Mon],
    timezone: "Asia/Shanghai".into(),
}, ...)
```

**好处**：

- 每个值有名字，读得懂
- 字段顺序无关
- 类型不同（`u8` vs `Vec<Weekday>`）不会互相搞混
- 加新字段有明确的默认值位置

**"canonical"（规范）这个词说明这是团队要求统一遵循的**，不是个别地方的自选动作。

## 触发器的组成

一个完整的触发器至少要包含：

| 部分 | 例子 |
|---|---|
| **匹配条件** | 每天早上 9 点 / `package.json` 变了 |
| **动作** | 启动一个会话，发一条预设的提示词 |
| **去重** | 同一个文件连续变 5 次，不要触发 5 次 |
| **失败策略** | 失败 3 次后停用 |
| **启用状态** | 可以临时关掉 |

**"去重"是最容易漏的一项。**

想想 `npm install` —— 它会改动几百个文件。如果触发器是"文件变化就运行"，那会瞬间触发几百次。

所以文件监听类触发器必须有**防抖（debounce）**：等变化停下来一段时间后，才触发一次。

## 和 `scheduler.rs` 的区别

`core/session/scheduler.rs` 也做定时（"cron-style session-side trigger"）。

两者区别：

| | `integrations/automation/` | `core/session/scheduler.rs` |
|---|---|---|
| 范围 | 全局，可以创建会话 | 会话内部 |
| 层 | 2b（外部集成） | 1（core） |
| 用途 | "每天检查安全更新" | "这个会话 30 分钟后提醒我一下" |

**同一个技术概念（定时）在两个层各有一份实现，不是重复，是作用域不同。**

## 对你的启发

你的 harness 现在是纯被动的。如果要做自动化，最小实现大概是：

```python
# 一个极简的定时触发
import threading, time

def schedule_every(seconds, prompt, session):
    def loop():
        while True:
            time.sleep(seconds)
            run_turn(session, provider, registry, prompt, bus, max_steps=10)
    threading.Thread(target=loop, daemon=True).start()
```

**但请注意三件事**：

1. **必须有一个能停的开关**，否则你关不掉它
2. **必须有成本上限**，否则半夜烧了你的余额
3. **必须记录结果**，否则失败了没人知道

**这三件事比"能不能触发"重要得多。**

---

!!! quote "📝 我的批注 · 2026-11-06 · v0.1"
    留白。
