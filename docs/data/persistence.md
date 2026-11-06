# 持久化

## 一个反直觉的设计决定

先说这一章最值得注意的东西。

`ARCHITECTURE.md` 第 4.6 节原文：

> **Schema lives in `foundation::persistence::session_snapshots::ensure_tables`.** Migrations are intentionally lightweight — there is no `migrations/` directory and no version table. A new column is added by appending an `ALTER TABLE ... ADD COLUMN ...` line via the local `try_migrate` helper, which tolerates `"duplicate column name"` so re-runs are idempotent.

翻译：

- **表结构定义在一个函数里**（`ensure_tables`）
- **迁移是故意做得轻量的**：没有 `migrations/` 目录，没有版本表
- 加一列的做法：往 `ensure_tables` 里追加一行 `ALTER TABLE ... ADD COLUMN ...`
- 由 `try_migrate` 辅助函数执行，它**容忍 "duplicate column name" 错误**，从而让重复执行是幂等的

**这和主流做法完全相反。**

## 主流做法 vs 这个做法

| | 主流（Django / Rails / Flyway） | ORG2 |
|---|---|---|
| 迁移文件 | 每个改动一个文件，编号 | 无 |
| 版本表 | 有，记录执行到第几号 | 无 |
| 执行逻辑 | 只执行未执行过的 | 每次全部执行，报错就吞 |
| 回滚 | 有 down 迁移 | `try_drop_col` |

## 为什么这样也行

关键在于**幂等（idempotent）**。

`ALTER TABLE ... ADD COLUMN x` 如果 x 已经存在，SQLite 会报 `duplicate column name`。`try_migrate` 捕获这个特定错误并忽略。

于是：

```text
第 1 次启动：执行 50 条 ALTER，全部成功
第 2 次启动：执行 50 条 ALTER，50 条都报重复，全部忽略
第 3 次启动：同上
```

**结果：无论启动多少次，表结构最终都是最新的。**

### 这个方案的优点

1. **零心智负担**。加一列就是加一行，不用想"我该编号几"
2. **不可能"漏执行"**。每次启动全跑一遍，不存在"某个环境卡在旧版本"
3. **对单人 / 小团队极度友好**。没有迁移顺序冲突（两个人同时加迁移文件，编号撞了）
4. **代码即文档**。`ensure_tables` 就是当前 schema 的完整定义

### 这个方案的代价

必须诚实地说清楚：

| 代价 | 说明 |
|---|---|
| **启动会变慢** | 每次启动要执行几十条会报错的 ALTER。表多了可能明显 |
| **不能删列** | 删列需要 `try_drop_col`，且 SQLite 对 DROP COLUMN 支持有限（老版本不支持） |
| **不能改类型** | 只能加，不能改 |
| **不能数据迁移** | "把 A 列的值搬到 B 列"这类操作没有地方放 |
| **报错被吞** | 如果某次 ALTER 因为别的原因失败（不是重复列），会被一起吞掉 |

!!! warning "⚙️ 这是推断，不是源码原文"
    最后一条（"别的原因失败也会被吞"）取决于 `try_migrate` 的实现 —— 它是只匹配 `"duplicate column name"` 这一个错误字符串，还是捕获所有错误。我只读到文档描述"tolerates duplicate column name"，没看到实现。

    **如果只匹配特定字符串，这个方案是安全的；如果捕获全部，就有掩盖真实错误的风险。**

## 对你的 harness 意味着什么

你现在用 JSONL 存会话（`sessions/*.jsonl`，每行 `{"ts","type","payload"}`）。

**这个方案在这个阶段是完全正确的**：

- 零依赖
- 可读
- 可 diff
- 追加写，不会损坏已有数据

**什么时候该换 SQLite？**

出现下面任一情况时：

- 需要按条件查询（"找出所有包含某个文件路径的会话"）
- 会话数超过几百个，`load()` 变慢
- 需要并发写
- 需要原子性（多条记录要么都写成功要么都不写）

**在那之前，JSONL 更好。** 不要为了"看起来专业"提前引入数据库。

## 存储的两部分

`ARCHITECTURE.md`：

> SQLite (via `rusqlite`) plus a file-system store for blobs.

两部分：

| 存储 | 放什么 |
|---|---|
| **SQLite** | 结构化数据 —— 会话、消息行、事件 |
| **文件系统** | 大块二进制 —— 截图、附件、大的工具输出 |

**为什么分开？**

因为 SQLite 里存几 MB 的二进制会让整个库膨胀，备份变慢，读取也慢。而文件系统天生适合存大块数据。

**这个分法和 `payload_refs`、`tool_result_storage`、`InboundMessage.media` 是同一个原则**：

> **结构化的东西进库，大块的东西进文件系统，中间用引用连起来。**

这个原则在整本书里出现了至少四次。看到它反复出现，说明它是这个系统的底层直觉。

## SQL 的组织方式

原文：

> The `db_helpers/` directory contains pure SQL builders; `crud/` directories under each domain (e.g. `core::session::persistence::crud`) compose them.

两层：

| 层 | 职责 |
|---|---|
| `db_helpers/` | **纯 SQL 构造器** |
| 各领域的 `crud/` | 组合这些构造器 |

**"pure SQL builders"（纯 SQL 构造器）** 的意思大概是：这些函数只拼 SQL 字符串和参数，不执行。执行由别处负责。

**好处**：SQL 可以被单独测试，不需要真的连数据库。

这也解释了为什么 `core::session::persistence::crud` 在 `core/` 层而不是 `foundation/` 层 —— **基础能力在 foundation，业务语义在 core。**

## 相关 crate

| crate | 职责 |
|---|---|
| `database` | 数据库核心 |
| `session-persistence` | 会话持久化 |
| `settings` | 配置存储 |
| `app-paths` | 数据放哪个目录（跨平台） |

**`app-paths` 值得注意**：Windows 上的 AppData、macOS 上的 `~/Library/Application Support`、Linux 上的 `~/.config` —— 每个平台规矩不同。这个 crate 把它们统一了。

**如果你要发布自己的 harness，这个是你迟早要处理的**：现在你的 `sessions/` 就在项目目录里，一提交就进 git 了。

---

!!! quote "📝 我的批注 · 2026-11-06 · v0.1"
    留白。
