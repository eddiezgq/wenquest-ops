"""WenQuest PLM add-on: settings (address of the quality ERP, access token) and sending a batch. The token is made
by the owner on the quality ERP's Integrations page with the right "plm:send"; it is kept in FreeCAD's user settings
on this computer only. Works without the FreeCAD window (command line)."""
import json
import os
import ssl
import urllib.error
import urllib.request
import uuid

PREF = "User parameter:BaseApp/Preferences/Mod/WenQuestPLM"


def settings():
    try:
        import FreeCAD as App
        g = App.ParamGet(PREF)
        return {"server": g.GetString("Server", ""), "token": g.GetString("Token", "")}
    except Exception:
        return {"server": os.environ.get("WQ_PLM_SERVER", ""), "token": os.environ.get("WQ_PLM_TOKEN", "")}


def save_settings(server, token):
    import FreeCAD as App
    g = App.ParamGet(PREF)
    g.SetString("Server", (server or "").strip().rstrip("/"))
    g.SetString("Token", (token or "").strip())


class NetError(Exception):
    pass


def _multipart(fields, files):
    """fields: name -> text; files: [(field, file name, bytes)]."""
    b = uuid.uuid4().hex
    out = []
    for k, v in fields.items():
        head = f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n'.encode()
        out.append(head + v.encode("utf-8") + b"\r\n")
    for k, name, data in files:
        out.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"; filename="{name}"\r\n'
                   'Content-Type: application/octet-stream\r\n\r\n'.encode() + data + b"\r\n")
    out.append(f"--{b}--\r\n".encode())
    return b"".join(out), f"multipart/form-data; boundary={b}"


def _open(req, timeout):
    if not req.full_url.startswith(("https://", "http://")):
        raise NetError("地址要以 https:// 开头 / the address starts with https://")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as r:  # noqa: S310
            return json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode("utf-8")).get("detail", "")
        except Exception:
            msg = ""
        raise NetError(f"{e.code}: {msg or e.reason}") from e
    except urllib.error.URLError as e:
        raise NetError(f"连不上 / cannot reach the server: {e.reason}") from e


def _check(s):
    if not s["server"] or not s["token"]:
        raise NetError("先在“设置”里填质量 ERP 地址和钥匙 / set the address and token first")


def whoami(timeout=10):
    s = settings()
    _check(s)
    req = urllib.request.Request(s["server"] + "/api/integration/v1/whoami",  # noqa: S310 - _open checks the scheme
                                 headers={"Authorization": "Bearer " + s["token"]})
    return _open(req, timeout)


def send(data, steps, model=None, timeout=300):
    """data: nodes and links; steps: node key -> (file name, bytes); model: (file name, bytes) of the FCStd."""
    s = settings()
    _check(s)
    files = [("file:" + k, n, b) for k, (n, b) in steps.items()]
    if model:
        files.append(("model", model[0], model[1]))
    body, ctype = _multipart({"data": json.dumps(data, ensure_ascii=False)}, files)
    req = urllib.request.Request(s["server"] + "/api/integration/v1/plm/design-data", data=body, method="POST",  # noqa: S310 - _open checks the scheme
                                 headers={"Authorization": "Bearer " + s["token"], "Content-Type": ctype})
    return _open(req, timeout)
