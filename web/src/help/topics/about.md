---
title: About and open source
group: Help
order: 9
summary: What WenQuest Ops is built on, and the open source licenses.
---

WenQuest Ops is our own program, on top of open source programs used as they are: ERPNext keeps orders, stock,
purchasing and the books; WenQuest Ops reads and writes it through ERPNext's REST API and never changes its code.

## Open source components

| Component · 组件 | Version · 版本 | License · 许可证 | Source · 源码 |
|---|---|---|---|
| ERPNext and the Frappe framework | v16.34.1 | GPL-3.0 (ERPNext), MIT (Frappe) | https://github.com/frappe/erpnext , https://github.com/frappe/frappe |
| MariaDB | 11.8 | GPL-2.0 | https://github.com/MariaDB/server |
| Redis | 6.2-alpine | BSD-3-Clause | https://github.com/redis/redis |
| PostgreSQL | 16-alpine | PostgreSQL License | https://www.postgresql.org/ftp/source/ |
| Caddy | 2.10-alpine | Apache-2.0 | https://github.com/caddyserver/caddy |
| Python |  | PSF-2.0 | https://www.python.org/downloads/source/ |
| Debian packages of the python:3.12-slim image |  | various (see /usr/share/doc/*/copyright in the image) | https://sources.debian.org/ |
| Tesseract OCR (tesseract-ocr, English and Simplified Chinese data) |  | Apache-2.0 | https://github.com/tesseract-ocr/tesseract |
| fastapi (Python) |  | MIT | https://github.com/fastapi/fastapi |
| httpx (Python) |  | BSD-3-Clause | https://github.com/encode/httpx |
| openpyxl (Python) |  | MIT | https://foss.heptapod.net/openpyxl/openpyxl |
| pillow (Python) |  | MIT-CMU | https://github.com/python-pillow/Pillow |
| psycopg (Python) |  | LGPL-3.0-only | https://github.com/psycopg/psycopg |
| pyjwt (Python) |  | MIT | https://github.com/jpadilla/pyjwt |
| pypdf (Python) |  | BSD-3-Clause | https://github.com/py-pdf/pypdf |
| pytesseract (Python) |  | Apache-2.0 | https://github.com/madmaze/pytesseract |
| python-docx (Python) |  | MIT | https://github.com/python-openxml/python-docx |
| python-multipart (Python) |  | Apache-2.0 | https://github.com/Kludex/python-multipart |
| pyyaml (Python) |  | MIT | https://github.com/yaml/pyyaml |
| uvicorn (Python) |  | BSD-3-Clause | https://github.com/encode/uvicorn |
| @fontsource/barlow-condensed (npm) | 5.2.8 | OFL-1.1 (the font) | https://github.com/fontsource/font-files |
| @zxing/browser (npm) | 0.2.1 | MIT | https://github.com/zxing-js/browser |
| @zxing/library (npm) | 0.23.0 | Apache-2.0 | https://github.com/zxing-js/library |
| bwip-js (npm) | 4.11.4 | MIT | https://github.com/metafloor/bwip-js |
| echarts (npm) | 5.6.0 | Apache-2.0 | https://github.com/apache/echarts |
| frappe-ui (npm) | 1.0.0 | MIT | https://github.com/frappe/frappe-ui |
| markdown-it (npm) | 14.1.0 | MIT | https://github.com/markdown-it/markdown-it |
| vue (npm) | 3.5.22 | MIT | https://github.com/vuejs/core |
| vue-router (npm) | 4.5.1 | MIT | https://github.com/vuejs/router |
| yaml (npm) | 2.9.1 | ISC | https://github.com/eemeli/yaml |

The images are the official, unmodified versions; each carries its own license files, and the source is at the
address given. The full text is in THIRD_PARTY_NOTICES.md with the installation.
