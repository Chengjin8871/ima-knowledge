# ima 知识库同步仓库

把 **ima 个人知识库**下「**数据结构**」和「**GitHub**」两个知识库的内容导出成 Markdown，并推送到 GitHub。

> ⚠️ 结构更正（2026-10-07 实测）：这两个在 ima 里是**各自独立的知识库**，
> 不是「个人知识库」这个分类下某个库里的文件夹。个人知识库是分类名，下面挂着 10 个库。

- 远端仓库：<https://github.com/Chengjin8871/ima-knowledge>（**公开**，2026-10-07 起）
- 本地目录：`D:\ima-knowledge`
- 推送方式：SSH 走 443 端口（本机 22 端口被拒）

> ⚠️ 仓库是**公开**的：推进去的内容全世界可见。
> 别把带个人信息、密钥、未公开资料的条目放进 `数据结构/` 和 `Github/`。
> ima 授权令牌放在 `tools/.ima_token`，已在 `.gitignore` 中排除，不会入库。

## 目录结构

```
ima-knowledge/
├── Github/                          # ima「GitHub」知识库（4 篇 Trending 简报）
│   ├── GitHub Trending 简报 2026-10-02.md
│   ├── GitHub Trending 简报 2026-10-04.md
│   ├── GitHub Trending 简报 2026-10-05.md
│   └── GitHub Trending 简报 2026-10-06.md
├── 数据结构/                        # ima「数据结构」知识库
│   └── 第二节习题/
│       ├── 第 5 题/                # 4 种找公共结点的解法
│       │   ├── 长度对齐法.md
│       │   ├── 双扫描指针边扫边找公共结点.md
│       │   ├── 哈希集合法 C++语法.md
│       │   └── 暴力枚举法（不建议用）.md
│       └── 第 9 题/
│           └── 归并思想求两链表交集.md
├── _meta/
│   ├── manifest.json      # 导出清单：条目 ID -> 文件路径 / 标题 / 来源 / 大小
│   └── sync.log           # 同步日志（自动生成，UTF-8）
├── tools/
│   ├── sync.py            # 同步核心：预检 / add / commit / pull / push
│   └── ima_export.py      # 云端导出器（需要 ima 授权令牌）
└── sync.bat               # 双击入口
```

首次导出：2026-10-07，共 **9 条**（GitHub 4 + 数据结构 5）。
「第一节习题」为空文件夹；「第二节习题」下第 1/2/3/4/6/7/8/10 题也均为空，只有第 5、9 题有内容。

## 日常使用

**推送**：双击桌面的 `同步ima到GitHub.bat`，或直接双击 `D:\ima-knowledge\sync.bat`。

脚本依次做：环境预检 → `git add -A` → 统计变更 → `git commit` → `pull --rebase` → `git push`，
失败会等 10 秒自动重试一次，全程写日志到 `_meta/sync.log`。

退出码：`0` 成功 / `1` 失败 / `2` 无变更（已最新）。

**三种情况都会正确处理：**

| 情况 | 行为 |
|---|---|
| 有新文件/改动 | 提交并推送 |
| 改动已 commit 但未 push | 跳过提交，直接补推送 |
| 完全无变化 | 提示「无需推送」并正常退出 |

**更新内容**：ima 是云端知识库，内容要经授权接口拉取（见下）。新内容落到
`数据结构/` 或 `Github/` 后，双击脚本即可推送。

## 云端导出（ima_export.py）

```bat
python tools\ima_export.py --repo D:\ima-knowledge            :: 导出
python tools\ima_export.py --repo D:\ima-knowledge --list-tools  :: 看可用工具
```

需要 ima 授权令牌，二选一：

1. 设置环境变量 `IMA_TOKEN`
2. 把令牌写入 `tools\.ima_token`（已在 `.gitignore` 中排除，不会入库）

工具名**不硬编码**：脚本先 `initialize` + `tools/list`，按关键词从服务端下发的工具表里
发现「查库 / 列条目 / 读正文」能力，再按官方 `inputSchema` 调用。

## 两个已踩过的坑（改代码前先看）

**1. 批处理文件不能写中文。**
cmd.exe 用 ANSI 代码页（本机 936/GBK）解析 `.bat`，但控制台跑在 65001/UTF-8，两者不一致 ——
UTF-8 的中文批文件会被解析成乱码并整片崩溃（2026-10-06 实测复现，`D:\dsa\sync.bat` 里也记着同样的事故）。
所以 `sync.bat` **必须保持纯 ASCII**，所有中文输出交给 `tools/sync.py` 打印。

**2. 只检测工作区改动会漏掉已提交未推送的 commit。**
最初版本用 `git diff --cached --quiet` 判定，结果本地有 2 个提交没推上去却报「无改动」。
现在会额外用 `git rev-list --count @{u}..HEAD` 检查待推送提交。

## 文件名清洗规则

ima 条目标题可能含 Windows 非法字符，导出时统一处理：

| 原字符 | 替换 |
|---|---|
| `\ / : * ? " < > \|` 及换行制表符 | `_` |
| 首尾空格与句点 | 去掉 |
| 连续空白 | 压成单个空格 |
| 超过 80 字符 | 截断 |
| 重名 | 追加 `-2`、`-3` |
