import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ml.compare_models import run_benchmark

if __name__ == "__main__":
    run_benchmark()
