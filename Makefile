.PHONY: install run test eval check
install:
	python -m pip install -e '.[dev]'
run:
	python -m flightcheck.cli --policy config/policy.yml serve
test:
	python -m pytest
eval:
	python -m flightcheck.cli eval
check: test eval
	python scripts/check_catalog.py
	node --check flightcheck/web/app.js
