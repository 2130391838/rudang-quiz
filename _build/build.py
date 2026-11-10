#!/usr/bin/env python3
"""重新生成单文件网页。

app_template.html + data.json
  -> repo/index.html        （发布用，Git 里的那份）
  -> ../入党刷题.html        （本机双击用的那份）

两份内容逐字节一致。不要手改生成物，改模板后重跑本脚本。
"""
import json
import pathlib

here = pathlib.Path(__file__).resolve().parent
repo = here.parent
root = repo.parent

data = json.loads((here / "data.json").read_text(encoding="utf-8"))
js = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
tpl = (here / "app_template.html").read_text(encoding="utf-8")
html = tpl.replace("__DATA__", js)

for out in (repo / "index.html", root / "入党刷题.html"):
    out.write_text(html, encoding="utf-8")

print(f"已生成 index.html / 入党刷题.html · {len(html.encode())} bytes")