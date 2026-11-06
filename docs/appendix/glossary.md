# 术语表

按拼音排序。每个词给出**一句话定义**和**在哪一章详细讲**。

## A

**Agent** — 能自己决定下一步做什么的程序，而不是按固定流程执行。全书主题。

**AgentSession** — 一个对话的全部状态容器，不只是聊天记录。[会话与状态](../core/session.md)

**AGPL-3.0** — ORG2 的许可证。改造成网络服务必须开源。[建造史](../history/stages.md)

## C

**crate** — Rust 的代码包单位，类似 Python 的包、Node 的 npm 包。

**compaction** — 上下文压缩。把长对话总结成短的，防止撞上窗口上限。[记忆系统](../intelligence/memory.md)

## D

**delta** — 增量，一小块流式文本碎片。[事件流](../core/event-stream.md)

**debounce（防抖）** — 变化连续发生时，等它停下来才触发一次。[自动化触发](../integrations/automation.md)

## H

**harness** — 内核/测试架。驱动模型循环的那层代码。[Agent 内核](../core/agent-kernel.md)

**Hook** — 钩子。在流程固定位置插入自定义逻辑。[Skills · MCP · Hooks](../intelligence/skills-mcp-hooks.md)

## I

**IPC** — 进程间通信。这里指前端和后端说话的方式。

**IoC（控制反转）** — 把"用哪个实现"的决定权交给调用方。这里用函数指针实现。[事件流](../core/event-stream.md)

**幂等（idempotent）** — 执行一次和执行多次结果相同。[持久化](../data/persistence.md)

## L

**LLM round-trip（往返）** — 发一次请求收一次响应。一个回合含多次往返。[一条消息的旅程](../core/message-journey.md)

## M

**MCP** — Model Context Protocol，让 Agent 接入外部服务的协议。[Skills · MCP · Hooks](../intelligence/skills-mcp-hooks.md)

**mpsc** — 多生产者单消费者通道。入站消息用它，容量 256。[事件流](../core/event-stream.md)

## P

**provider** — 模型服务的接入驱动。[Provider 层](../core/providers.md)

**broadcast** — 单生产者多消费者通道。出站事件用它，容量 1000。[事件流](../core/event-stream.md)

## S

**sidecar** — 伴随进程。主程序旁边运行的辅助程序（如 `agent-browser`）。

**Skill** — 一段带 frontmatter 的 Markdown 提示词，用作可插拔能力。[Skills · MCP · Hooks](../intelligence/skills-mcp-hooks.md)

**stop_reason** — 模型 API 返回的停止原因。`length` 表示被截断。[回合执行器](../core/turn-executor.md)

**system of record** — 系统之记录。唯一权威的数据源。[ORG2 是什么](../guide/what-is-org2.md)

## T

**tauri** — 用系统 WebView 跑前端的桌面框架。比 Electron 省内存。[前端与 Tauri](../data/frontend.md)

**thundering herd（惊群）** — 大量请求同时重试，把服务器二次打垮。用抖动解决。[回合执行器](../core/turn-executor.md)

**token** — 模型处理文本的最小单位。约等于 0.75 个英文单词 / 0.5 个汉字。

**turn（回合）** — 用户说一句话到模型彻底停下。含多次往返。[回合执行器](../core/turn-executor.md)

## U

**upsert** — 有则更新、无则插入。事件 id 撞车时会导致覆盖。[事件流](../core/event-stream.md)

## W

**WebSocket** — 双向长连接，后端可主动推数据。

**WebView** — 系统自带的浏览器内核。Tauri 复用它，Electron 内嵌一整个。

## 上下文窗口（context window）

模型一次能"看到"的最大 token 数。超了就报错或截断。不同模型不同大小。[Provider 层](../core/providers.md)

## 单一真相（single source of truth）

同一份事实只存一个权威副本。ORG2 最核心的设计理念。[事件流](../core/event-stream.md)

## 分支覆盖

| 缩写 | 全称 |
|---|---|
| E2E | End-to-End，端到端 |
| IoC | Inversion of Control |
| MCP | Model Context Protocol |
| SDE | Software Development Engineer |
| SoR | System of Record |
| TUI | Terminal User Interface |
| UI | User Interface |

---

!!! quote "📝 我的批注 · 2026-11-06 · v0.1"
    遇到不懂的词记在这里，我后续补进表里。
