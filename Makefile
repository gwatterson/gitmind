# Shortcuts for the evaluation (see eval/README.md). On Windows run the commands
# after each target from the backend directory.

.PHONY: eval eval-test eval-smoke eval-semgrep eval-check

eval: ## Evaluate the dev split with the local model (answers are cached)
	cd backend && uv run python -m evals run --split dev

eval-test: ## Final report on the frozen test split
	cd backend && uv run python -m evals run --split test

eval-smoke: ## CI subset, replaying the recorded answers
	cd backend && uv run python -m evals run --smoke --cache replay --label smoke

eval-semgrep: ## Baseline: semgrep alone on the same cases
	cd backend && uv run python -m evals semgrep --split all

eval-check: ## Validate the dataset
	cd backend && uv run python -m evals check
