"""No-install import shim for the src-layout package.

The implementation lives in src/ad_signal_lakehouse. Keeping this lightweight
shim lets `python -m ad_signal_lakehouse` work from a fresh clone before an
editable install.
"""

from pathlib import Path

_SRC_PACKAGE = Path(__file__).resolve().parent.parent / "src" / "ad_signal_lakehouse"
if _SRC_PACKAGE.exists():
    __path__ = [str(_SRC_PACKAGE)] + list(__path__)

__version__ = "0.1.0"
