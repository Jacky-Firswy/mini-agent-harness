# 我自己的 harness 对照

## 你的项目现状

`D:\AIAgentOrg2\项目\` —— `mini-agent-harness`，MIT 许可，已开源。

约 600 行核心代码，7 个文件，23 项冒烟测试全绿，不需要 API Key 也能测。

```
harness/
  config.py      2,261 B    配置 + 系统提示词
  bus.py           726 B    事件总线
  provider.py    3,378 B    OpenAI 兼容 provider + 重试
  tools.py       8,593 B    四个工具 + 沙箱
  session.py     3,994 B    JSONL 落盘 + 回放
  loop.py        2,866 B    回合循环
  main.py        4,575 B    CLI 入口
```

## 逐层对照表

| 能力 | 你的实现 | ORG2 对应 | 状态 |
|---|---|---|---|
| 回合循环 | `loop.run_turn()` | `turn_executor::execute_turn` | ✅ 有，但薄 |
| 工具抽象 | `Tool` dataclass | `Tool` trait | ✅ 对齐 |
| 工具注册表 | `ToolRegistry` | `registry.rs` | ✅ 对齐 |
| 参数 schema | `Tool.schema()` | `traits.rs` | ✅ 对齐 |
| 沙箱 | `_sandbox()` | `foundation/security/` | ✅ 有 |
| 模型调用 | `OpenAICompatProvider` | `openai_compat/` | ✅ 同一条路 |
| 重试 | 3 次，指数退避 | 5 类错误，各自预算 | ⚠️ 有，但粗 |
| 事件总线 | `Bus.publish()` | `MessageBus<I,O>` | ⚠️ 有，但直接打印 |
| 会话落盘 | JSONL 追加 | SQLite | ✅ 够用 |
| 回放 | `replay()` | `EventStore` + 界面 | ✅ 有，ORG2 更强 |
| 循环上限 | `MAX_STEPS=25` | `TurnConfig` | ✅ 对齐 |
| 输出截断 | `_truncate(8000)` | `MAX_TOOL_OUTPUT_CHARS=100000` | ✅ 对齐 |

## 你缺的东西，按优先级排

### 优先级 1：会崩的（必须补）

| 缺什么 | 后果 | 推荐做法 |
|---|---|---|
| **上下文压缩** | 聊长了直接报错 | 见下方代码 |
| **截断恢复** | 模型写一半被切断，返回残句 | 抄 `length_recovery.rs` 的两级策略 |

### 优先级 2：会烧钱的

| 缺什么 | 后果 | 推荐做法 |
|---|---|---|
| **重复调用检测** | 模型卡在一个工具上无限循环 | 相同 (名, 参数) 3 次就中断 |
| **连续错误上限** | 工具一直失败，循环不停 | 8 次就中断 |
| **token 记账** | 不知道花了多少钱 | 每回合累加并打印 |

### 优先级 3：能变成产品的

| 缺什么 | 后果 | 推荐做法 |
|---|---|---|
| **工具权限策略** | 危险操作无人拦 | 二十行确认提示 |
| **事件攒批** | 没法加界面 | 见 [事件流](../core/event-stream.md) |
| **模型窗口表** | 没法做预算 | 一张字典 |
| **provider 常量** | 字符串比较会静默失效 | 定义常量 |

## 最该先写的两段代码

### 一、上下文压缩（约 30 行）

放在 `harness/loop.py` 里，每次 `run_turn` 开头调用：

```python
def compact_if_needed(messages, provider, limit=40):
    if len(messages) <= limit:
        return messages
    head, tail = messages[:3], messages[-10:]
    middle = messages[3:-10]
    text = "\n".join(
        f"{m['role']}: {m.get('content') or '[工具调用]'}" for m in middle
    )
    summary = provider.chat(
        [
            {"role": "system", "content": "把下面的对话压缩成要点。保留所有关键决定、文件路径、以及待办事项。"},
            {"role": "user", "content": text},
        ],
        tools=[],
    )
    note = {"role": "user", "content": f"[早期对话摘要]\n{summary}"}
    return head + [note] + tail
```

**这解决了你 README 里写的"无上下文压缩"限制。**

### 二、防死循环（约 15 行）

在 `run_turn` 的工具分发处：

```python
seen = {}
consecutive_errors = 0

for call in tool_calls:
    sig = (call.function.name, call.function.arguments)
    seen[sig] = seen.get(sig, 0) + 1
    if seen[sig] >= 3:
        return "（检测到重复调用，本轮中止。）"

    result = registry.execute(call.function.name, call.function.arguments)
    if result.startswith("错误") or result.startswith("Error"):
        consecutive_errors += 1
        if consecutive_errors >= 8:
            return "（连续工具失败 8 次，本轮中止。）"
    else:
        consecutive_errors = 0
```

## 你和 ORG2 的真实差距

不要说"我只差 100 万行"。**差的不是行数，是三类东西：**

### 1. 失败路径的厚度

你的代码假设"一切顺利"。ORG2 的每个模块都在处理"顺利之外的情况"：

- 断了怎么办
- 被截断怎么办
- 重复了怎么办
- 太多了怎么办
- 名字撞了怎么办

**这占了它 70% 的代码量。**

### 2. 单一真相的纪律

你的 `Bus` 直接 `print`，没有"攒批"的概念。

要做到 ORG2 那样，你得回答：**谁是真相？** 打印出来的东西不算真相，它转瞬即逝。

### 3. 多入口的抽象

ORG2 把 `tauri` 当成和 `telegram` 并列的一个渠道。你的入口是 `argparse`。

**如果要加 Web 界面，你需要先做这个抽象** —— 否则 `loop.py` 会慢慢长出 `if is_web:` 这种分支。

## 一个鼓励性的观察

你的 600 行里，**该有的抽象一个都没少**：

- 工具是对象，不是 if-else
- provider 是可替换的
- 事件走总线，不直接耦合
- 会话落盘 + 可回放
- 沙箱检查

**这些恰恰是最难教的部分。** 剩下的（重试策略、压缩、记账）都是"照着做"就能对的工程细节。

**你的骨架是对的。** 剩下的只是把它变厚。

---

!!! quote "📝 我的批注 · 2026-11-06 · v0.1"
    留白。
