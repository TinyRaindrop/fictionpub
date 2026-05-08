# Development Tasks

.PHONY: install format lint typecheck check build exe gui cli clean

install:
	pip install -e .[dev]

## Code Quality

format:
	ruff format .
	ruff check --fix .

lint:
	ruff check .

typecheck:
	mypy .

# only check without modifying files
check: lint typecheck

## Build

build:
	python -m build

exe:
	python build_exe.py

gui:
	python build_exe.py --gui

cli:
	python build_exe.py --cli

## Cleanup

clean:
	rm -rf build/ dist/ .pytest_cache .ruff_cache .mypy_cache __pycache__