import sys
import os

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from database import get_conn, init_db  # noqa: E402

__all__ = ["get_conn", "init_db"]
