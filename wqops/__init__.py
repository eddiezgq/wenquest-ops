"""WenQuest Ops: AI-native operations platform for small and mid-sized businesses, built on ERPNext.

See docs/plan.md for the phased plan and docs/adr/ for decisions.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("wenquest-ops")
except PackageNotFoundError:  # running from a source tree that is not installed
    __version__ = "0.0.0"
