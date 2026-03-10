from pathlib import Path
import sys

# Ensure top-level modules (for example dynamic_orchestration.py) are importable in tests.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
