import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def main():
    from backend.main import run
    run()


if __name__ == "__main__":
    main()
