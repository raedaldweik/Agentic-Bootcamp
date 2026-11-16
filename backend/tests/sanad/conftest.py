import os
import sys
from pathlib import Path

os.environ["SANAD_PERSIST"] = "false"
os.environ.pop("ANTHROPIC_API_KEY", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
