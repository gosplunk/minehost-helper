from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    # Reuse the same code so installer and uninstaller behavior cannot drift.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import bootstrap_installer

    if "--uninstall" not in sys.argv:
        sys.argv.append("--uninstall")
    bootstrap_installer.main()


if __name__ == "__main__":
    main()
