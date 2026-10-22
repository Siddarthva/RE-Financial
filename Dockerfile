# Offline close engine: one client per container. No credentials, no network, no model calls.
# Build:  docker build -t re-close-engine:local .
# Run:    see deploy/compose.yaml (mounts clients/<id> read-only, outputs/<id> writable, network_mode: none).
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONUTF8=1 HOME=/tmp
WORKDIR /app

# Engine dependencies only (streamlit is the review UI and is not needed to compute numbers).
RUN pip install --no-cache-dir "pandas>=2.2,<3.0" "openpyxl>=3.1,<4.0" "PyYAML>=6.0,<7.0"

# Code the pipeline imports. Client folders, source data and outputs are NOT baked in; compose mounts them.
COPY src/ /app/src/
COPY scripts/run_pipeline.py /app/scripts/run_pipeline.py
COPY 03_evals/grade_commentary.py /app/03_evals/grade_commentary.py
COPY .claude/skills/monthly-financial-analysis/SKILL.md /app/.claude/skills/monthly-financial-analysis/SKILL.md

RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin engine \
 && mkdir -p /app/clients /app/outputs /app/data \
 && chown 10001 /app/outputs
USER 10001

ENTRYPOINT ["python", "-X", "utf8", "scripts/run_pipeline.py"]
