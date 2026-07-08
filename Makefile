# Convenience targets. On Windows without make, run the underlying commands
# directly (they're plain python invocations).

.PHONY: test lint typecheck eval eval-score serve

test:
	python -m pytest

lint:
	python -m ruff check .
	python -m black --check .

typecheck:
	python -m mypy

serve:
	uvicorn --factory truthlayer.api:create_app --reload

# One command = one measurement: runs the full dataset through the graph and
# scores it. Pass TAG=reranking (etc.) to label the run.
TAG ?= run
eval:
	python eval/run_eval.py --tag $(TAG)

# Score the most recent results file.
eval-score:
	python eval/score_eval.py "$$(ls -t eval/results/*.json | head -1)" --report eval/report.md
