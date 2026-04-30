.PHONY: test test-cov test-unit test-integration

test:
	pytest tests/ -v

test-unit:
	pytest tests/unit/ -v

test-integration:
	pytest tests/integration/ -v

test-cov:
	pytest tests/ --cov=app --cov-report=term-missing --cov-fail-under=80
