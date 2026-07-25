#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["keyring>=25,<26"]
# ///
"""Store Even Hub credentials in the operating system's credential store."""

from __future__ import annotations

import argparse
import getpass
import sys

import keyring
from keyring.errors import PasswordDeleteError


SERVICE_NAME = "xangi-even-g2/even-hub"


def normalize_account(account: str) -> str:
    normalized = account.strip().lower()
    if not normalized:
        raise ValueError("account must not be empty")
    return normalized


def store(account: str, password: str) -> None:
    if not password:
        raise ValueError("password must not be empty")
    keyring.set_password(SERVICE_NAME, normalize_account(account), password)


def lookup(account: str) -> str | None:
    return keyring.get_password(SERVICE_NAME, normalize_account(account))


def clear(account: str) -> bool:
    try:
        keyring.delete_password(SERVICE_NAME, normalize_account(account))
    except PasswordDeleteError:
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("store", "lookup", "clear"))
    parser.add_argument("--account", required=True)
    parser.add_argument("--stdin", action="store_true", help="read password from standard input")
    args = parser.parse_args()

    if args.action == "store":
        password = sys.stdin.read().rstrip("\n") if args.stdin else getpass.getpass()
        store(args.account, password)
        return 0
    if args.action == "lookup":
        password = lookup(args.account)
        if password is None:
            return 1
        sys.stdout.write(password)
        return 0
    return 0 if clear(args.account) else 1


if __name__ == "__main__":
    raise SystemExit(main())
