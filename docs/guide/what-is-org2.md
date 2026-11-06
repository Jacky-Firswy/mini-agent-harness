# ORG2 到底是个什么系统

## 一句话

**ORG2 是一个本地运行的 AI 编程 Agent 平台：内核用 Rust 写，界面用 Tauri 桌面壳包着，你的 API Key 放在自己机器上。**

这是它的官网简介（`org2.dev`）和 GitHub 仓库描述拼出来的：

> System of record for how agents build software: Built-in rust harness & 20+ CLIs.

翻成中文：**记录 Agent 如何构建软件的"系统之记录"，自带 Rust 内核和 20 多个命令行工具。**

这句话里有两个词值得注意：**harness**（内核/测试架）和 **system of record**（系统之记录）。后面会展开。

## 名字的来历

这件事先弄清楚，否则你会在各种仓库地址里迷路。

| 你看到的名字 | 是什么 |
|---|---|
| ORGII | 它最初的名字。旧仓库地址 `github.com/YORG-AI/ORGII` |
| ORG2 | 现在的名字。旧地址会**自动重定向**到 `github.com/org2AI/ORG2` |
| YORG-AI | 旧的组织名 |
| org2AI | 现在的组织名 |

所以 **ORGII 和 ORG2 是同一个项目的两个阶段**，不是两个项目。你在网上看到的 "ORGII" 资料，讲的就是它的早期形态。

!!! warning "⚙️ 这是推断，不是源码原文"
    仓库改名的具体时间点我没有精确查到。我能确认的是：初始提交里的 README 自称 "ORGII"，并且指向 `github.com/YORG-AI/ORGII/releases`；而现在这个地址会重定向到 `org2AI/ORG2`。

## 一个系统，四种身份

这是理解 ORG2 最关键的一段。它同时是四样东西，**而这四样东西会互相打架**。

### 身份一：Agent 内核（harness）

`src-tauri/crates/agent-core/` —— 一个**没有界面**的大脑。

它的全部工作可以概括成一句话：

> 把用户的话加上历史，发给模型；模型说要调工具，就执行工具；把结果再发回去；直到模型说"我说完了"。

这就是所谓的 **harness**（内核）。你那个 600 行的 `mini-agent-harness` 做的也是同一件事，只是厚度差了几百倍。

内核不该知道界面上有什么按钮，也不该知道消息是从 Telegram 来的还是从桌面窗口来的。**这种"什么都不知道"是刻意设计的。**

### 身份二：IDE（桌面应用）

`src/` 目录 —— 一个完整的编辑器前端。

有代码编辑器（`CodeMirror`）、文件树、终端、会话标签页、看板（`KanbanBoard`）、甘特图（`GanttChart`）、日历（`CalendarView`）。

它和 VS Code / Cursor 是同一类东西：**本地优先**（local-first），代码不上传云端。

为什么用 Tauri 而不是 Electron？初始 README 的原话是：

> Built with Tauri and Rust, ORGII stays lightweight and RAM-friendly compared with Electron-based IDEs and heavier agentic tools.

翻译：Tauri 比 Electron 更轻、更省内存。因为 Tauri 用的是系统自带的 WebView，而 Electron 要在每个应用里塞一整个 Chromium。

### 身份三：编排平台（Agentic Orgs）

README 里有个说法叫 **Agentic Orgs** —— "Agent 组织"。

意思是：不是一个 Agent 干活，而是**一群 Agent 分工协作**，像一个虚拟团队。有负责人、有任务分配、有并行执行、有汇总。

代码里对应的是 `tools/impls/orchestration/`（编排类工具）、`core/coordination/`（协调）、`project-management` crate（项目管理）。

### 身份四：记录系统（system of record）

这是它后来的定位，也是最容易忽略的一个。

"System of record" 是企业管理软件里的术语，指**唯一权威的数据源**。比如 HR 系统是"员工信息的 system of record"。

ORG2 把它用在 Agent 上：**每一次 AI 写代码的会话，都被完整记录、可回放、可追溯。**

为什么需要这个？它的中文 README 给了两个理由：

> 一是"周一写的代码，到周五就成了遗留代码"
> 二是"任何上线的代码行都能追溯到写下它的那次会话"

第一句是说：**在 Agent 的速度下，代码的"保质期"被压缩到了几天。** 人脑已经跟不上"这行代码是谁为什么加的"这种追溯了，只能靠系统记。

## 四者为什么会打架

这是全书会反复出现的一条暗线。

| 冲突 | 具体表现 |
|---|---|
| 内核 vs 界面 | 内核要"什么都不知道"，界面要"立刻显示每个字"。于是需要一层事件流把两者隔开 |
| 单 Agent vs 多 Agent | 单会话状态很好管；一旦 Agent 之间要协作，状态就变成分布式问题 |
| 功能 vs 可追溯 | 每加一个功能，就多一类要记录的事件；记录越全，写入压力越大 |
| 本地 vs 协作 | 本地优先意味着数据在你机器上；但"团队"就意味着要同步 |

书里后面每一章，本质上都在讲它**怎么在这些冲突里选边**。

## 规模：几个数字建立体感

| 指标 | 数值 | 出处 |
|---|---|---|
| 首次提交导入代码量 | 约 130 万行 | 初始提交页面 |
| 提交总数 | 7,273 | GitHub 仓库页 |
| Rust crate 数（内核侧） | 43 | 初始提交 `src-tauri/crates/` 目录 |
| 时间跨度 | 2026-06-01 → 2026-10-11 | 提交历史 |
| Star 数 | 2.6k | 仓库页 |
| 许可证 | AGPL-3.0 | `LICENSE` |

!!! warning "⚠️ 关于 130 万行"
    这个数字来自 GitHub 初始提交页面的统计，我没有逐字节核对。"约"字是必要的。

## 43 个 crate 的全景图

这是 `src-tauri/crates/` 下的完整清单（初始提交，`truncated: false` 即无遗漏）。先扫一眼有个印象，后面章节会逐个碰到。

按能力归类：

| 能力域 | crate |
|---|---|
| **Agent 内核** | `agent-core`、`agent-cli` |
| **持久化** | `database`、`session-persistence`、`settings`、`app-paths` |
| **编辑与开发** | `file-ops`、`git`、`git-api`、`lsp`、`terminal`、`search`、`advanced-search`、`api-search`、`ui-indexer` |
| **外部世界** | `browser`、`container`、`integrations`、`transport`、`dev-record`、`inbox`、`system-services` |
| **数据库工具** | `db-browser`、`db-clients` |
| **Cursor 互操作** | `cursor-bridge`、`cursor-bridge-app` |
| **移动端** | `mobile-remote`、`orgii-mobile-relay`、`orgii-protocol` |
| **安全 / 协作** | `key-vault`、`project-management`、`shared-state`、`perf-utils` |
| **测试基建** | `e2e-test`、`test-runner`、`test-helpers` |
| **独立二进制** | `bin-gateway-chat-cli`、`bin-provider-key-check`、`bin-telegram-smoke` |

几个值得单独提的：

- **`key-vault`** —— 你的 API Key 存在哪、怎么加密。这对应 README 里 "bring-your-own keys"（自带密钥）的承诺。
- **`cursor-bridge`** —— 和 Cursor 编辑器的互操作。这说明它不打算完全取代别的工具，而是**接入**。
- **`e2e-test`** —— 端到端测试。这是它能"自我进化"的物理基础，详见 [测试与自进化](../data/testing.md)。
- **`ui-indexer`** —— 给界面用的索引器。说明前端不是简单调接口，有自己的一套数据组织。

## 整个仓库的目录形状

```text
src-tauri/               ← Rust 后端
  crates/                ← 43 个 crate
    agent-core/          ← 内核，全书重心
  src/                   ← Tauri 应用主体
  Cargo.toml             ← 35,955 字节，工作区定义
  tauri.conf.json        ← 桌面应用配置
  capabilities/          ← Tauri 权限声明
src/                     ← TypeScript 前端
  modules/               ← 7 个大模块
  features/              ← 10 个功能块
  components/  hooks/  store/  ...
mobile-pwa/              ← 手机端网页
packages/                ← 共享包
scripts/                 ← 构建脚本
tests/                   ← 测试
```

前端 `modules/` 的七个大模块，名字很能说明产品形态：

`AppLogin`（登录）、`HumanTools`（人的工具）、`MainApp`（主应用）、`ProjectManager`（项目管理）、`Session`（会话）、`SetupWalkthrough`（首次设置引导）、`WorkStation`（工作台）。

`features/` 里除了编辑器，还有 `BenchmarkPanel`（跑分面板）、`KanbanBoard` / `TaskKanban`（看板）、`GanttChart`（甘特图）、`CalendarView`（日历）、`SessionCreator` / `WorkItemCreator`（会话/工作项创建器）。

**这些不是"AI 编程工具"该有的东西，这是项目管理软件该有的东西。** 这个细节暗示了它在往哪个方向走。

## 它不是什么

避免误会，明确几条：

- **不是模型**。它不训练模型，只是调用别人的 API（Anthropic、OpenAI、DeepSeek、各种兼容接口）。
- **不是云服务**。核心跑在你自己电脑上，数据在你自己的 SQLite 里。
- **不是玩具**。43 个 crate、7,273 次提交、有签名公证的分发包、有 CI 有 E2E。
- **不是开源免费就能随便抄**。它是 AGPL-3.0 —— 你可以用、可以改，但**如果你把它改成网络服务提供给别人用，你必须也开源**。这条和你自己的 MIT 项目不一样，第 [建造史](../history/stages.md) 章会再提。

---

!!! quote "📝 我的批注 · 2026-11-06 · v0.1"
    留白。
