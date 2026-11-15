"""Native UI fixtures use signed test licenses and a test-key-only executable."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def provision(home):
    subprocess.run([str(ROOT / 'target/license-fixture'), '--home', str(home)], check=True)
