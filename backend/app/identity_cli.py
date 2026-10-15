"""One-time privileged account bootstrap command."""

from __future__ import annotations

import argparse
import getpass
import sys

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from backend.app.api.auth import hash_password, normalize_email
from backend.app.audit import record_audit_event
from backend.app.db import SessionFactory
from backend.app.models import SystemRole, SystemUser


def create_first_administrator(
    *, username: str, email: str, display_name: str, password: str
) -> int:
    """Create the initial administrator, only while the user table is empty."""
    normalized_email = normalize_email(email)
    user = SystemUser(
        username=username.strip(),
        email_normalized=normalized_email,
        display_name=display_name.strip(),
        role=SystemRole.GLOBAL_ADMINISTRATOR,
        password_hash=hash_password(password),
    )
    if not user.username or len(user.username) > 80:
        raise ValueError("Username must contain between 1 and 80 characters")
    if not user.display_name or len(user.display_name) > 160:
        raise ValueError("Display name must contain between 1 and 160 characters")
    with SessionFactory() as session:
        # Serialize concurrent bootstrap attempts before checking that this is the first user.
        session.execute(text("BEGIN IMMEDIATE"))
        if session.scalar(select(func.count()).select_from(SystemUser)):
            raise ValueError("Administrator bootstrap is available only before any user exists")
        session.add(user)
        session.flush()
        record_audit_event(
            session,
            actor_user_id=None,
            action="system_user.initial_global_administrator_bootstrapped",
            target_type="system_user",
            target_id=user.id,
            metadata={"role": user.role.value, "bootstrap": True},
        )
        session.commit()
        return user.id


def main() -> None:
    parser = argparse.ArgumentParser(prog="contestmaster-admin")
    subparsers = parser.add_subparsers(dest="command", required=True)
    bootstrap = subparsers.add_parser(
        "create-first-admin", help="Create the initial global administrator account"
    )
    bootstrap.add_argument("--username", required=True)
    bootstrap.add_argument("--email", required=True)
    bootstrap.add_argument("--display-name", required=True)
    arguments = parser.parse_args()

    first = getpass.getpass("New administrator password (minimum 12 characters): ")
    confirmation = getpass.getpass("Confirm password: ")
    if first != confirmation:
        parser.error("Passwords do not match")
    try:
        user_id = create_first_administrator(
            username=arguments.username,
            email=arguments.email,
            display_name=arguments.display_name,
            password=first,
        )
    except (ValueError, IntegrityError) as exc:
        print(f"Administrator was not created: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(f"Created global administrator {arguments.username!r} (user id {user_id}).")


if __name__ == "__main__":
    main()
