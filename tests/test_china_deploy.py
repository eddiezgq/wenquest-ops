"""A deployment in China (ADR-0023, step 23f): every image can come from one registry in China (install.sh --mirror,
copied there by images.yml), and the China setting turns off Microsoft and Google sign-in."""

import re
from pathlib import Path

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
