#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
ima 云端导出器：把 ima 个人知识库里指定文件夹的条目拉下来，写成 Markdown。

数据来源是 ima 的 MCP 端点（https://ima.qq.com/mcp，streamableHttp）。
工具名不硬编码 —— 先 initialize + tools/list，按关键词在服务端下发的
工具表里发现对应能力，再用官方 inputSchema 调用。

令牌获取方式（任选其一，优先级从高到低）:
    1. 环境变量 IMA_TOKEN
    2. 本目录下的 .ima_token 文件（纯文本，已在 .gitignore 中排除）

用法:
    python tools/ima_export.py --repo D:\ima-knowledge
    python tools/ima_export.py --repo D:\ima-knowledge --only 数据结构
"""

import argparse
import datetime
import json
import os
import re
import sys
import uuid

try:
    import urllib.request
    import urllib.error
except ImportError:  # pragma: no cover
    urllib = None

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

MCP_URL = "https://ima.qq.com/mcp"

# 目标：ima 个人知识库下的这两个文件夹
TARGET_FOLDERS = ["数据结构", "Github"]

# Windows 文件名非法字符
ILLEGAL = r'[\\/:*?"<>|\r\n\t]'


def safe_name(title: str, used: set) -> str:
    """把条目标题洗成合法的 Windows 文件名，并处理重名。"""
    name = re.sub(ILLEGAL, "_", (title or "untitled").strip())
    name = name.strip(" .")
    name = re.sub(r"\s+", " ", name)
    if not name:
        name = "untitled"
    if len(name) > 80:
        name = name[:80].rstrip(" .")
    base, n = name, 2
    while name.lower() in used:
        name = f"{base}-{n}"
        n += 1
    used.add(name.lower())
    return name


class McpClient:
    """极简 MCP streamableHttp 客户端（无第三方依赖）。"""

    def __init__(self, url: str, token: str):
        self.url = url
        self.token = token
        self.session_id = None
        self._id = 0

    def _post(self, payload: dict) -> dict:
        self._id += 1
        payload = dict(payload)
        payload.setdefault("jsonrpc", "2.0")
        payload.setdefault("id", self._id)

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id

        req = urllib.request.Request(
            self.url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            sid = resp.headers.get("Mcp-Session-Id")
            if sid:
                self.session_id = sid
            raw = resp.read().decode("utf-8", errors="replace")

        # 可能返回 SSE，也可能直接是 JSON
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                line = line[5:].strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"error": {"message": f"无法解析响应: {raw[:300]}"}}

    def initialize(self) -> bool:
        r = self._post(
            {
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "ima-knowledge-export", "version": "1.0"},
                },
            }
        )
        if "error" in r:
            raise RuntimeError(f"initialize 失败: {r['error']}")
        # 通知服务端初始化完成
        self._post({"method": "notifications/initialized", "params": {}})
        return True

    def list_tools(self) -> list:
        r = self._post({"method": "tools/list", "params": {}})
        if "error" in r:
            raise RuntimeError(f"tools/list 失败: {r['error']}")
        return r.get("result", {}).get("tools", [])

    def call_tool(self, name: str, arguments: dict) -> dict:
        r = self._post(
            {"method": "tools/call", "params": {"name": name, "arguments": arguments}}
        )
        if "error" in r:
            raise RuntimeError(f"{name} 调用失败: {r['error']}")
        return r.get("result", {})


def find_tool(tools: list, must: list, must_not: list = None) -> dict | None:
    """按关键词在工具表里发现能力（工具名以服务端下发为准）。"""
    must_not = must_not or []
    for t in tools:
        blob = (t.get("name", "") + " " + t.get("description", "")).lower()
        if all(m.lower() in blob for m in must) and not any(
            m.lower() in blob for m in must_not
        ):
            return t
    return None


def unwrap(result: dict):
    """MCP 工具结果是 content[] 列表，取出里面的文本/JSON。"""
    out = []
    for c in result.get("content", []):
        if c.get("type") == "text":
            out.append(c["text"])
    if not out:
        return result
    text = "\n".join(out)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def load_token(tools_dir: str) -> str | None:
    tok = os.environ.get("IMA_TOKEN")
    if tok:
        return tok.strip()
    p = os.path.join(tools_dir, ".ima_token")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            t = f.read().strip()
        if t:
            return t
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--only", nargs="*", default=None, help="只导出指定文件夹")
    ap.add_argument("--list-tools", action="store_true", help="只列出可用工具后退出")
    args = ap.parse_args()

    repo = os.path.abspath(args.repo)
    tools_dir = os.path.join(repo, "tools")
    meta_dir = os.path.join(repo, "_meta")
    os.makedirs(meta_dir, exist_ok=True)

    token = load_token(tools_dir)
    if not token:
        print()
        print("  [未配置] 没有找到 ima 授权令牌，无法访问云端知识库。")
        print()
        print("  两种配置方式（任选其一）：")
        print("    1) 设置环境变量 IMA_TOKEN")
        print(f"    2) 把令牌写入 {os.path.join(tools_dir, '.ima_token')}")
        print()
        print("  拿到令牌后重跑本脚本即可。")
        return 1

    folders = args.only or TARGET_FOLDERS

    print()
    print("  ima 云端导出")
    print("  " + "-" * 40)

    client = McpClient(MCP_URL, token)
    print("[1/4] 连接 ima MCP ...")
    try:
        client.initialize()
        tools = client.list_tools()
    except Exception as exc:
        print(f"  [错误] 连接失败: {exc}")
        print("  常见原因：令牌过期。请重新获取令牌后重试。")
        return 1

    print(f"  可用工具: {len(tools)} 个")
    if args.list_tools:
        for t in tools:
            print(f"      · {t.get('name')}: {t.get('description','')[:80]}")
        return 0

    # 能力发现：查库 / 列举条目 / 读正文
    t_kb = find_tool(tools, ["知识库"], ["内容", "正文", "media"])
    t_list = find_tool(tools, ["知识库"], []) or find_tool(tools, ["内容"], [])
    t_read = find_tool(tools, ["正文"]) or find_tool(tools, ["读取"])

    if not t_kb:
        print("  [错误] 服务端没有提供「查询知识库」能力。")
        print("  可用工具清单：")
        for t in tools:
            print(f"      · {t.get('name')}")
        return 1

    print("[2/4] 定位个人知识库 ...")
    kb_data = unwrap(client.call_tool(t_kb["name"], {}))
    print(f"  返回类型: {type(kb_data).__name__}")

    # 到这里为止是确定能跑通的部分；后续步骤依赖服务端真实结构，
    # 首次运行时按实际返回的字段名补齐。
    print()
    print("  [提示] 已连通 ima 服务端。")
    print("  下一步需要根据服务端真实返回结构完成条目遍历。")
    print(f"  目标文件夹: {', '.join(folders)}")
    print("  把上面 --list-tools 的输出发给我，我来把字段对齐。")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n  已取消。")
        sys.exit(130)
