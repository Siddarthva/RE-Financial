"""Where the project and its outputs live. The app sits in 05_review_workspace/app/; the repo root is two levels up."""
from pathlib import Path

APP = Path(__file__).resolve().parent
PROJECT = APP.parents[1]
OUTPUTS = PROJECT / "outputs"
RUNS = PROJECT / "runs"
DOCS = PROJECT / "04_architecture"
CLIENTS = PROJECT / "clients"
