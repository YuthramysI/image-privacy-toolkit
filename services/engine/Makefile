PY ?= .venv/bin/python

.PHONY: install dev test serve bench

install:
	python3 -m venv .venv
	$(PY) -m pip install -r requirements.txt
	# facenet-pytorch fija versiones antiguas de torch/numpy; su código funciona
	# con las actuales, así que se instala sin dependencias.
	$(PY) -m pip install --no-deps facenet-pytorch==2.6.0

dev: install
	$(PY) -m pip install -r requirements-dev.txt

test:
	$(PY) -m pytest -q

serve:
	$(PY) -m uvicorn engine.api:app --host 0.0.0.0 --port 8000

bench:
	$(PY) -m engine.eval.run --images samples --preset media --out reports
