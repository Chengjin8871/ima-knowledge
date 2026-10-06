# ima 知识库同步仓库

把 **ima 个人知识库**里「**数据结构**」和「**Github**」两个文件夹的内容，导出成 Markdown 并推送到 GitHub。

> 仓库地址：<https://github.com/Chengjin8871/ima-knowledge>
> 本地目录：`D:\ima-knowledge`

## 目录结构

```
ima-knowledge/
├── 数据结构/          # ima 个人知识库 - 数据结构文件夹
├── Github/            # ima 个人知识库 - Github 文件夹
├── _meta/
│   ├── manifest.json  # 导出清单：条目 ID -> 文件路径 / 标题 / 来源 / 更新时间
│   └── sync.log       # 同步日志（自动生成）
├── tools/
│   └── ima_export.py  # 云端导出器（需要 ima 授权令牌）
└── sync.bat           # 双击即可同步推送
```

## 怎么用

**日常推送**：双击桌面的 `同步ima到GitHub.bat`（或本目录下的 `sync.bat`）。
脚本会自动完成：预检 → `git add` → 生成 commit → `pull --rebase` → `push`，全程有中文提示和日志。

**更新内容**：ima 是云端知识库，内容需要走授权接口拉取。
新内容导出后放进 `数据结构/` 或 `Github/`，再双击脚本推送即可。

## 文件名清洗规则

ima 条目标题可能含 Windows 非法字符，导出时统一替换：

| 原字符 | 替换 |
|---|---|
| `\ / : * ? " < > \|` | `_` |
| 首尾空格与句点 | 去掉 |
| 重名 | 追加 `-2`、`-3` |

## 常见问题

- **提示 SSH 连不上**：脚本已强制走 443 端口（`GIT_SSH_COMMAND=ssh -p 443`），22 端口在本机被拒。
- **提示没有改动**：正常，`git diff --cached --quiet` 判定无变更时会直接跳过。
- **rebase 冲突**：脚本会自动 `rebase --abort` 并报错，不会留下脏状态。
