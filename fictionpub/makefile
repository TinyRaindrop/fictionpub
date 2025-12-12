# Development Tasks

.PHONY: install
install:
	pip install -e .[dev]

.PHONY: format
format:
	ruff check --fix .
	ruff format .

.PHONY: lint
lint:
	ruff check .
	mypy .

.PHONY: test
test:
	pytest -q

.PHONY: testcov
testcov:
	pytest --cov=fictionpub --cov-report=term-missing

.PHONY: build
build:
	python -m build

.PHONY: exe
exe:
	python build_exe.py

.PHONY: publish
publish:
	twine upload dist/*

.PHONY: clean
clean:
	rm -rf build/ dist/ .pytest_cache .ruff_cache .mypy_cache
