.PHONY: test test-cov test-unit test-integration eval

test:
	pytest tests/ -v

test-unit:
	pytest tests/unit/ -v

test-integration:
	pytest tests/integration/ -v

test-cov:
	pytest tests/ --cov=app --cov-report=term-missing --cov-fail-under=80

eval:
	@echo "Running RAG evaluation suite (backend must be running on port 8002)..."
	python evaluation/run_eval.py
