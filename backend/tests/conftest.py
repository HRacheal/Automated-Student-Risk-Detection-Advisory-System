import sys
from pathlib import Path

# Allow `import anomaly_engine` etc. (the backend uses flat imports)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
