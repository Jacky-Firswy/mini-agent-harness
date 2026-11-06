# 从零学会 Git、GitHub 和 PR

给完全没用过的人。读完你能独立把自己的项目发到 GitHub 上。

---

## 先分清三个东西

这三个词经常被混着说，其实是三件事：

| 东西 | 是什么 | 类比 |
|---|---|---|
| **Git** | 装在你电脑上的**版本控制软件** | 游戏存档系统 |
| **GitHub** | 一个**网站**，存放 Git 仓库 | 云存档 + 好友共享 |
| **PR** | GitHub 上的一个**功能**，用来请求合并代码 | 提交作业等老师批改 |

关键理解：**Git 不需要 GitHub 也能用**。
你在本地随时可以存档、回退、开分支，全程不联网。
GitHub 只是让"存档"能备份、能分享、能被别人看到。

---

## 四个必懂概念

### 仓库（Repository / repo）

一个被 Git 管理的文件夹。文件夹里会有个隐藏的 `.git` 目录，所有历史都藏在里面。

```
项目/            ← 这是你的工作目录，你看到的普通文件
  .git/          ← 这是存档本身，别手动改
  harness/
  README.md
```

### 提交（Commit）

**一次存档**。你把改动"打包"成一个提交，附上一句说明。

```
git add README.md          ← 挑选要存哪些改动
git commit -m "补充说明"    ← 存下来，附一句说明
```

一次提交 = 一个时间点 + 一份改动 + 一句说明。之后随时能回到任何一次提交。
**这就是为什么你改代码不会把东西改坏** —— 大不了退回去。

### 分支（Branch）

**平行世界**。默认叫 `main`。你可以从 `main` 开一个分支去试新想法，
搞砸了直接删掉，`main` 毫发无损。

```
git switch -c 试试新功能    ← 开一个新分支并切过去
# ... 在这里随便改 ...
git switch main            ← 切回来，你会发现改动"不见了"
```

改动没丢，只是还在那个分支上。这是 Git 最有用的能力。

### 远程（Remote）

你本地仓库在 GitHub 上的那一份拷贝。

```
git remote add origin https://github.com/你/仓库名.git
git push -u origin main    ← 把本地 main 推上去
git pull                   ← 把别人的改动拉下来
```

`origin` 只是"那个远程叫啥"的默认名字，没别的含义。

---

## PR 是什么（Pull Request）

**场景**：你在自己分支上做完了功能，想把它合进 `main`。

按老办法你得直接在 `main` 上改，容易出事。PR 的思路是：

> "我在 `feature-x` 分支做好了东西，请**拉取（pull）**我的改动，考虑合并。"

所以 PR 的本质是一个**带讨论区的合并请求**。它包含：

- 改了哪些文件的对比（diff，绿色是新增、红色是删除）
- 完整讨论记录（谁在什么时候说什么）
- 自动化检查结果（CI 跑测试有没有过）
- 最终"合并"或"关闭"的按钮

**为什么 PR 重要**：它把"偷偷改代码"变成了"公开讨论改动"。
现代软件团队几乎全部用 PR 工作流，开源项目更是如此 ——
你给别人的项目贡献代码，就是提 PR。

---

## 完整流程：从本地到第一次 PR

下面是一套可复制的标准动作。

### 准备（只做一次）

```
git config --global user.name  "你的名字"
git config --global user.email "你的邮箱"
```

这两行只是给提交签名用，不需要和 GitHub 账号一致，但建议一致。

### 第 1 步：让文件夹变成仓库（只做一次）

```
cd 你的项目文件夹
git init
```

会生成 `.git` 目录。如果这个文件夹已经是仓库，会提示 `Reinitialized`，无害。

### 第 2 步：先写好 .gitignore（**极其重要**）

这一步在**第一次提交之前**做。`.gitignore` 里列出的文件，Git 永远不看。

```
# 密钥
.env

# 运行产物
sessions/
__pycache__/
*.pyc

# 编辑器
.vscode/
.idea/
```

**为什么重要**：API Key 一旦被提交，它就永久留在了历史里。
即使你下一分钟删掉文件再提交一次，历史里的那份还在 ——
网上的爬虫几分钟内就能扫到并拿去盗刷。

如果已经误提交了，处理顺序是：
1. 立刻去服务商后台**作废这把 Key**（最重要，别想着抢救）
2. 重新生成一把
3. 再想办法清理历史（`git filter-repo` 或 GitHub 官方帮助文档）

**作废永远比清理优先。** 因为清理需要强推，而强推不保证所有副本都消失。

### 第 3 步：看看现在什么状态

```
git status
```

红色是"还没被追踪的文件"，绿色是"已暂存准备提交"。
养成每次提交前先看一眼的习惯 —— 能避免把不该提交的东西提交上去。

### 第 4 步：提交

```
git add .                              ← 把所有改动加入暂存区
git commit -m "初始提交：最小可用的 Agent harness"
```

`git add` 和 `commit` 分开是有道理的：你可以只 `add` 一部分文件，
让这次提交只包含一个完整的逻辑改动。

提交说明怎么写：
- 第一行简明扼要，说**做了什么**（不是"改了点东西"）
- 空一行，后面可以写**为什么**这么做
- 用祈使句："添加登录功能"比"添加了登录功能"更常见

### 第 5 步：在 GitHub 上建仓库

1. 打开 https://github.com/new
2. 填仓库名（比如 `mini-agent-harness`）
3. **不要**勾选 "Add a README"、"Add .gitignore"、"Choose a license"
   —— 你本地已经有了，勾了会造成冲突
4. 点 Create repository

### 第 6 步：连上远程并推送

GitHub 建完会显示几条命令，照抄即可：

```
git remote add origin https://github.com/你的用户名/仓库名.git
git branch -M main
git push -u origin main
```

- `-u` 表示"记住这次配对"，以后直接 `git push` 就行
- 推送时会弹出登录窗口，现代 Git 要求用 **Personal Access Token**（个人访问令牌）
  代替密码。去 https://github.com/settings/tokens 生成一个，勾选 `repo` 权限，
  **令牌只显示一次**，复制好存起来

推完刷新 GitHub 页面，代码就在上面了。

### 第 7 步：做一次 PR（即使只有你一个人）

一个人也能练 PR，而且强烈建议练一次：

```
git switch -c 加一个-code_search-工具     ← 开分支
# 改代码、测试、提交
git add .
git commit -m "添加 code_search 工具"
git push -u origin 加一个-code_search-工具
```

推完 GitHub 页面顶部会出现一个黄色横条：**"Compare & pull request"**，点它。

填三样东西：
- **标题**：一句话说清这个 PR 干什么
- **描述**：改了什么、为什么改、怎么验证的（截图/测试输出）
- **Reviewers**：自己练的话可以不填

然后点 **Create pull request**。你会看到：
- `Files changed` 标签页里是完整的 diff
- 可以给某一行留评论
- `Conversation` 标签页里能看到检查有没有过

最后点 **Merge pull request** 合并，再 `git switch main && git pull` 把合并结果拉回本地。

---

## 常用命令速查

```
# 看状态
git status                    现在什么情况
git log --oneline -10         最近 10 次提交
git diff                      还没暂存的改动内容

# 提交
git add 文件名                 暂存某个文件（. 表示全部）
git commit -m "说明"           提交

# 分支
git branch                    有哪些分支
git switch -c 新分支名         创建并切换
git switch main               切回 main
git branch -d 分支名           删除已合并的分支

# 远程
git remote -v                 看远程地址
git push                      推上去
git pull                      拉下来
git clone 地址                把别人的仓库整个复制到本地

# 反悔（常用且安全）
git restore 文件名             丢弃还没暂存的改动
git restore --staged 文件名    取消暂存（保留改动）
git log → git checkout 提交号   回到某个历史版本看
```

> `git reset --hard` 和 `git push --force` 是危险命令，
> 会**永久丢弃**改动。新手阶段先不要用。

---

## 五类报错与解法

**`fatal: not a git repository`**
你不在仓库目录里。`cd` 到有 `.git` 的文件夹。

**`Updates were rejected because the remote contains work that you do not have`**
远程有你本地没有的提交（通常是建仓库时勾选了 README）。
```
git pull --rebase origin main
git push
```

**`Please tell me who you are`**
没配置身份，跑最上面那两行 `git config`。

**`Authentication failed`**
GitHub 不接受账号密码了。去生成 Personal Access Token，用它当密码。

**中文文件名显示成 `\346\226\207\344\273\266`**
Windows 特有，执行一次：
```
git config --global core.quotepath false
```

---

## 提交什么、别提交什么

**该提交**：源代码、文档、配置模板（`.env.example`）、测试

**绝不提交**：`.env`、任何含 Key/token 的文件、`sessions/` 运行产物、
`__pycache__/`、`node_modules/`、几百 MB 的二进制文件

判断标准很简单：**别人 clone 下来能不能直接跑？**
需要但你没有的，就写进 README 让它自己配。

---

## 这个项目现在的状态

已经帮你做好了：

- ✅ `.gitignore` 已写，`.env` 和 `sessions/` 都在排除列表里
- ✅ `.env.example` 作为配置模板（不含真实 Key）
- ✅ README 说明了怎么跑

还没做（需要你确认）：

- ⬜ `git commit` 第一次提交
- ⬜ 创建 GitHub 仓库
- ⬜ 推送

这些都会改动到外部可见的状态，所以我在动手前会先问你。
