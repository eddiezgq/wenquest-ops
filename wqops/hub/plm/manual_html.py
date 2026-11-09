"""The parts manual as a web page for a read-only link (PLM step 27c, round 124): one self-contained page that works
on a phone, Chinese and English side by side; pictures and tables only. Everything shown is escaped."""

from __future__ import annotations

import html

STYLE = """
:root{--ink:#1f2328;--muted:#6b7280;--line:#d8dce2;--bg:#fff;--head:#f3f5f8}
@media (prefers-color-scheme:dark){:root{--ink:#e7e9ee;--muted:#9aa3ae;--line:#3a3f47;--bg:#16181c;--head:#22262c}}
*{box-sizing:border-box}body{margin:0;font:15px/1.5 system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
color:var(--ink);background:var(--bg)}main{max-width:1100px;margin:0 auto;padding:16px}
h1{font-size:22px;margin:8px 0 2px}h2{font-size:17px;margin:28px 0 8px}.muted{color:var(--muted);font-size:13px}
a{color:#2563eb}nav ol{padding-left:20px}nav li{margin:2px 0}
img{width:100%;height:auto;border:1px solid var(--line);border-radius:6px;background:#fff}
.wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px;margin-top:8px}
th,td{border:1px solid var(--line);padding:5px 7px;text-align:left;vertical-align:top}th{background:var(--head)}
.en{color:var(--muted)}section{border-top:1px solid var(--line);margin-top:24px}
"""
GONE = "这个链接已作废，请联系制造商。 This link is revoked: please ask the maker."
TBC = "英文名待确认 to be confirmed"
UNKNOWN = "没有这个配件手册链接。 There is no such parts manual link."


def _e(s) -> str:
    return html.escape(str(s or ""))


def message(text: str) -> str:
    return (f"<!doctype html><html lang='zh'><meta charset='utf-8'><meta name='viewport' "
            f"content='width=device-width,initial-scale=1'><meta name='robots' content='noindex'>"
            f"<title>配件手册 Parts Manual</title><style>{STYLE}</style><main><h1>配件手册 Parts Manual</h1>"
            f"<p>{_e(text)}</p></main></html>")


def _note(x: dict) -> str:
    if x.get("page"):
        n = int(x["page"])
        return f"<a href='#s{n}'>见第 {n} 节 See section {n}</a>"
    return _e(x.get("note"))


def page(m: dict, base: str) -> str:
    pages = m["pages"]
    toc = "".join(f"<li><a href='#s{n}'>{_e(p['code'])} {_e(p['name'])} <span class='en'>{_e(p.get('name_en'))}"
                  f"</span></a></li>" for n, p in enumerate(pages, start=1))
    body = []
    for n, p in enumerate(pages, start=1):
        pic = (f"<img src='{base}/picture/{n}' alt='{_e(p['code'])}' loading='lazy'>" if p.get("picture")
               else "<p class='muted'>本节无爆炸图 No exploded view</p>")
        rows = "".join(
            f"<tr><td>{x['no']}</td><td>{_e(x['code'])}</td><td>{_e(x['name'])}</td>"
            f"<td class='en'>{_e(x.get('name_en')) or TBC}</td><td>{_e(x['qty'])} {_e(x['uom'])}</td>"
            f"<td>{_note(x)}</td></tr>" for x in p["lines"])
        body.append(f"<section id='s{n}'><h2>{n}. {_e(p['code'])} {_e(p['name'])} <span class='en'>"
                    f"{_e(p.get('name_en'))}</span></h2><p class='muted'>BOM {_e(p['revision'])}</p>{pic}"
                    f"<div class='wrap'><table><thead><tr><th>序号 No.</th><th>编码 Part No.</th><th>名称 Name</th>"
                    f"<th>英文名 English</th><th>数量 Qty</th><th>备注 Note</th></tr></thead><tbody>{rows}</tbody>"
                    f"</table></div></section>")
    return (f"<!doctype html><html lang='zh'><meta charset='utf-8'><meta name='viewport' "
            f"content='width=device-width,initial-scale=1'><meta name='robots' content='noindex'>"
            f"<title>{_e(m['item_code'])} 配件手册 Parts Manual</title><style>{STYLE}</style><main>"
            f"<p class='muted'>配件手册 Parts Manual · 第 {m['edition']} 版 Edition {m['edition']} · "
            f"{_e(str(m['created_at'])[:10])}</p><h1>{_e(m['name'])}</h1><p class='muted'>{_e(m['item_code'])} · "
            f"<a href='{base}/pdf'>下载 PDF · Download PDF</a></p><nav><h2>目录 Contents</h2><ol>{toc}</ol></nav>"
            f"{''.join(body)}</main></html>")
