import datetime
import os
import pathlib
import shutil
import sys


def check_db():
    print("📊 Checking database...")
    db_path = "data/bountyhunter.db"
    if os.path.exists(db_path):
        print(f"✅ Database exists at {db_path}")
    else:
        print("⚠️  Database not found (will be created on first run)")


def backup_db():
    print("💾 Backing up database...")
    os.makedirs("backups", exist_ok=True)
    src = "data/bountyhunter.db"
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = f"backups/bountyhunter_{timestamp}.db"
    if os.path.exists(src):
        shutil.copy2(src, dst)
        print(f"✅ Database backed up to {dst}")
    else:
        print("⚠️  No database to backup")
    print("✅ Backup operation complete")


def clean_cache():
    print("🧹 Cleaning Python cache files...")
    for p in pathlib.Path(".").rglob("__pycache__"):
        shutil.rmtree(p)
    for p in pathlib.Path(".").rglob("*.pyc"):
        p.unlink()
    print("✅ Python cache cleaned")


def clean_venv():
    print("🧹 Removing virtual environment...")
    shutil.rmtree(".venv", ignore_errors=True)
    print("✅ Virtual environment removed")


def clean_test():
    print("🧹 Cleaning test artifacts...")
    for p in [".pytest_cache", "htmlcov"]:
        shutil.rmtree(p, ignore_errors=True)
    pathlib.Path(".coverage").unlink(missing_ok=True)
    print("✅ Test artifacts cleaned")


def clean_build():
    print("🧹 Cleaning build artifacts...")
    for p in ["dist", "build"]:
        shutil.rmtree(p, ignore_errors=True)
    for p in pathlib.Path(".").rglob("*.egg-info"):
        shutil.rmtree(p)
    print("✅ Build artifacts cleaned")


def init_project():
    print("📁 Creating project structure...")
    dirs = ["src/bounty_core", "src/bounty_discord", "tests", "data", "backups", "logs"]
    for d in dirs:
        os.makedirs(d, exist_ok=True)
    for d in ["src/bounty_core", "src/bounty_discord", "tests"]:
        init_file = os.path.join(d, "__init__.py")
        if not os.path.exists(init_file):
            open(init_file, "a").close()
    print("✅ Project structure created")


def check_env():
    print("🔍 Checking environment configuration...")
    if os.path.exists(".env"):
        print("✅ .env file found")
    else:
        print("⚠️  .env file not found. Copy .env.example to .env")


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/tasks.py <command>")
        sys.exit(1)

    command = sys.argv[1]

    commands = {
        "check-db": check_db,
        "backup-db": backup_db,
        "clean-cache": clean_cache,
        "clean-venv": clean_venv,
        "clean-test": clean_test,
        "clean-build": clean_build,
        "init-project": init_project,
        "check-env": check_env,
    }

    if command in commands:
        commands[command]()
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
