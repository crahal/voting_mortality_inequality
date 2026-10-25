PYTHON ?= python

.PHONY: help install check test sources fetch-data verify-data verify-results analysis

help:
	@printf '%s\n' 'install         Install analysis and development dependencies' 'check           Lint code and validate repository metadata' 'test            Run synthetic-data unit tests' 'sources         Print the pinned data-source manifest' 'fetch-data      Fetch available inputs and verify all required data' 'verify-data     Verify local input hashes and schemas offline' 'verify-results  Recompute and check correlation/p-value hashes offline' 'analysis        Execute the notebook and regenerate publication outputs'

install:
	$(PYTHON) -m pip install -r requirements-dev.txt

check:
	$(PYTHON) -m ruff check .
	$(PYTHON) scripts/check_repository.py

test:
	$(PYTHON) -m unittest discover -s tests -v

sources:
	$(PYTHON) scripts/manage_data.py sources

fetch-data:
	$(PYTHON) scripts/manage_data.py fetch

verify-data:
	$(PYTHON) scripts/manage_data.py verify

verify-results:
	$(PYTHON) scripts/verify_results.py

analysis:
	$(PYTHON) scripts/run_analysis.py
