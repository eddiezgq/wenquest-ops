"""Third-party open source notices (ADR-0028): one table of what WenQuest Ops ships or installs, written to
THIRD_PARTY_NOTICES.md and to the help topic "About" (English and Chinese).

    python tools/third_party.py            # write the files
    python tools/third_party.py --check    # exit 1 if they are out of date (tests/test_third_party.py does this)

The table is kept here by hand (license as each project states it); the test fails when a dependency in
pyproject.toml, web/package.json or the images the installer uses is missing from it.
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (name, license, source); a version is read from the repository where there is one
IMAGES = {
    "frappe/erpnext": ("ERPNext and the Frappe framework", "GPL-3.0 (ERPNext), MIT (Frappe)",
                       "https://github.com/frappe/erpnext , https://github.com/frappe/frappe"),
    "mariadb": ("MariaDB", "GPL-2.0", "https://github.com/MariaDB/server"),
    "redis": ("Redis", "BSD-3-Clause", "https://github.com/redis/redis"),
    "postgres": ("PostgreSQL", "PostgreSQL License", "https://www.postgresql.org/ftp/source/"),
    "caddy": ("Caddy", "Apache-2.0", "https://github.com/caddyserver/caddy"),
}
IN_HUB = [
    ("Python", "PSF-2.0", "https://www.python.org/downloads/source/"),
    ("Debian packages of the python:3.12-slim image", "various (see /usr/share/doc/*/copyright in the image)",
     "https://sources.debian.org/"),
    ("Tesseract OCR (tesseract-ocr, English and Simplified Chinese data)", "Apache-2.0",
     "https://github.com/tesseract-ocr/tesseract"),
    ("Droid Sans Fallback font (fonts-droid-fallback, Chinese in the parts manual PDF)", "Apache-2.0",
     "https://sources.debian.org/src/fonts-android/"),
]
PYTHON = {
    "pyyaml": ("MIT", "https://github.com/yaml/pyyaml"),
    "openpyxl": ("MIT", "https://foss.heptapod.net/openpyxl/openpyxl"),
    "fastapi": ("MIT", "https://github.com/fastapi/fastapi"),
    "uvicorn": ("BSD-3-Clause", "https://github.com/encode/uvicorn"),
    "httpx": ("BSD-3-Clause", "https://github.com/encode/httpx"),
    "psycopg": ("LGPL-3.0-only", "https://github.com/psycopg/psycopg"),
    "python-multipart": ("Apache-2.0", "https://github.com/Kludex/python-multipart"),
    "pyjwt": ("MIT", "https://github.com/jpadilla/pyjwt"),
    "pypdf": ("BSD-3-Clause", "https://github.com/py-pdf/pypdf"),
    "python-docx": ("MIT", "https://github.com/python-openxml/python-docx"),
    "pillow": ("MIT-CMU", "https://github.com/python-pillow/Pillow"),
    "pytesseract": ("Apache-2.0", "https://github.com/madmaze/pytesseract"),
    "reportlab": ("BSD-3-Clause", "https://hg.reportlab.com/hg-public/reportlab"),
}
NPM = {
    "@fontsource/barlow-condensed": ("OFL-1.1 (the font)", "https://github.com/fontsource/font-files"),
    "@zxing/browser": ("MIT", "https://github.com/zxing-js/browser"),
    "@zxing/library": ("Apache-2.0", "https://github.com/zxing-js/library"),
    "bwip-js": ("MIT", "https://github.com/metafloor/bwip-js"),
    "echarts": ("Apache-2.0", "https://github.com/apache/echarts"),
    "frappe-ui": ("MIT", "https://github.com/frappe/frappe-ui"),
    "markdown-it": ("MIT", "https://github.com/markdown-it/markdown-it"),
    "occt-import-js": ("LGPL-2.1 (with Open CASCADE Technology, LGPL-2.1 with exception; unmodified, loaded as a "
                       "separate WebAssembly file)", "https://github.com/kovacsv/occt-import-js"),
    "three": ("MIT", "https://github.com/mrdoob/three.js"),
    "vue": ("MIT", "https://github.com/vuejs/core"),
    "vue-router": ("MIT", "https://github.com/vuejs/router"),
    "yaml": ("ISC", "https://github.com/eemeli/yaml"),
}


def _name(req: str) -> str:
    return re.split(r"[\[<>=!~ ;]", req, maxsplit=1)[0].strip().lower()


def python_deps() -> list[str]:
    p = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    return sorted({_name(r) for r in [*p["dependencies"], *p["optional-dependencies"]["hub"]]} - {"wenquest-ops"})


def npm_deps() -> dict[str, str]:
    import json  # noqa: PLC0415

    return json.loads((ROOT / "web" / "package.json").read_text())["dependencies"]


def images() -> dict[str, str]:
    """Image -> tag, as deploy/docker-compose.yml uses them (the hub image is ours)."""
    out = {}
    for m in re.finditer(r"image: \$\{[A-Z_]+:-([^}]+)\}", (ROOT / "deploy" / "docker-compose.yml").read_text()):
        name, _, tag = m.group(1).rpartition(":")
        if "wenquest-ops-hub" not in name:
            out[name] = tag
    return out


def missing() -> list[str]:
    return ([f"python {n}" for n in python_deps() if n not in PYTHON] + [f"npm {n}" for n in npm_deps() if n not in NPM]
            + [f"image {n}" for n in images() if n not in IMAGES])


def rows() -> list[tuple[str, str, str, str]]:
    imgs = images()
    out = [(IMAGES[n][0], imgs[n], IMAGES[n][1], IMAGES[n][2]) for n in IMAGES if n in imgs]
    out += [(n, "", lic, src) for n, lic, src in IN_HUB]
    out += [(f"{n} (Python)", "", *PYTHON[n]) for n in python_deps()]
    npm = npm_deps()
    out += [(f"{n} (npm)", npm[n], *NPM[n]) for n in sorted(npm)]
    return out


def table() -> str:
    lines = ["| Component · 组件 | Version · 版本 | License · 许可证 | Source · 源码 |", "|---|---|---|---|"]
    lines += [f"| {a} | {b} | {c} | {d} |" for a, b, c, d in rows()]
    return "\n".join(lines) + "\n"


NOTICES = """# Third-party open source notices · 第三方开源组件说明

WenQuest Ops is our own program. It installs and talks to the open source programs below through their published
interfaces (ERPNext through its REST API), using the official, **unmodified** versions; the server in China gets
the same official images through a mirror registry. Each image carries its own license files. The source of each is
at the address given; for ERPNext, the tag of the version named. The Python and npm libraries listed are the ones
WenQuest Ops uses directly; their own dependencies carry their licenses in their packages. (ADR-0028; this is our
engineering reading, to be confirmed by a lawyer before commercial use.)

问渠质量 ERP 是我们自己的程序。它安装下列开源软件，并通过它们公开的接口与之通信（ERPNext 通过 REST API），用的都是
**未经修改**的官方版本；国内服务器经镜像仓库取得同样的官方镜像。每个镜像里都带着各自的许可证文件，源码在表中所列地址
（ERPNext 为所列版本的标签）。所列 Python 和 npm 库是问渠质量 ERP 直接使用的；它们自己的依赖，许可证见各自的包。
（ADR-0028；以上为工程上的理解，正式商用前请律师确认。）

""" + "{table}" + """
Generated by `python tools/third_party.py` · 由 `python tools/third_party.py` 生成。
"""

ABOUT = {
    "en": """---
title: About and open source
group: Help
order: 9
summary: What WenQuest Ops is built on, and the open source licenses.
---

WenQuest Ops is our own program, on top of open source programs used as they are: ERPNext keeps orders, stock,
purchasing and the books; WenQuest Ops reads and writes it through ERPNext's REST API and never changes its code.

## Open source components

{table}
The images are the official, unmodified versions; each carries its own license files, and the source is at the
address given. The full text is in THIRD_PARTY_NOTICES.md with the installation.
""",
    "zh": """---
title: 关于与开源组件
group: Help
order: 9
summary: 问渠质量 ERP 建在哪些开源软件之上，以及它们的许可证。
---

问渠质量 ERP 是我们自己的程序，建在原样使用的开源软件之上：订单、库存、采购和账务在 ERPNext 里；问渠质量 ERP 通过
ERPNext 的 REST API 读写，从不改动它的代码。

## 开源组件

{table}
镜像都是官方的、未经修改的版本，各自带着许可证文件，源码在表中所列地址。完整说明见安装目录里的 THIRD_PARTY_NOTICES.md。
""",
}


def files() -> dict[Path, str]:
    t = table()
    help_ = ROOT / "web" / "src" / "help" / "topics"
    return {ROOT / "THIRD_PARTY_NOTICES.md": NOTICES.replace("{table}", t),
            help_ / "about.md": ABOUT["en"].replace("{table}", t),
            help_ / "zh" / "about.md": ABOUT["zh"].replace("{table}", t)}


def main(argv: list[str]) -> int:
    gone = missing()
    if gone:
        print("not in tools/third_party.py: " + ", ".join(gone), file=sys.stderr)
        return 1
    stale = [p for p, text in files().items() if not p.is_file() or p.read_text(encoding="utf-8") != text]
    if "--check" in argv:
        if stale:
            print("out of date (run python tools/third_party.py): " + ", ".join(str(p.relative_to(ROOT))
                                                                               for p in stale), file=sys.stderr)
            return 1
        return 0
    for p, text in files().items():
        p.write_text(text, encoding="utf-8")
    print(f"wrote {len(files())} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
