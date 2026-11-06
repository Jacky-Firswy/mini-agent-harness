# 一个最小可用的编程 Agent harness

这不是又一个 AI 编程工具，而是**拆开来看的**那种。

用 Python 标准库写成，**零第三方依赖**，一共 7 个文件、约 600 行。
读完之后你会真正明白：所谓"AI Agent 会自己干活"，到底是怎么做到的。

---

## 5 分钟跑起来

### 第 1 步：确认 Python

打开命令提示符（Win + R 输入 `cmd`），执行：

```
python --version
```

看到 `Python 3.9` 或更高就行。没有的话去 https://www.python.org/downloads/ 装一个，
安装时**记得勾选 Add Python to PATH**。

### 第 2 步：配置 API Key

```
copy .env.example .env
notepad .env
```

把 `HARNESS_API_KEY=` 等号后面填上你自己的 Key。默认对接 DeepSeek，
你也可以改成任何 OpenAI 兼容的服务（OpenAI、Moonshot、智谱、本地 Ollama）。

> `.env` 已被 `.gitignore` 排除，不会被提交到 GitHub。**永远不要把 Key 写进代码。**

### 第 3 步：自检并启动

```
python -m harness.main --check
python -m harness.main
```

`--check` 会告诉你 Key 有没有读到、工具注册了几个。然后就可以对话了：

```
你 › 看一下这个项目有哪些文件
你 › 帮我写一个 hello.py，打印当前时间
```

退出后它会告诉你会话存在哪，用 `--replay` 可以像录像一样重播：

```
python -m harness.main --sessions
python -m harness.main --replay 20261106-205512-a1b2
```

---

## 不用 API Key 也能验证

```
python tests/smoke_test.py
```

23 项检查，覆盖工具执行、路径沙箱、会话落盘、回合循环、死循环保护。
全部通过说明代码本身是好的，问题只可能在 Key 或网络上。

---

## 目录结构

```
harness/
  main.py       CLI 入口，把下面这些串起来        ← ORG2 的 state/
  loop.py       回合循环，Agent 的心脏            ← ORG2 的 core/turn_executor
  tools.py      工具抽象 + 4 个内置工具 + 沙箱    ← ORG2 的 core/tools
  provider.py   模型接入（OpenAI 兼容协议）        ← ORG2 的 core/providers
  session.py    会话状态 + JSONL 落盘 + 回放      ← ORG2 的 core/session
  bus.py        事件总线，引擎与界面的隔离层      ← ORG2 的 foundation/bus
  config.py     配置与系统提示                    ← ORG2 的 foundation/
tests/
  smoke_test.py 冒烟测试
docs/
  principle.md  原理深入讲解
  github-guide.md 从零学会 git、GitHub 和 PR
```

依赖方向**只能向下**：`main` 能用 `loop`，`loop` 不能 import `main`。
这条规矩守住了，代码就不会烂成一团。

---

## 四个核心概念

### 1. 工具（Tool）—— 让模型长出"手"

模型本身只会输出文字。它读不了你的文件，也跑不了命令。

那它怎么干活？靠**它输出一段 JSON**：

```json
{"name": "read_file", "arguments": {"path": "hello.py"}}
```

你这边收到这段 JSON，去真的执行，再把结果拼成一条消息喂回去。
模型就这样"看见"了文件内容。

在 `tools.py` 里，一个工具就是四样东西：

| 字段 | 谁看 | 作用 |
|---|---|---|
| `name` | 模型 | 工具叫什么 |
| `description` | 模型 | 什么时候该用它（**写得越清楚，模型用得越准**） |
| `parameters` | 模型 | 参数长什么样，JSON Schema 格式 |
| `run` | 只有你看 | 真正执行的 Python 函数 |

**关键**：`execute()` 无论内部怎么出错，都必须返回字符串而不是抛异常。
因为结果要喂给模型看 —— 模型看到"文件不存在"，才会自己换个路径重试。
你一抛异常，循环就断了，模型连补救的机会都没有。

### 2. 循环（Loop）—— Agent 的全部秘密

`loop.py` 里就是这二十来行：

```python
while 步数 < 上限:
    回复 = 模型.chat(历史消息, 工具列表)

    if 回复里没有 tool_calls:
        return 回复.content        # 模型认为干完了

    for 每个 tool_call:
        结果 = 执行工具(...)
        历史消息.append(工具结果)  # 关键：把结果塞回历史
    # 然后回到循环开头，再问模型一次
```

就这么朴素。所谓"Agent 会自己想办法"，本质是**它在多轮里反复观察工具结果**，
根据上一次的失败修正下一次的行动。没有魔法，只有循环。

**必须设步数上限**。模型偶尔会陷进"读文件→改文件→再读"的循环里，
没上限就是一夜之间烧掉你几百块。

### 3. 模型接入（Provider）—— 换模型不改代码

OpenAI 定了一套 `chat/completions` 的 HTTP 格式，DeepSeek、Moonshot、
智谱、Ollama 全都照着它做。所以只要实现一次，就能接一大片。

改模型只需要改 `.env` 里的两行，代码一行不动。这就是"驱动层"的价值。

> ORG2 支持 4 种驱动（Anthropic 原生、OpenAI 兼容、OpenAI Responses、ChatGPT Codex），
> 因为它们协议有硬性差异。我们只做最通用的那一种。

### 4. 会话（Session）—— 为什么轨迹能回放

`session.py` 做的事很简单：每一条消息，**进内存的同时追加到 JSONL 文件**。

```
{"ts": 1762..., "type": "message", "payload": {"role": "user", "content": "你好"}}
{"ts": 1762..., "type": "message", "payload": {"role": "assistant", "tool_calls": [...]}}
{"ts": 1762..., "type": "event",   "payload": {"event": "tool_call", "name": "read_file", ...}}
```

一行一个事件，只追加不修改。进程崩溃了，前面写好的也不会坏。
之后想回放、审计、算成本、追溯某行代码是谁改的 —— 数据都在，随便查。

ORG2 把这套东西换成了 SQLite + 文件快照，但出发点完全一样。

---

## 一次对话到底发生了什么

假设你说"帮我看下有哪些文件"：

```
你按下回车
  │
  ├─ main.py        把这句话加进会话
  │
  ├─ loop.py        第 1 次请求模型，附上 4 个工具的 schema
  │                 └─ provider.py → HTTPS → 模型
  │
  ├─ 模型返回：我要调 list_dir
  │
  ├─ tools.py       真的去列目录，拿到 "harness/ docs/ ..."
  │                 ├─ 沙箱检查：路径必须在项目内
  │                 └─ 结果转成字符串
  │
  ├─ session.py     把这个结果作为 role=tool 的消息存进历史 + 落盘
  │
  ├─ loop.py        第 2 次请求模型（这次历史里带着工具结果）
  │
  ├─ 模型返回：项目里有 harness 和 docs 两个目录……
  │
  └─ 没有 tool_calls 了 → 循环结束 → 打印给你
```

全程 `bus.publish()` 在发事件，终端上那些 `⚙ read_file` `↳ ...` 就是订阅了总线打印出来的。

---

## 与 ORG2 的对照

| 这里的文件 | ORG2 对应 | 差在哪 |
|---|---|---|
| `loop.py` | `core/turn_executor/` | ORG2 有流式解析、并行工具、断线重连、超长截断恢复、成本累计 |
| `tools.py` | `core/tools/` | ORG2 有工具策略（白名单/审批）、MCP 桥接、UI 元数据分离 |
| `provider.py` | `core/providers/` | ORG2 有 4 种协议 + 重试降级包装（`ReliableProvider`） |
| `session.py` | `core/session/` | ORG2 有 SQLite、上下文压缩（compaction）、会话恢复 |
| `bus.py` | `foundation/bus/` | ORG2 用 `tokio::broadcast`，类型化事件族 |
| `main.py` | `state/commands/` | ORG2 是 Tauri 命令，供 React 前端调用 |
| — | `intelligence/` | ORG2 有记忆、技能、MCP、hooks —— 这里还没有 |
| — | `integrations/` | ORG2 接了 Telegram/Discord/Slack 等外部渠道 |

**结论**：这 600 行是 ORG2 的骨架，不是它的全部。
但从"能跑"到"能生产"，每一步加的都是具体工程问题的具体解法，没有换赛道。

---

## 练习：从会读到会造

按难度递增，每做完一个你都会对某一层有真实的体感。

**① 加一个 `code_search` 工具（最简单）**

在 `tools.py` 里加一个函数，用 `Path.rglob()` 遍历文件、`in` 判断是否匹配。
然后在 `build_registry()` 里注册，下次启动模型就能用了。

注意两件事：跳过 `__pycache__` 和 `.git`；限制单个文件大小（超过 1MB 别读）。

**② 加流式输出（有点意思）**

现在模型是一次性返回整段。改成流式要在 SSE 里逐块解析，
并且 `tool_calls` 的 `arguments` 是分片到达的，得自己拼接完整。
看懂这个，你就理解了所有 AI 编程工具右上角那个"打字机效果"。

**③ 加验收门槛（触及产品本质）**

给 `run_shell` 加一个审批：执行 `del`、`rm`、`git push` 这类命令前，
先在终端问你 `允许吗？(y/n)`。用户拒绝就把拒绝理由作为工具结果返回给模型。

这就是 ORG2 里 `ResolvedToolPolicy` 在做的事，也是"可控 Agent"和"放养 Agent"的分水岭。

**④ 加记忆（进入下一层）**

把每次对话的结论摘要存成 markdown，下次启动时把相关的几条塞进系统提示。
你会立刻遇到新问题：怎么判断哪条相关？存太多把上下文撑爆了怎么办？
—— 这就是 ORG2 `intelligence::memory` 五个子系统要解决的。

---

## 已知限制

诚实列出，避免你误以为它很完整：

- **非流式**：回答一次性出现，没有逐字效果
- **工具串行**：模型要求调 3 个工具时逐个执行，ORG2 会并行
- **无上下文压缩**：聊得很长会撞上模型的上下文上限，然后报错
- **无记忆**：每次新会话都是白纸
- **JSONL 存储**：会话多了以后检索会很慢，该换 SQLite
- **Windows 友好但非最优**：编码、路径分隔符都做了处理，但没在其他平台验证过

这些不是缺陷，是**下一步该做的事**。每一项都对应文档里的一个知识点。

---

## 许可

MIT。随便用、随便改、随便发。
