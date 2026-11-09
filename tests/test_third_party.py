"""ADR-0028: every image the installer uses and every direct Python and npm dependency is in the third-party
notices, and the notices (and the help topic "About") are up to date."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_notices_list_every_component_and_are_up_to_date():
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "third_party.py"), "--check"], capture_output=True,
                       text=True, check=False)
    assert r.returncode == 0, r.stderr
    text = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert "GPL-3.0 (ERPNext)" in text and "https://github.com/frappe/erpnext" in text and "unmodified" in text
