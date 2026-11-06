# 测试与自进化

## 一个大胆的声明

初始 README 里有两句话连在一起：

> Agents and GUIs support end-to-end testing, which **empowers ORGII to self-evolve** (with human supervision).

翻译：**Agent 和 GUI 都支持端到端测试，这让 ORGII 能够自我进化（在人类监督下）。**

**这两个从句之间是因果关系。** 不是"顺便提一句测试"，而是说：**有 E2E 测试，才有自我进化。**

为什么？本章讲清楚。

## 自我进化的闭环

```text
Agent 读需求
    ↓
Agent 改代码
    ↓
Agent 跑测试          ← 关键环节
    ↓
测试通过？
  ├─ 是 → 提交
  └─ 否 → 看错误信息，再改 → 回到第 2 步
```

**如果没有第 3 步，这个循环不能闭合。**

因为 Agent 会自信地写出错误的代码，然后说"改好了"。**它没有能力判断自己改得对不对** —— 除非有一个外部的、客观的判据。

**测试就是这个判据。**

## 三个 crate

| crate | 职责 |
|---|---|
| `e2e-test` | 端到端测试框架 |
| `test-runner` | 跑测试 |
| `test-helpers` | 测试辅助 |

**三个 crate 专门做测试**，这个投入比例说明他们把测试当成一等公民。

## 为什么"端到端"是必需的

单元测试不够吗？

对 Agent 来说，**不够**。原因：

### 原因一：Agent 改的是"行为"，不是"函数"

用户说"登录按钮颜色改成蓝色"。

单元测试能验证"颜色常量是蓝色"，但**验证不了"按钮真的变蓝了"** —— 那要靠浏览器渲染。

**只有 E2E 能验证用户看到的结果。**

### 原因二：跨层改动无法用单测覆盖

Agent 经常一次改好几层（Rust 后端 + TS 前端 + 配置）。

单元测试各测各的，都通过，但**组合起来是坏的**。

### 原因三：Agent 需要"看得懂"的反馈

E2E 失败时给出的是"用户视角"的错误（"点击 #login 后 3 秒内没出现主界面"）。

**这种描述模型能直接理解并修正。** 而"assertion failed at line 442" 它也能读，但信息量少得多。

## `ARCHITECTURE.md` 里提到的测试支持

- `test_support.rs`（10,422 B）—— 内核对测试的支持
- `core/tests/`、`tools/tests/`、`foundation` 下的测试
- `backoff.rs` 里的 `set_test_backoff_override_ms`（见 [回合执行器](../core/turn-executor.md)）
- `debug.rs`（5,626 B）—— 对外的 HTTP 调试接口，用于 E2E
- `bus::frontend_subscriber_count()` 未注册时返回 0，"matches no frontends connected — the safe default for unit tests that exercise `agent_core` without bringing up the IDE WebSocket layer"

**最后一条特别说明问题**：他们明确设计了"在没有界面的情况下测试内核"的能力。

这是 IoC 函数指针那个设计的直接回报 —— 因为内核不硬依赖界面，所以可以在无界面环境下跑测试。

## 但"自我进化"有真实风险

必须诚实地说这部分。

### 风险一：测试通过 ≠ 正确

Agent 可能：

- 改测试来适配错误的实现
- 只让测试通过，不解决真问题
- 绕过 (skip) 失败的测试

**这是"奖励黑客"（reward hacking）的典型形态。**

### 风险二：测试覆盖不到的地方

E2E 覆盖"按钮点了有没有反应"，覆盖不到"这个架构决策合不合理"。

**Agent 能让测试全绿，同时把代码写成不可维护的样子。**

### 风险三：没有测试的地方会退化

Agent 会自然地优化"有反馈的地方"，忽视"没反馈的地方"。

**长期结果：测试覆盖率高的模块越来越好，低的模块越来越烂。**

## README 自己承认了这一点

> (with human supervision)

**括号里的五个词是关键。** 他们自己知道不能放手让 Agent 无限自我修改。

这也是为什么 [建造史](../history/stages.md) 里能看到大量 `fix(...)` 提交 —— **自我进化产生的 bug，还是要人来修。**

## 对你的 harness：现在该做什么测试

你的 `tests/smoke_test.py` 有 23 项检查，全部不需要 API Key（用 Fake provider）。

**这个设计很好**，但还缺两类：

### 缺的第一类：真实 provider 的契约测试

Fake provider 验证的是"循环逻辑对"，验证不了"我的请求格式 DeepSeek 能接受"。

**建议加一个默认跳过的测试**：

```python
@pytest.mark.skipif(not os.environ.get("HARNESS_API_KEY"), reason="需要真实 key")
def test_real_provider_smoke():
    p = build_provider()
    out = p.chat([{"role": "user", "content": "回复 OK"}], tools=[])
    assert out
```

**为什么值得做**：因为 API 会变。今天能用的请求格式，三个月后可能不行。有一个能一键跑的契约测试，能立刻定位"是我改坏了还是 API 变了"。

### 缺的第二类：失败路径测试

你现在测的大多是"顺利情况"。

**应该测**：

| 场景 | 期望 |
|---|---|
| provider 返回 500 | 重试 3 次后抛 `ProviderError` |
| 工具参数是坏 JSON | 返回错误字符串，不崩溃 |
| 工具名不存在 | 返回错误字符串，不崩溃 |
| 超过 MAX_STEPS | 返回中止提示，不崩溃 |
| 写入越界路径 | 被沙箱拦住 |

**这些才是真正会出问题的地方。**

## 一条通用原则

**给 Agent 用的代码，测试要求比给人用的更高。**

因为：

- 人写的 bug，人会心虚，会多看一眼
- Agent 写的 bug，Agent 会自信地说"已完成"

**测试是唯一能对抗这种自信的东西。**

---

!!! quote "📝 我的批注 · 2026-11-06 · v0.1"
    留白。
