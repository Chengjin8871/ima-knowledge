#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
ima-knowledge 同步器：把本地导出的知识库内容推送到 GitHub。

由 sync.bat（纯 ASCII 启动器）调用。所有中文输出都由本文件负责，
避免 cmd.exe 用 GBK 解析 UTF-8 批处理导致的解析崩溃。

用法:
    python tools/sync.py --repo D:\ima-knowledge [--auto] [--dry-run]
"""

import argparse
import datetime
import json
import os
import subprocess
import sys

# 控制台代码页由 bat 切到 65001，这里保证 Python 也按 UTF-8 输出
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_NOCHANGE = 2

MANIFEST_NAME = "manifest.json"


def log_write(logfile: str, line: str) -> None:
    os.makedirs(os.path.dirname(logfile), exist_ok=True)
    with open(logfile, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_git(repo: str, args: list[str], env: dict | None = None) -> tuple[int, str]:
    cmd = ["git", "-C", repo] + args
    e = os.environ.copy()
    e["GIT_TERMINAL_PROMPT"] = "0"
    # 本机 22 端口被拒，强制 SSH 走 443
    e.setdefault("GIT_SSH_COMMAND", "ssh -p 443 -o StrictHostKeyChecking=accept-new")
    if env:
        e.update(env)
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=e)
    out = (p.stdout or "") + (p.stderr or "")
    return p.returncode, out.strip()


def check_manifest(repo: str) -> str | None:
    """如果导出清单存在，校验清单里的文件是否都真的落盘了。"""
    path = os.path.join(repo, "_meta", MANIFEST_NAME)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        return f"清单解析失败: {exc}"

    items = data.get("items", data if isinstance(data, list) else [])
    missing = []
    for it in items:
        rel = it.get("path") if isinstance(it, dict) else None
        if not rel:
            continue
        if not os.path.exists(os.path.join(repo, rel)):
            missing.append(rel)
    if missing:
        shown = "\n".join(f"       - {m}" for m in missing[:10])
        more = f"\n       ...还有 {len(missing) - 10} 个" if len(missing) > 10 else ""
        return f"清单里有 {len(missing)} 个文件尚未落盘:\n{shown}{more}"
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="仓库目录")
    ap.add_argument("--auto", action="store_true", help="静默模式（不暂停）")
    ap.add_argument("--dry-run", action="store_true", help="只检查不提交")
    # 兼容 Windows 风格的 /auto /dry-run（bat 传参用）
    norm = {
        "/auto": "--auto",
        "-auto": "--auto",
        "/dry-run": "--dry-run",
        "-dry-run": "--dry-run",
    }
    argv = [norm.get(a.lower(), a) for a in sys.argv[1:]]
    args = ap.parse_args(argv)

    repo = os.path.abspath(args.repo)
    meta = os.path.join(repo, "_meta")
    os.makedirs(meta, exist_ok=True)
    logfile = os.path.join(meta, "sync.log")
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    log_write(logfile, "=" * 60)
    log_write(logfile, f"[{stamp}] === sync start ===")

    print()
    print("  ima 知识库 → GitHub 同步")
    print("  " + "-" * 40)

    # ---------- [0/5] 预检 ----------
    print("[0/5] 环境检查...")
    rc, out = run_git(repo, ["--version"])
    if rc != 0:
        print("  [错误] 没有找到 git，请先安装 Git for Windows。")
        log_write(logfile, f"[{stamp}] FAILED - git not available")
        return EXIT_FAIL

    if not os.path.isdir(os.path.join(repo, ".git")):
        print(f"  [错误] {repo} 不是 git 仓库。")
        log_write(logfile, f"[{stamp}] FAILED - not a git repo")
        return EXIT_FAIL

    rc, origin = run_git(repo, ["remote", "get-url", "origin"])
    if rc != 0:
        print("  [错误] 仓库没有配置 origin 远程地址。")
        log_write(logfile, f"[{stamp}] FAILED - no origin remote")
        return EXIT_FAIL

    rc, branch = run_git(repo, ["rev-parse", "--abbrev-ref", "HEAD"])
    branch = branch or "main"
    print(f"  仓库: {repo}")
    print(f"  远程: {origin}")
    print(f"  分支: {branch}")

    warn = check_manifest(repo)
    if warn:
        print(f"  [提示] {warn}")

    # ---------- [1/5] add ----------
    print("[1/5] 暂存改动 (git add -A) ...")
    rc, out = run_git(repo, ["add", "-A"])
    if rc != 0:
        print(f"  [错误] git add 失败: {out}")
        log_write(logfile, f"[{stamp}] FAILED - git add: {out}")
        return EXIT_FAIL

    has_staged = True
    rc, _ = run_git(repo, ["diff", "--cached", "--quiet"])
    if rc == 0:
        has_staged = False

    # ---------- [2/5] 统计 ----------
    print("[2/5] 统计变更...")
    if not has_staged:
        # 工作区干净，但可能存在已 commit 尚未 push 的提交
        rc, ahead = run_git(repo, ["rev-list", "--count", "@{u}..HEAD"])
        n = int(ahead) if ahead.isdigit() else 0
        if n == 0:
            print()
            print("  没有检测到改动，无需推送。")
            log_write(logfile, f"[{stamp}] no changes - skipped")
            return EXIT_NOCHANGE
        print(f"  工作区无改动，但有 {n} 个本地提交尚未推送。")
        log_write(logfile, f"[{stamp}] {n} local commit(s) not pushed yet")
        files = []

    else:
        _, changed = run_git(repo, ["diff", "--cached", "--name-only"])
        files = [l for l in changed.splitlines() if l.strip()]
        print(f"  待提交文件: {len(files)} 个")
        for f in files[:10]:
            print(f"      · {f}")
        if len(files) > 10:
            print(f"      ...还有 {len(files) - 10} 个")
        log_write(logfile, f"[{stamp}] staged {len(files)} file(s)")

    if args.dry_run:
        print()
        print("  --dry-run：只检查，不提交。")
        return EXIT_OK

    # ---------- [3/5] commit ----------
    if has_staged:
        print("[3/5] 提交 (git commit) ...")
        msg = f"ima sync {stamp} ({len(files)} files)"
        rc, out = run_git(repo, ["commit", "-m", msg])
        if rc != 0:
            print(f"  [错误] git commit 失败: {out}")
            log_write(logfile, f"[{stamp}] FAILED - git commit: {out}")
            return EXIT_FAIL
    else:
        print("[3/5] 无新改动，跳过提交 ...")

    # ---------- [4/5] pull --rebase ----------
    print("[4/5] 拉取远端并变基 (pull --rebase) ...")
    rc, out = run_git(repo, ["pull", "--rebase", "origin", branch])
    if rc != 0:
        print("  [警告] rebase 冲突，已自动回滚，本地提交保留。")
        run_git(repo, ["rebase", "--abort"])
        log_write(logfile, f"[{stamp}] FAILED - rebase conflict: {out}")
        return EXIT_FAIL

    # ---------- [5/5] push ----------
    print("[5/5] 推送到 GitHub (git push) ...")
    rc, out = run_git(repo, ["push", "origin", branch])
    if rc != 0:
        print("  首次推送失败，10 秒后重试...")
        log_write(logfile, f"[{stamp}] first push failed, retrying")
        import time

        time.sleep(10)
        rc, out = run_git(repo, ["push", "origin", branch])

    if rc != 0:
        print(f"  [错误] git push 失败: {out}")
        log_write(logfile, f"[{stamp}] FAILED - git push: {out}")
        return EXIT_FAIL

    print()
    print(f"  [完成] 已推送到 GitHub。  {stamp}")
    if has_staged:
        print(f"  共提交 {len(files)} 个文件。")
    log_write(logfile, f"[{stamp}] SUCCESS - pushed")
    return EXIT_OK


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n  已取消。")
        sys.exit(130)
