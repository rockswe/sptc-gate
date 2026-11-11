import os
import sys
from pathlib import Path

CLOUD = Path(__file__).resolve().parents[1]
SPEC_PTC = Path(os.environ.get("SPEC_PTC_ROOT") or CLOUD.parents[1] / "spec-ptc")

for p in (str(SPEC_PTC), str(CLOUD), str(CLOUD / "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)
os.environ.setdefault("SPEC_PTC_ROOT", str(SPEC_PTC))
