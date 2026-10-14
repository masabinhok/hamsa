"""Checker accounts, from backend/ (run by whoever administers the desk):

uv run python -m app.checkers add "Sita Sharma"   # prints her access code, once
uv run python -m app.checkers list
uv run python -m app.checkers remove "Sita Sharma"
"""

import argparse
import hashlib
import secrets
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.store.cases import Database
from app.store.models import Checker


def code_hash(code: str) -> str:
    # Codes are 128-bit random, so a plain hash suffices: there is nothing to brute-force.
    return hashlib.sha256(code.encode()).hexdigest()


def add(session: Session, name: str) -> str:
    """Create a checker; return their access code, which is not stored and not shown again."""
    name = name.strip()
    if not name:
        raise ValueError("a checker needs a name")
    if session.scalar(select(Checker).where(Checker.name == name)):
        raise ValueError(f"{name} already has an account; remove it first to issue a new code")
    code = secrets.token_urlsafe(16)
    session.add(Checker(name=name, code_sha256=code_hash(code)))
    return code


def signed_in(session: Session, code: str) -> str | None:
    """The active checker this code belongs to, if any."""
    found = session.scalar(select(Checker).where(Checker.code_sha256 == code_hash(code)))
    return found.name if found and found.active else None


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.checkers")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("add").add_argument("name")
    commands.add_parser("list")
    commands.add_parser("remove").add_argument("name")
    args = parser.parse_args()

    db = Database(get_settings().database_url)
    db.create_all()
    with db.session.begin() as session:
        if args.command == "add":
            try:
                code = add(session, args.name)
            except ValueError as error:
                print(error, file=sys.stderr)
                return 1
            print(f"{args.name.strip()}'s access code (shown once, give it to them privately):")
            print(code)
        elif args.command == "list":
            for c in session.scalars(select(Checker).order_by(Checker.name)):
                state = "active" if c.active else "removed"
                print(f"{c.name}  {state}  since {c.created_at:%Y-%m-%d}")
        else:
            found = session.scalar(select(Checker).where(Checker.name == args.name))
            if found is None:
                print(f"no checker named {args.name}", file=sys.stderr)
                return 1
            found.active = False
            print(f"{args.name} can no longer sign in")
    return 0


if __name__ == "__main__":
    sys.exit(main())
