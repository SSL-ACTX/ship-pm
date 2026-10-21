"""Ship CLI entrypoint — thin wrapper over the declarative engine."""

from __future__ import annotations


def main() -> None:
    # Import locally so `ship --help` / `--version` stay cold-start fast:
    # command handlers (install, github, admin) load only when dispatched.
    from ship.cli.app import build_app

    build_app().run()


if __name__ == "__main__":
    main()
