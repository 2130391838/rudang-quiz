#!/usr/bin/env python3
"""重新生成单文件网页：app_template.html + data.json -> ../入党刷题.html"""
import json, pathlib
here = pathlib.Path(__file__).resolve().parent
data = json.loads((here / 'data.json').read_text(encoding='utf-8'))
js = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
tpl = (here / 'app_template.html').read_text(encoding='utf-8')
out = here.parent / 'index.html'
out.write_text(tpl.replace('__DATA__', js), encoding='utf-8')
print('已生成', out, out.stat().st_size, 'bytes')
