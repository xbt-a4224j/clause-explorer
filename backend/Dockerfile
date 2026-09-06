FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The platform, as a local wheel. `vendor/` is gitignored and written by semantic-quorum's
# scripts/sync-into.sh, so `make platform-sync` is a prerequisite of building this image — the
# COPY below fails loudly if it was skipped, which is the intent. That is the accepted cost of
# local wheels over a submodule: a fresh clone cannot build until it syncs once. The wheel is
# not committed because this repo has already lost the ability to push once by committing
# generated files.
#
# `pip install ../semantic-quorum` is not an option here: the build context is `.`, so a
# sibling directory is not in it. That constraint is what decided wheels over an editable
# install in the first place.
COPY vendor/ ./vendor/
RUN pip install --no-cache-dir --no-deps vendor/semantic_quorum-*.whl

# The domain manifest. Read at import by explorer/domain.py and validated there, so a missing
# or wrong one fails at container start rather than on the first question — where the symptom,
# every question declining, reads as a model problem rather than a configuration one.
COPY quorum.yaml .

COPY backend/ ./backend/
COPY data/ ./data/
# docs/results and docs/eval are read at runtime by /admin (calibration, eval reports) and
# /label (calibration_predictions.json) — committed artefacts, not regenerated in the image.
COPY docs/ ./docs/
ENV PYTHONPATH=/app/backend PYTHONUNBUFFERED=1
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=5 CMD curl -fs http://localhost:8000/healthz || exit 1
CMD ["uvicorn", "explorer.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
