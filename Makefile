.PHONY: run dev install clean format lint

# The default target
.DEFAULT_GOAL := run

# Run the timer application
run:
	uv run main.py

# Install project dependencies and sync the virtual environment
install:
	uv sync

# Run the app in Textual development mode
# Note: It's recommended to run `uvx textual console` in a separate terminal to see dev logs
dev:
	uv run textual run --dev main.py

# Format code using Ruff (runs via uvx so you don't need to install it globally)
format:
	uvx ruff check --fix .
	uvx ruff format .

# Lint code using Ruff
lint:
	uvx ruff check .

# Clean up environment and cache directories
clean:
	rm -rf .venv
	rm -rf .ruff_cache
	find . -type d -name "__pycache__" -exec rm -rf {} +
