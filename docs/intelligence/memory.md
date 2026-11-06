# 记忆系统

## 根本问题：模型不记事

每一次 API 请求都是**无状态**的。模型不记得你上次说了什么 —— 它看到的全是你这次发过去的内容。

**所以"记忆"不是模型的能力，是宿主程序的责任。**

`intelligence/memory/` 下的五个子系统，就是 ORG2 对这责任的回答。

## 五个子系统

`ARCHITECTURE.md` 第 4.1 节原文列举：

| 子系统 | 职责 |
|---|---|
| `learnings/` | Agent 认为值得记住的长期事实 |
| `reflection/` | 回合前后的综合流水线，用来产出 learnings |
| `embeddings/` | 对 learnings 做向量检索（provider key 解析也在这里） |
| `consolidation/` | 定期整理陈旧的 learnings |
| `workspace_memory/` | 工作区范围的笔记 + 每个 story 的上下文检索 |

另外 `commands.rs` 是给界面用的 Tauri 命令层（「学习浏览器」UI 和调试/E2E HTTP 入口）。

## 为什么要五个，不是一个

这是本章的核心问题。逐个说明它们各自解决什么别人解决不了的问题。

### `learnings/` —— 存"事实"

最基础的一个：把"值得记住的东西"存下来。

**什么算值得记住？** 比如：

- "这个项目用 pnpm 而不是 npm"
- "测试命令是 `pytest -q`"
- "用户偏好中文回答"

### `reflection/` —— 决定"什么值得记"

**这是最容易被忽略但最关键的一环。**

如果没有它，`learnings/` 就得靠人手动往里塞，或者靠规则（"每 10 轮总结一次"）。

`reflection/` 做的是**在回合前后做一次综合判断**：这段对话里有没有产生值得长期保留的信息？

原文措辞：

> pre/post-turn synthesis pipeline that produces learnings

**注意 "pre/post-turn"（回合前后）** —— 它不是一个独立的定时任务，是**嵌在回合流程里的**。

### `embeddings/` —— 让"记得"能被找到

存了 1000 条事实，怎么在需要时找到相关的那 3 条？

**关键词匹配不行** —— 你问"怎么跑测试"，存的事实是"用 pytest 验证"，没有共同关键词。

所以用**向量检索**：把每条事实转成一个向量，查询时找向量最接近的。

**这也是为什么 `embeddings/` 的注释特别提到 "provider key resolution lives here"** —— 生成向量要调 embedding API，要 API Key。

**这是一个很实际的耦合点**：记忆系统依赖外部 API。如果没配 key，向量检索就不可用，得降级到别的方式。

### `consolidation/` —— 遗忘

**这个子系统最反直觉：它是用来"忘"的。**

原文：

> periodic compaction of stale learnings

翻译：**定期压缩陈旧的 learnings。**

为什么要忘？

1. **检索质量**：1000 条里混着 300 条过时的，检索准确率会掉
2. **成本**：每条 learnings 都要算 embedding
3. **冲突**：旧事实和新事实矛盾时，模型会困惑

**"遗忘"是记忆系统的高级功能，不是缺陷。** 一个只会记不会忘的系统，最终会变得和没有记忆一样难用。

### `workspace_memory/` —— 分作用域

原文：

> workspace-scoped notes + per-story context retrieval

**为什么要分作用域？**

因为"这个项目用 pnpm"这条事实，**只在这个项目里成立**。带到别的项目就是错误信息。

所以记忆必须分层：

| 层 | 例子 |
|---|---|
| 全局 | "用户偏好中文" |
| 工作区 | "这个仓库用 pnpm" |
| story / 任务 | "这次重构的目标是把 X 拆成 Y" |

**不分层的记忆系统，用得越久越有毒。**

## 一个整体的心智模型

```text
对话进行中
    │
    ├─ reflection 判断：这里有什么值得记？
    │        │
    │        └─► learnings 存下事实
    │                   │
    │                   └─► embeddings 建向量索引
    │
    ├─ 需要回忆时
    │        │
    │        └─► embeddings 检索 → 取回相关 learnings
    │
    └─ 定期
             │
             └─► consolidation 清理过时的
```

## 入口在哪

原文给了建议：

> If you're adding memory features, start in `learnings/types.rs` and `reflection/mod.rs`.

**先看数据类型，再看产生逻辑。** 这个建议适用于任何陌生子系统 —— 类型定义往往比实现更能说明设计意图。

## 和你的 harness 对照

| 能力 | 你的版本 | ORG2 |
|---|---|---|
| 跨会话记忆 | ❌ 无 | ✅ 五子系统 |
| 上下文压缩 | ❌ 无（会报错） | ✅ `compaction/` |
| 检索 | ❌ 无 | ✅ 向量 |
| 分层 | ❌ 无 | ✅ 全局/工作区/story |

**你最早该补的不是完整记忆系统，而是 `compaction/`。**

因为记忆是"加分项"，上下文压缩是"不加就崩"的必需项。

一个最小可行的压缩：

```python
def compact_if_needed(messages, limit=40):
    if len(messages) <= limit:
        return messages
    # 保留系统提示 + 前 2 条 + 最近 10 条，中间让模型总结
    keep_head, keep_tail = messages[:3], messages[-10:]
    middle = messages[3:-10]
    summary = provider.chat([
        {"role": "system", "content": "把下面的对话压缩成要点，保留所有关键决定和文件路径。"},
        {"role": "user", "content": render(middle)},
    ], tools=[])
    return keep_head + [{"role": "user", "content": f"[早期对话摘要]\n{summary}"}] + keep_tail
```

**三十行，解决你 README 里那个已知限制。**

---

!!! quote "📝 我的批注 · 2026-11-06 · v0.1"
    留白。
