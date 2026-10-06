#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
ima 云端导出器：把 ima 知识库里的条目拉下来写成 Markdown，并生成导出清单。

调用链路（2026-10-07 在真实账号上手工跑通一遍，工具名与参数均为实测值）：
    get_knowledge_base_list  ->  拿到 knowledge_base_id
    get_knowledge_list       ->  递归展开文件夹，拿到 media_id
    fetch_media_content      ->  取正文

令牌获取（优先级从高到低）：
    1. 环境变量 IMA_TOKEN
    2. 本目录下的 .ima_token 文件（已在 .gitignore 中排除，不会入库）

用法:
    python tools/ima_export.py --repo D:\ima-knowledge
    python tools/ima_export.py --repo D:\ima-knowledge --only 数据结构
    python tools/ima_export.py --repo D:\ima-knowledge --list-tools
"""

import argparse
import datetime
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

MCP_URL = "https://ima.qq.com/mcp"

# ima 里的知识库名 -> 本仓库里的目录名
# 注意：这两个在 ima 里是【各自独立的知识库】，不是某个库下面的文件夹。
TARGET_KBS = {
    "GitHub": "Github",
    "数据结构": "数据结构",
}

# media_type == 99 表示文件夹
MEDIA_TYPE_FOLDER = 99

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
    """极简 MCP streamableHttp 客户端（只用标准库）。"""

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

    def initialize(self):
        self._post(
            {
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "ima-knowledge-export", "version": "1.0"},
                },
            }
        )
        self._post({"method": "notifications/initialized", "params": {}})

    def list_tools(self) -> list:
        r = self._post({"method": "tools/list", "params": {}})
        return r.get("result", {}).get("tools", [])

    def call(self, name: str, arguments: dict) -> dict:
        """调工具并解包 content[]。"""
        r = self._post(
            {"method": "tools/call", "params": {"name": name, "arguments": arguments}}
        )
        if "error" in r:
            raise RuntimeError(f"{name} 失败: {r['error']}")
        res = r.get("result", {})
        texts = [c["text"] for c in res.get("content", []) if c.get("type") == "text"]
        blob = "\n".join(texts)
        try:
            return json.loads(blob)
        except json.JSONDecodeError:
            return {"raw": blob}


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


def walk_folder(client, kb_id: str, folder_id: str, prefix: str, out: list) -> None:
    """递归展开知识库（或文件夹）下的所有条目。"""
    args = {
        "knowledge_base_id": kb_id,
        "limit": 50,
        "cursor": "",
        "sort_type": "UPDATE_TS_DESC_SORT_TYPE",
    }
    if folder_id:
        args["folder_id"] = folder_id

    data = client.call("get_knowledge_list", args)
    for item in data.get("knowledge_list", []):
        mt = item.get("media_type")
        title = item.get("title", "")
        if mt == MEDIA_TYPE_FOLDER or item.get("folder_info"):
            fid = (item.get("folder_info") or {}).get("folder_id") or item.get("media_id")
            walk_folder(client, kb_id, fid, f"{prefix}/{title}", out)
        else:
            out.append({"item": item, "folder": prefix})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--only", nargs="*", default=None, help="只导出指定知识库（ima 里的库名）")
    ap.add_argument("--list-tools", action="store_true")
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
        print("  仓库里现有的 9 个条目是 2026-10-07 经 WorkBuddy 的 ima 连接器导出的；")
        print("  日常新增内容后直接双击 sync.bat 推送即可，不必每次重跑本脚本。")
        return 1

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
        print("  通常是令牌过期，重新获取后重试。")
        return 1

    if args.list_tools:
        for t in tools:
            print(f"      · {t.get('name')}: {t.get('description','')[:70]}")
        return 0

    print(f"  可用工具: {len(tools)} 个")

    print("[2/4] 定位知识库 ...")
    kbs = client.call(
        "get_knowledge_base_list",
        {"params": [{"limit": 50, "type": "KBT_MINE_KB"}]},
    ).get("knowledge_base_list", [])

    want = args.only or list(TARGET_KBS)
    targets = [kb for kb in kbs if kb.get("basic_info", {}).get("name") in want]
    if not targets:
        print(f"  [错误] 没找到目标知识库 {want}。")
        print("  账号下可见的库：")
        for kb in kbs:
            print(f"      · {kb.get('basic_info', {}).get('name')}")
        return 1
    print("  命中库: " + ", ".join(kb["basic_info"]["name"] for kb in targets))

    print("[3/4] 递归展开条目 ...")
    all_items = []
    for kb in targets:
        kb_id = kb["id"]
        kb_name = kb["basic_info"]["name"]
        out = []
        walk_folder(client, kb_id, "", "", out)
        for o in out:
            o["kb"] = kb_name
        all_items.extend(out)
        print(f"      {kb_name}: {len(out)} 条")

    print(f"[4/4] 拉取正文并写盘（共 {len(all_items)} 条）...")
    used: dict[str, set] = {}
    manifest_items = []
    for o in all_items:
        item = o["item"]
        kb_name = o["kb"]
        rel_dir = os.path.join(TARGET_KBS.get(kb_name, kb_name), o["folder"].lstrip("/"))
        os.makedirs(os.path.join(repo, rel_dir), exist_ok=True)
        used.setdefault(rel_dir, set())

        fname = safe_name(item.get("title", ""), used[rel_dir])
        if not fname.lower().endswith(".md"):
            fname += ".md"
        rel_path = os.path.join(rel_dir, fname).replace("\\", "/")

        try:
            data = client.call("fetch_media_content", {"media_id": item["media_id"]})
            content = data.get("content", data.get("raw", ""))
        except Exception as exc:
            print(f"      [跳过] {item.get('title')}: {exc}")
            continue

        with open(os.path.join(repo, rel_path), "w", encoding="utf-8") as f:
            f.write(content.rstrip() + "\n")
        print(f"      OK  {rel_path}")

        manifest_items.append(
            {
                "media_id": item["media_id"],
                "title": item.get("title", ""),
                "kb": kb_name,
                "folder": o["folder"],
                "type": (item.get("media_type_info") or {}).get("name", ""),
                "size": item.get("file_size", ""),
                "path": rel_path,
            }
        )
        time.sleep(0.3)

    manifest = {
        "exported_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "ima 个人知识库（ima.qq.com）",
        "total_items": len(manifest_items),
        "items": manifest_items,
    }
    with open(os.path.join(meta_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print()
    print(f"  [完成] 导出 {len(manifest_items)} 条，清单已写入 _meta\\manifest.json")
    print("  接下来双击 sync.bat 推送到 GitHub。")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n  已取消。")
        sys.exit(130)
