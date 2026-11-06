# 前端与 Tauri

## Tauri 是什么

一句话：**用网页技术写界面，用 Rust 写后端，界面跑在系统自带的浏览器内核里。**

对比 Electron（VS Code、Slack 用的）：Electron 在每个应用里塞一整个 Chromium（约 100MB+）。Tauri 用系统已有的 WebView（Windows 上是 WebView2，macOS 上是 WKWebView）。

这就解释了初始 README 的原话：

> Built with Tauri and Rust, ORGII stays lightweight and RAM-friendly compared with Electron-based IDEs and heavier agentic tools.

## 两种通信方式

前端（TypeScript）和后端（Rust）之间有两种通路：

| 方式 | 方向 | 用于 |
|---|---|---|
| **Tauri command** | 前端调用后端，等结果 | 请求-响应（读文件、发消息） |
| **IPC Channel / WebSocket** | 后端主动推前端 | 流式事件 |

**这个分工很关键**：

- 用户点"读取文件" → command（要拿到结果）
- 模型正在吐字 → 推送（不需要前端请求，后端自己发）

**如果只有 command**，前端就得轮询"有新内容了吗"，那是灾难。

## 界面在架构里的位置

回到 [Agent 内核](../core/agent-kernel.md) 的层表：

```text
┌─────────────────────────────┐
│  TS 前端（src/）             │  ← 不属于 Rust 的五层
└──────────────┬──────────────┘
               │ Tauri command / IPC
┌──────────────▼──────────────┐
│  state/  （第 3 层）         │  ← Rust 里唯一懂前端的层
└─────────────────────────────┘
```

**关键约束**：`state/` 之下的任何层都不许 import `state/`。

那内核怎么往界面推事件？

答案是 [事件流](../core/event-stream.md) 讲的 **IoC 函数指针**：内核定义一个空插槽，启动时由 `app` 层把真正的广播函数塞进去。

```rust
static BROADCAST: OnceLock<BroadcastFn> = OnceLock::new();
pub fn register_broadcast(f: BroadcastFn) { let _ = BROADCAST.set(f); }
```

**这样内核在编译期完全不依赖界面。**

## 前端目录结构

`src/` 下的顶层：

```text
ActionSystem/   api/       app/        assets/
components/     config/    contexts/   engines/
features/       hooks/     i18n/       lib/
modules/        router/    scaffold/   services/
shells/         store/     styles/     test/
types/          util/      windows/
```

### `modules/` —— 七个大模块

| 模块 | 干什么 |
|---|---|
| `AppLogin` | 登录 |
| `HumanTools` | **人的**工具（和 AI 工具对应） |
| `MainApp` | 主应用 |
| `ProjectManager` | 项目管理 |
| `Session` | 会话界面 |
| `SetupWalkthrough` | 首次设置引导 |
| `WorkStation` | 工作台 |

**`HumanTools` 这个名字很有意思** —— 说明设计者明确区分"Agent 用的工具"和"人用的工具"。

### `features/` —— 十个功能块

`BenchmarkPanel`（跑分）、`CalendarView`（日历）、`CodeMirror`（编辑器）、`CodeViewer`（只读查看）、`GanttChart`（甘特图）、`KanbanBoard`（看板）、`SessionCreator`、`SessionSetup`、`TaskKanban`、`WorkItemCreator`。

**注意：这里一半的东西是项目管理软件的功能，不是编辑器功能。**

## 一个诚实的问题：为什么前端这么大

`modules/index.tsx` 有 **18,691 字节**（单文件）。

`WorkStation` 和 `MainApp` 是"七个超大文件"之一 —— 建造史里 2026-08-23 有一条提交：

```
refactor(modules): modularize seven oversized WorkStation and MainApp files
```

**这说明前端曾经（或仍然）有巨型文件问题。**

`ARCHITECTURE.md` 之外还有一条规矩（见 [五层架构规则速查](../appendix/architecture-rules.md)）：前端单文件 700 行上限，CI 检查改动文件。

**18,691 字节的 `index.tsx`** 大概在 500-700 行之间 —— 刚好在限制边缘。

## 一个值得学的做法：前端是 Agent 写的

初始 README 里有一句很特别的话：

> The frontend is written with our ORGII SDE Agent.

翻译：**这个前端是用他们自己的 Agent 写的。**

这不只是炫技。它意味着：

1. **前端代码必须对 Agent 友好** —— 结构清晰、命名明确、单文件不大
2. **他们把产品当自己的狗粮** —— 每天用自己造的 Agent 写自己的界面

**这解释了为什么会有"单文件 700 行上限"这条规矩** —— 那不是给人看的规范，是给 Agent 用的规范。

## 和你的关系

你现在没有前端。如果以后要加，最小的路是：

```text
CLI（已有）
  ↓ 加一个 web 渠道
一个极简 HTTP + SSE 服务
  ↓
一个单页 HTML
```

**关键设计**：不要改 `loop.py`。让它照旧通过 `bus` 发事件，你只是给 bus 加一个新的订阅者，把事件转成 SSE。

```python
bus.subscribe(lambda event, data: queue.put({"event": event, "data": data}))
```

**这样你的 CLI 和网页界面能同时工作** —— 这正是 ORG2 把 `tauri` 当成一个"渠道"的好处。

---

!!! quote "📝 我的批注 · 2026-11-06 · v0.1"
    留白。
