"""A deployment in China (ADR-0023, step 23f): every image can come from one registry in China (install.sh --mirror,
copied there by images.yml), and the China setting turns off Microsoft and Google sign-in."""

import re
from pathlib import Path

import yaml

from wqops.hub import oidc as O

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = (ROOT / "deploy" / "docker-compose.yml").read_text()
INSTALL = (ROOT / "deploy" / "install.sh").read_text()
IMAGES = (ROOT / ".github" / "workflows" / "images.yml").read_text()


def test_every_image_can_come_from_the_mirror():
    defaults = dict(re.findall(r"image: \$\{(WQO_\w+_IMAGE):-([^}]+)\}", COMPOSE))
    assert set(defaults) == {"WQO_ERP_IMAGE", "WQO_CADDY_IMAGE", "WQO_DB_IMAGE", "WQO_MARIADB_IMAGE",
                             "WQO_REDIS_IMAGE", "WQO_HUB_IMAGE"}
    assert not re.findall(r"^\s*image: (?!\$\{)", COMPOSE, re.M), "an image without a setting"
    mirrored = dict(re.findall(r'envset (WQO_\w+_IMAGE) "\$MIRROR/([^"]+)"', INSTALL))
    copied = re.search(r"for b in (.*?); do", IMAGES, re.S).group(1).replace("\\", " ").split()
    for var, image in defaults.items():
        if var == "WQO_HUB_IMAGE":
            continue
        name = image.split("/")[-1]
        assert mirrored.get(var) == name, (var, image, mirrored.get(var))     # same name and tag in the mirror
        assert any(c.split("/")[-1] == name for c in copied), (name, copied)  # and images.yml copies it there
    assert "wenquest-ops-hub" in INSTALL and "$CN/wenquest-ops-hub" in IMAGES


def test_china_has_no_microsoft_or_google_sign_in():
    env = {"WQO_OIDC_MICROSOFT_TENANT": "t", "WQO_OIDC_MICROSOFT_CLIENT_ID": "i",
           "WQO_OIDC_MICROSOFT_CLIENT_SECRET": "s",
           "WQO_OIDC_GOOGLE_CLIENT_ID": "g", "WQO_OIDC_GOOGLE_CLIENT_SECRET": "h"}
    assert set(O.providers(env)) == {"microsoft", "google"}
    assert O.providers({**env, "WQO_DEPLOYMENT": "cn"}) == {}
    assert "WQO_DEPLOYMENT: ${WQO_DEPLOYMENT:-us}" in COMPOSE and "envset WQO_DEPLOYMENT cn" in INSTALL


def _mb(v: str) -> float:
    n, unit = re.fullmatch(r"(\d+)([mg])", v).groups()
    return int(n) * (1024 if unit == "g" else 1)


def test_the_module_on_the_wenquest_server_fits_its_share():
    """ADR-0024: behind the server's own Caddy (no host ports, qms-demo-edge on qms-edge) and within 2.5 GB."""
    class Loader(yaml.SafeLoader):               # compose's own tags (!reset, !override) are kept as plain values
        pass

    for tag in ("!reset", "!override"):
        Loader.add_constructor(tag, lambda ld, node: ld.construct_sequence(node) if isinstance(node, yaml.SequenceNode)
                               else ld.construct_mapping(node) if isinstance(node, yaml.MappingNode) else None)
    edge = yaml.load((ROOT / "deploy" / "docker-compose.edge.yml").read_text(), Loader=Loader)
    caddy = edge["services"]["caddy"]
    assert caddy["container_name"] == "qms-demo-edge" and "qms-edge" in caddy["networks"]
    assert edge["networks"]["qms-edge"]["external"] is True
    assert "ports: !reset []" in (ROOT / "deploy" / "docker-compose.edge.yml").read_text()
    edgefile = (ROOT / "deploy" / "Caddyfile.edge").read_text()
    assert "auto_https off" in edgefile
    assert "http://{$WQO_DOMAIN}" in edgefile and "http://{$WQO_ERP_DOMAIN}" in edgefile

    small = yaml.safe_load((ROOT / "deploy" / "docker-compose.small.yml").read_text())["services"]
    base = yaml.safe_load(COMPOSE)["services"]
    running = {k for k in base if k != "erp-configurator" and "off" not in (small.get(k) or {}).get("profiles", [])}
    limits = {}
    for k in running:
        v = small[k]["mem_limit"]
        limits[k] = _mb(re.sub(r"\$\{\w+:-(\w+)\}", r"\1", v))
    assert set(limits) == running, running - set(limits)          # every container that runs has a limit
    assert sum(limits.values()) <= 2.5 * 1024, limits
    assert "erp-queue-short" not in running                          # one ERPNext worker takes every queue
    assert "erp-queue-long" in running
