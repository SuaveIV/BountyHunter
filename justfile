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

# === DATABASE OPERATIONS ===

# Inspect database (requires sqlite3 or similar tool, or just checks file existence)
check-db:
    @echo "📊 Checking database..."
    @if [ -f "data/free_games.db" ]; then echo "✅ Database exists at data/free_games.db"; else echo "⚠️  Database not found (will be created on first run)"; fi

# === LINTING AND TESTING ===

# Run tests
test:
    @echo "🧪 Running tests..."
    mise exec -- uv run pytest

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

# Run all code quality checks
check: lint format-check type-check test
    @echo "✅ All code quality checks passed!"

# Fix and format all code issues
fix: lint-fix format
    @echo "✅ Code fixed and formatted!"

# === CLEANUP TASKS ===

# Clean Python cache files
clean-cache:
    @echo "🧹 Cleaning Python cache files..."
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -name "*.pyc" -delete 2>/dev/null || true
    @echo "✅ Python cache cleaned"

# Clean virtual environment
clean-venv:
    @echo "🧹 Removing virtual environment..."
    rm -rf .venv
    @echo "✅ Virtual environment removed"
