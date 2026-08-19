# Every target runs against the project virtualenv if one exists, so the
# pipeline can never quietly install itself over a global interpreter.
# Create it once with:  python -m venv .venv && make install

VENV := .venv
ifeq ($(OS),Windows_NT)
  PY := $(VENV)/Scripts/python.exe
else
  PY := $(VENV)/bin/python
endif
ifeq ($(wildcard $(PY)),)
  PY := python
endif

.PHONY: venv install test test-fast lint format ingest backfill backfill-history reconcile clean build analyse simulate sensitivity dashboard screenshots all

venv:         ; python -m venv $(VENV)
install:      ; $(PY) -m pip install -r requirements.txt
lint:         ; $(PY) -m ruff check . && $(PY) -m ruff format --check .
format:       ; $(PY) -m ruff format . && $(PY) -m ruff check --fix .
test:         ; $(PY) -m pytest -v --cov=ingest --cov=transform --cov=simulate --cov-report=term-missing
test-fast:    ; $(PY) -m pytest -v -m "not slow"
ingest:       ; $(PY) -m ingest.daily
backfill:     ; $(PY) -m ingest.backfill
backfill-history: ; $(PY) -m ingest.backfill --history
reconcile:    ; $(PY) -m ingest.backfill --reconcile
clean:        ; $(PY) -m transform.clean
build:        ; $(PY) -m transform.warehouse
analyse:      ; $(PY) -m analytics.queries
simulate:     ; $(PY) -m simulate.engine
sensitivity:  ; $(PY) -m simulate.sensitivity
dashboard:    ; $(PY) -m streamlit run dashboard/app.py
screenshots:  ; $(PY) tools/capture_screenshots.py
all:          ; $(MAKE) clean && $(MAKE) build && $(MAKE) analyse && $(MAKE) simulate
