"""
Conecta o repositório local ao GitHub e envia a branch main.
Uso: python scripts/push_github.py
"""
from __future__ import annotations

import subprocess
import sys


def run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, check=False)
    if r.returncode != 0:
        sys.exit(r.returncode)


def main() -> None:
    REPO_URL = input("Informe URL do repositório GitHub: ").strip()
    if not REPO_URL:
        print("URL vazia. Abortando.")
        sys.exit(1)

    run(["git", "branch", "-M", "main"])

    check = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
    )
    if check.returncode == 0:
        run(["git", "remote", "set-url", "origin", REPO_URL])
    else:
        run(["git", "remote", "add", "origin", REPO_URL])

    run(["git", "push", "-u", "origin", "main"])


if __name__ == "__main__":
    main()
