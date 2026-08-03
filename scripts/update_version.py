# -*- coding: utf-8 -*-
"""
版本号同步脚本（唯一主源：core/_version.py）。

用法：
    python scripts/update_version.py

流程：
    1) 读取 core/_version.py 的 version / version_log（唯一事实源）。
    2) 写入 docs/version.json 的 version / version_log（保留其余字段如 infrom）。
    3) 打印仍需手动同步的文档位置（README / docs 徽章等）。

发版流程：
    1) 只改 core/_version.py 的 version / version_log。
    2) 运行本脚本。
    3) 按提示手动更新 README.md / docs/docs.md 的徽章版本号（仅显示用）。
"""
import json
import os
import sys
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION_MODULE = os.path.join(ROOT, 'core', '_version.py')
VERSION_JSON = os.path.join(ROOT, 'docs', 'version.json')

# 仍需手动同步的文档位置（仅显示徽章/文档，不参与逻辑）
MANUAL_DOCS = [
    os.path.join(ROOT, 'README.md'),
    os.path.join(ROOT, 'docs', 'docs.md'),
    os.path.join(ROOT, 'AGENTS.md'),
]


def read_main_source():
    """从 core/_version.py 解析 version / version_log。"""
    if not os.path.exists(VERSION_MODULE):
        sys.exit(f'[ERROR] 主源不存在: {VERSION_MODULE}')
    with open(VERSION_MODULE, 'r', encoding='utf-8') as f:
        src = f.read()
    version = _extract(src, 'version')
    version_log = _extract(src, 'version_log')
    if not version:
        sys.exit('[ERROR] 主源未解析到 version')
    return version, version_log


def _extract(src, name):
    m = re.search(rf'^{name}\s*=\s*["\'](.*?)["\']', src, re.MULTILINE)
    return m.group(1) if m else None


def update_version_json(version, version_log):
    """同步 docs/version.json（保留其余字段）。"""
    if not os.path.exists(VERSION_JSON):
        data = {}
    else:
        with open(VERSION_JSON, 'r', encoding='utf-8') as f:
            data = json.load(f)
    data['version'] = version
    data['version_log'] = version_log
    with open(VERSION_JSON, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    return VERSION_JSON


def print_manual_hints(version):
    print(f'\n[SYNCED] docs/version.json -> version={version}')
    print('[MANUAL] 以下位置仍为显示用，若需同步请手动更新版本字符串（无需改动 core/_version.py 之外的逻辑源）：')
    for path in MANUAL_DOCS:
        if os.path.exists(path):
            print(f'  - {path}')


def main():
    version, version_log = read_main_source()
    out = update_version_json(version, version_log)
    print(f'[OK] 已写入 {os.path.relpath(out, ROOT)}')
    print_manual_hints(version)


if __name__ == '__main__':
    main()