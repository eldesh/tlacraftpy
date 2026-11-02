PYTHON ?= python
TLA2TOOLS_JAR :=
unexport TLA2TOOLS_JAR
.DEFAULT_GOAL := check

.PHONY: check format format-check docstring-check type-check test docs docs-serve build dist-check

check: format-check docstring-check type-check test

format:
	$(PYTHON) -m ruff format .

format-check:
	$(PYTHON) -m ruff format --check .

docstring-check:
	$(PYTHON) -m ruff check --select D src/tlacraftpy

type-check:
	$(PYTHON) -m mypy

test:
	$(PYTHON) tests/run_tests.py $(if $(TLA2TOOLS_JAR),--tla2tools-jar "$(TLA2TOOLS_JAR)")

docs:
	$(PYTHON) -m mkdocs build --strict

docs-serve:
	$(PYTHON) -m mkdocs serve

build:
	$(PYTHON) -m build

dist-check: build
	$(PYTHON) -m twine check --strict dist/*
