#!/usr/bin/env python3
"""构建并发布到 GitHub Pages。

用法：
    python3 _build/deploy.py                 # 构建 + 发布
    python3 _build/deploy.py --no-build      # 只发布当前 index.html
    python3 _build/deploy.py -m "提交说明"    # 自定义提交信息

令牌来源（按顺序）：
    GH_TOKEN 环境变量
    macOS 钥匙串 service=rudang-quiz-deploy

做的事：模板+数据 -> 两份 HTML -> 与远端 Git 树逐个文件比对
-> 只上传变化（含删除）-> 提交 -> 等 Pages 线上 MD5 与本地一致。
不需要 git push，走 api.github.com（本机到 github.com 的 443 偶发超时）。
"""
import base64
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request

REPO = "2130391838/rudang-quiz"
BRANCH = "main"
API = "https://api.github.com"
PAGES = "https://2130391838.github.io/rudang-quiz/"
ROOT = pathlib.Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git"}


def die(msg):
    print(f"✗ {msg}", file=sys.stderr)
    sys.exit(1)


def get_token():
    env = os.environ.get("GH_TOKEN", "").strip()
    if env:
        return env
    r = subprocess.run(
        ["security", "find-generic-password", "-s", "rudang-quiz-deploy", "-w"],
        capture_output=True, text=True,
    )
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip()
    die(
        "找不到令牌。执行下面任一方式后重试：\n"
        "  export GH_TOKEN=ghp_xxx\n"
        "  security add-generic-password -a 2130391838 -s rudang-quiz-deploy -w ghp_xxx -U"
    )


def api(tok, path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        API + path, data=data, method=method,
        headers={
            "Authorization": "Bearer " + tok,
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "rudang-quiz-deploy",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as f:
            raw = f.read()
        return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400]
        if e.code == 401:
            die(f"令牌无效或已过期（401）。请更新钥匙串里的令牌后重试。\n{detail}")
        die(f"{method} {path} 失败 {e.code}\n{detail}")
    except urllib.error.URLError as e:
        die(f"网络错误：{e.reason}（重试一次通常就好）")


def blob_sha(b):
    return hashlib.sha1(b"blob %d\0" % len(b) + b).hexdigest()


def collect(root):
    out = {}
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if SKIP_DIRS & set(rel.parts) or rel.name == ".DS_Store":
            continue
        out[rel.as_posix()] = p
    return out


def main():
    args = sys.argv[1:]
    message = None
    if "-m" in args:
        message = args[args.index("-m") + 1]
    if "--no-build" not in args:
        subprocess.run([sys.executable, str(ROOT / "_build/build.py")], check=True)

    tok = get_token()
    files = collect(ROOT)

    head = api(tok, f"/repos/{REPO}/git/ref/heads/{BRANCH}")["object"]["sha"]
    remote = {
        e["path"]: e["sha"]
        for e in api(tok, f"/repos/{REPO}/git/trees/{head}?recursive=1")["tree"]
        if e["type"] == "blob"
    }

    entries, changed = [], []
    for rel, p in files.items():
        b = p.read_bytes()
        if remote.get(rel) == blob_sha(b):
            continue
        blob = api(tok, f"/repos/{REPO}/git/blobs", "POST",
                   {"content": base64.b64encode(b).decode(), "encoding": "base64"})
        entries.append({"path": rel, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        changed.append(rel)

    for rel in sorted(set(remote) - set(files)):
        entries.append({"path": rel, "mode": "100644", "type": "blob", "sha": None})
        changed.append("-" + rel)

    index = ROOT / "index.html"
    md5 = hashlib.md5(index.read_bytes()).hexdigest()

    if not entries:
        print("没有文件变化，跳过提交")
    else:
        msg = message or f"chore: 更新 {len(changed)} 个文件"
        tree = api(tok, f"/repos/{REPO}/git/trees", "POST",
                   {"base_tree": head, "tree": entries})["sha"]
        commit = api(tok, f"/repos/{REPO}/git/commits", "POST",
                     {"message": msg, "tree": tree, "parents": [head]})
        api(tok, f"/repos/{REPO}/git/refs/heads/{BRANCH}", "PATCH",
            {"sha": commit["sha"], "force": False})
        print(f"已提交 {commit['sha'][:7]}：{', '.join(changed)}")

    print(f"等待 Pages 刷新（本地 index.html md5 {md5}）…")
    for i in range(24):
        try:
            with urllib.request.urlopen(f"{PAGES}?v={int(time.time())}", timeout=20) as r:
                if hashlib.md5(r.read()).hexdigest() == md5:
                    print(f"✓ 已上线 {PAGES}")
                    break
        except Exception:
            pass
        time.sleep(5)
    else:
        print("…已提交，但 Pages 还没刷新到最新版（通常 1 分钟内生效，稍后刷新页面即可）")

    # 本地 git 只是镜像：尽力跟随远端，失败不影响发布
    try:
        subprocess.run(
            ["git", "-C", str(ROOT), "-c", "http.version=HTTP/1.1",
             "fetch", "--quiet", "origin", BRANCH],
            check=True, timeout=45, capture_output=True,
        )
        subprocess.run(["git", "-C", str(ROOT), "reset", "--hard", "FETCH_HEAD"],
                       check=True, capture_output=True)
        print("本地 git 已同步")
    except Exception:
        print("本地 git 未同步（网络），不影响线上；下次发布成功时会自动对齐")


if __name__ == "__main__":
    main()