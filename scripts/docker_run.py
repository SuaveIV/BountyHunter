import os
import subprocess
import sys


def main():
    cwd = os.getcwd()
    try:
        # Run docker command
        # Use shell=False for list arguments
        subprocess.run(
            [
                "docker",
                "run",
                "-it",
                "--rm",
                "--env-file",
                ".env",
                "-v",
                f"{cwd}/data:/app/data",
                "bountyhunter:latest",
            ],
            check=True,
        )
    except KeyboardInterrupt:
        print("\n🛑 Stopping Docker container...")
        sys.exit(0)
    except subprocess.CalledProcessError as e:
        # Docker exited with error
        sys.exit(e.returncode)
    except Exception as e:
        print(f"Error running docker: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
