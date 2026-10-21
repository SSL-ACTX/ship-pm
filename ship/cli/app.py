"""Ship CLI application — command registry (help is generated, never hand-written)."""

from __future__ import annotations

from ship import __version__
from ship.cli.engine import Argument, CliEngine, Command, Option, lazy


def build_app() -> CliEngine:
    app = CliEngine(
        name="ship",
        version=__version__,
        about="Agnostic shell package orchestrator for pre-built binaries.",
        global_opts=(
            Option(
                ("-h", "--help"),
                dest="help",
                help="Print help information and exit",
                default=False,
            ),
            Option(
                ("-V", "--version"),
                dest="version",
                help="Print version info and exit",
                default=False,
            ),
            Option(
                ("-t", "--target"),
                dest="target",
                help="Override target platform architecture",
                takes_value=True,
                metavar="triple",
            ),
            Option(
                ("--select-target", "--interactive-target"),
                dest="select_target",
                help="Interactively choose target platform",
                default=False,
            ),
            Option(
                ("--asset",),
                dest="asset",
                help="Filter GitHub release assets by name substring",
                takes_value=True,
                metavar="name",
            ),
        ),
    )

    app.command(
        Command(
            name="install",
            aliases=("i",),
            help="Install from registry or GitHub repository",
            usage="install [OPTIONS] <package|owner/repo> [version]",
            args=(
                Argument("package", "Registry package name or owner/repo"),
                Argument("version", "Version or release tag", required=False),
            ),
            handler=lazy("ship.cli.commands.pkgs:run_install"),
        ),
        Command(
            name="remove",
            aliases=("rm", "uninstall"),
            help="Uninstall a package and remove binary symlinks",
            usage="remove <package>",
            args=(Argument("package", "Installed package name"),),
            handler=lazy("ship.cli.commands.pkgs:run_remove"),
        ),
        Command(
            name="rollback",
            help="Restore a package's previous version or a saved command",
            usage="rollback (<package>|--binary <command>) [--yes]",
            args=(Argument("package", "Package to roll back", required=False),),
            opts=(
                Option(
                    ("--binary",),
                    dest="binary",
                    help="Restore a backed-up command by name",
                    takes_value=True,
                    metavar="command",
                ),
                Option(
                    ("--yes",),
                    dest="yes",
                    help="Skip confirmation prompts",
                    default=False,
                ),
            ),
            handler=lazy("ship.cli.commands.pkgs:run_rollback"),
        ),
        Command(
            name="repatch",
            aliases=("repair",),
            help="Reapply patches to an installed package without downloading",
            usage="repatch <package>",
            args=(Argument("package", "Installed package name"),),
            handler=lazy("ship.cli.commands.pkgs:run_repatch"),
        ),
        Command(
            name="update",
            aliases=("u",),
            help="Update packages, registry index, or ship itself",
            usage="update [package|registry|self]",
            args=(
                Argument(
                    "target",
                    "Package name, 'registry', or 'self'",
                    required=False,
                ),
            ),
            handler=lazy("ship.cli.commands.update:run_update"),
        ),
        Command(
            name="check-upstream",
            aliases=("outdated",),
            help="Check if upstream releases are newer than registry",
            usage="check-upstream <package>",
            args=(Argument("package", "Registry package name"),),
            handler=lazy("ship.cli.commands.update:run_check_upstream"),
        ),
        Command(
            name="search",
            help="Search registry for packages",
            usage="search [query]",
            args=(Argument("query", "Name or description filter", required=False),),
            handler=lazy("ship.cli.commands.pkgs:run_search"),
        ),
        Command(
            name="info",
            help="Display details and targets for a package",
            usage="info <package>",
            args=(Argument("package", "Registry package name"),),
            handler=lazy("ship.cli.commands.pkgs:run_info"),
        ),
        Command(
            name="list",
            aliases=("ls",),
            help="List installed packages in store",
            usage="list",
            handler=lazy("ship.cli.commands.pkgs:run_list"),
        ),
        Command(
            name="publish",
            help="Submit a release to the central registry",
            usage="publish <owner/repo> [tag]",
            args=(
                Argument("repo", "GitHub repository (owner/repo)"),
                Argument("tag", "Release tag (default: latest)", required=False),
            ),
            handler=lazy("ship.cli.commands.publish:run_publish"),
        ),
        Command(
            name="auth",
            help="Log in to GitHub or show the authenticated account",
            usage="auth [status|login]",
            args=(
                Argument(
                    "action",
                    "status (default) or login",
                    required=False,
                ),
            ),
            handler=lazy("ship.cli.commands.publish:run_auth"),
        ),
        Command(
            name="admin",
            help="Review, accept, or reject package submissions (admins only)",
            usage="admin <prs|review|accept|reject> [PR] [--reason TEXT] [--yes]",
            args=(
                Argument("action", "prs | review | accept | reject"),
                Argument("pr", "Pull request number", required=False),
            ),
            opts=(
                Option(
                    ("--reason",),
                    dest="reason",
                    help="Rejection reason text",
                    takes_value=True,
                    metavar="text",
                ),
                Option(
                    ("--yes",),
                    dest="yes",
                    help="Skip confirmation prompts",
                    default=False,
                ),
            ),
            handler=lazy("ship.cli.commands.admin:run_admin"),
        ),
        Command(
            name="self-update",
            aliases=("upgrade-self",),
            help="Upgrade ship to the latest version",
            usage="self-update",
            handler=lazy("ship.cli.commands.update:run_self_update"),
        ),
        Command(
            name="clean",
            help="Purge download caches and backups",
            usage="clean",
            handler=lazy("ship.cli.commands.pkgs:run_clean"),
        ),
    )
    return app
