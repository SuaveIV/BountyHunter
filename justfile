set dotenv-load

# Default recipe - shows help
default:
    @just --list

# === SETUP AND INSTALLATION ===

# Complete setup: create venv, generate lockfile, and install dependencies
setup:
    @echo "🚀 Setting up BountyHunter development environment..."
    just lock
    just install-deps
    just export-requirements
    just verify-setup
    @echo "✅ Setup complete! Run 'just run' to start the bot."

# Install all dependencies (runtime + dev) using uv sync
install-deps:
    @echo "📥 Syncing dependencies with uv..."
    mise exec -- uv sync --extra dev
    @echo "✅ Dependencies synced."

# Install only production dependencies (no dev tools)
install-prod:
    @echo "📥 Syncing production dependencies..."
    mise exec -- uv sync
    @echo "✅ Production dependencies synced."

# Generate/Update uv.lock
lock:
    @echo "🔒 Updating uv.lock..."
    mise exec -- uv lock
    @echo "✅ uv.lock updated."

# Export requirements.txt for Docker
export-requirements:
    @echo "📄 Exporting requirements.txt from lockfile..."
    mise exec -- uv export --format requirements-txt --output-file requirements.txt
    @echo "✅ requirements.txt exported."

# Upgrade all dependencies
update-deps:
    @echo "⬆️  Upgrading dependencies..."
    mise exec -- uv lock --upgrade
    just install-deps
    just export-requirements
    @echo "✅ Dependencies upgraded and requirements.txt updated."

# Upgrade a specific package
update-package package:
    @echo "⬆️  Upgrading {{package}}..."
    mise exec -- uv add "{{package}}@latest"
    just lock
    just export-requirements
    @echo "✅ {{package}} upgraded."

# Verify installation is working
verify-setup:
    @echo "🔍 Verifying installation..."
    @echo "Python version:"
    mise exec -- uv run python --version
    @echo "BountyHunter packages:"
    mise exec -- uv run python -c "import bounty_core; import bounty_discord; print('✅ Packages loaded successfully')" || echo "⚠️  Packages not found"

# === RUNNING THE BOT ===

# Run the main bot
run:
    @echo "🤖 Starting BountyHunter..."
    @echo "Press Ctrl+C to stop the bot gracefully"
    mise exec -- uv run python src/bounty_discord/run.py
    @echo "🛑 BountyHunter stopped"

# Run bot in development mode with auto-reload (if supported)
dev:
    @echo "🔧 Starting BountyHunter in development mode..."
    mise exec -- uv run python src/bounty_discord/run.py --dev

# Run bot with specific log level
run-verbose:
    @echo "🤖 Starting BountyHunter with verbose logging..."
    mise exec -- uv run python src/bounty_discord/run.py --log-level DEBUG

# === DATABASE OPERATIONS ===

# Inspect database (requires sqlite3 or similar tool, or just checks file existence)
check-db:
    @mise exec -- uv run python scripts/tasks.py check-db

# Backup database
backup-db:
    @mise exec -- uv run python scripts/tasks.py backup-db

# Open database shell (requires sqlite3)
db-shell:
    @echo "🗄️  Opening database shell..."
    @sqlite3 data/bountyhunter.db || echo "⚠️  sqlite3 not installed or database not found"

# === LINTING AND TESTING ===

# Run tests
test:
    @echo "🧪 Running tests..."
    mise exec -- uv run pytest

# Run tests with coverage report
test-cov:
    @echo "🧪 Running tests with coverage..."
    mise exec -- uv run pytest --cov=src --cov-report=term-missing --cov-report=html
    @echo "📊 Coverage report generated in htmlcov/index.html"

# Run tests for a specific file or directory
test-file path:
    @echo "🧪 Running tests for {{path}}..."
    mise exec -- uv run pytest {{path}}

# Run tests in watch mode (requires pytest-watch)
test-watch:
    @echo "👀 Running tests in watch mode..."
    mise exec -- uv run ptw

# Run ruff linter
lint:
    @echo "🔍 Running ruff linter..."
    mise exec -- uv run ruff check .

# Run ruff linter with auto-fix
lint-fix:
    @echo "🔧 Running ruff linter with auto-fix..."
    mise exec -- uv run ruff check --fix .

# Format code with ruff
format:
    @echo "✨ Formatting code with ruff..."
    mise exec -- uv run ruff format .

# Check code formatting without making changes
format-check:
    @echo "🔍 Checking code formatting..."
    mise exec -- uv run ruff format --check .

# Run static type checking
type-check:
    @echo "🧐 Running pyright type checker..."
    mise exec -- uv run pyright

# Run type checking on a specific file or directory
type-check-file path:
    @echo "🧐 Running pyright on {{path}}..."
    mise exec -- uv run pyright {{path}}

# Run all code quality checks
check: lint format-check type-check test
    @echo "✅ All code quality checks passed!"

# Fix and format all code issues
fix: lint-fix format
    @echo "✅ Code fixed and formatted!"

# Run security checks (requires bandit or similar)
security:
    @echo "🔒 Running security checks..."
    mise exec -- uv run bandit -r src/ || echo "⚠️  Bandit not installed. Add it to dev dependencies."

# === DOCKER OPERATIONS ===

# Build Docker image
docker-build:
    @echo "🐳 Building Docker image..."
    docker build -t bountyhunter:latest .
    @echo "✅ Docker image built"

# Run bot in Docker
docker-run:
    @echo "🐳 Running BountyHunter in Docker..."
    @mise exec -- uv run python scripts/docker_run.py

# Build and run in Docker
docker-up: docker-build docker-run

# === CLEANUP TASKS ===

# Clean Python cache files
clean-cache:
    @mise exec -- uv run python scripts/tasks.py clean-cache

# Clean virtual environment
clean-venv:
    @mise exec -- uv run python scripts/tasks.py clean-venv

# Clean test artifacts
clean-test:
    @mise exec -- uv run python scripts/tasks.py clean-test

# Clean build artifacts
clean-build:
    @mise exec -- uv run python scripts/tasks.py clean-build

# Clean everything (cache, venv, test, build)
clean-all: clean-cache clean-test clean-build
    @echo "✅ All artifacts cleaned!"

# Deep clean (everything including venv)
clean-deep: clean-all clean-venv
    @echo "✅ Deep clean complete! Run 'just setup' to reinstall."

# === DOCUMENTATION ===

# Generate documentation (if using sphinx or similar)
docs:
    @echo "📚 Generating documentation..."
    @echo "⚠️  Documentation generation not configured yet"

# Serve documentation locally
docs-serve:
    @echo "📖 Serving documentation..."
    @echo "⚠️  Documentation serving not configured yet"

# === UTILITY TASKS ===

# Show project information
info:
    @echo "📋 BountyHunter Project Information"
    @echo "==================================="
    @echo "Python version:"
    @mise exec -- uv run python --version
    @echo ""
    @echo "UV version:"
    @mise exec -- uv --version
    @echo ""
    @echo "Mise version:"
    @mise --version
    @echo ""
    @echo "Installed packages:"
    @mise exec -- uv pip list

# Check for outdated dependencies
check-outdated:
    @echo "🔍 Checking for outdated dependencies..."
    @mise exec -- uv pip list --outdated

# Create project structure (for new setup)
init-project:
    @mise exec -- uv run python scripts/tasks.py init-project

# Validate .env file exists
check-env:
    @mise exec -- uv run python scripts/tasks.py check-env

# Run pre-commit checks (ideal before committing)
pre-commit: check
    @echo "✅ Pre-commit checks passed! Safe to commit."
