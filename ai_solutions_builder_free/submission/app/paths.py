"""Where the project and its outputs live. Works from the dev layout (app/ beside ai_solutions_builder_free/)
and from the submission layout (app/ inside the project folder, outputs/ one level up)."""
from pathlib import Path

APP = Path(__file__).resolve().parent
_inside = APP.parent / "scripts" / "run_pipeline.py"
PROJECT = APP.parent if _inside.is_file() else APP.parent / "ai_solutions_builder_free"
OUTPUTS = PROJECT.parent / "outputs"
DOCS = PROJECT / "docs"
