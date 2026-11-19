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
                dest="_global_help",
                help="Print help information and exit",
                default=False,
            ),
            Option(
                ("-V", "--version"),
                dest="_global_version",
                help="Print version info and exit",
                default=False,
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
            opts=(
                Option(
                    ("-f", "--force"),
                    dest="force",
                    help="Force reinstallation even if already installed",
                    default=False,
                ),
                Option(
                    ("--clean",),
                    dest="clean",
                    help="Clean existing store directory before install",
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
                    ("--select-target",),
                    dest="select_target",
                    help="Interactively choose target platform",
                    default=False,
                ),
                Option(
                    ("--deb", "--ubuntu"),
                    dest="deb",
                    help="Install directly from Ubuntu deb registry",
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
            handler=lazy("ship.cli.commands.pkgs:run_install"),
        ),
        Command(
            name="remove",
            aliases=("rm", "uninstall", "purge"),
            help="Uninstall a package and remove binary symlinks",
            usage="remove [OPTIONS] <package>",
            args=(Argument("package", "Installed package name"),),
            opts=(
                Option(
                    ("--purge",),
                    dest="purge",
                    help="Also remove package archives from download cache",
                    default=False,
                ),
            ),
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
            aliases=("u", "upgrade"),
            help="Update packages, registry index, deb cache, or ship itself",
            usage="update [package|registry|deb|self] [--all|--github]",
            args=(
                Argument(
                    "target",
                    "Package name, 'registry', 'deb', or 'self'",
                    required=False,
                ),
            ),
            opts=(
                Option(
                    ("--all", "-a"),
                    dest="all",
                    help="Include GitHub-installed packages when checking for updates",
                    default=False,
                ),
                Option(
                    ("--github", "-g"),
                    dest="github",
                    help="Only check GitHub-installed packages for updates",
                    default=False,
                ),
            ),
            handler=lazy("ship.cli.commands.update:run_update"),
        ),
        Command(
            name="check-upstream",
            aliases=("outdated",),
            help="Check if upstream releases are newer than registry or installed packages",
            usage="check-upstream [package]",
            args=(
                Argument(
                    "package", "Registry package name or omit for all", required=False
                ),
            ),
            handler=lazy("ship.cli.commands.update:run_check_upstream"),
        ),
        Command(
            name="search",
            help="Search registry for packages",
            usage="search [query] [--deb|--all]",
            args=(Argument("query", "Name or description filter", required=False),),
            opts=(
                Option(
                    ("--deb", "--ubuntu"),
                    dest="deb",
                    help="Search Debian/Ubuntu packages index only",
                    default=False,
                ),
                Option(
                    ("--all",),
                    dest="all",
                    help="Search both core registry and secondary deb packages",
                    default=False,
                ),
            ),
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
            help="Review submissions or trigger upstream sync (admins only)",
            usage="admin <sync|prs|review|accept|reject> [target/PR] [--reason TEXT] [--yes]",
            args=(
                Argument("action", "sync | prs | review | accept | reject"),
                Argument("pr", "Package name (for sync) or PR number", required=False),
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
            name="clean",
            help="Purge download caches, backups, and orphaned store directories",
            usage="clean [--all] [--store]",
            opts=(
                Option(
                    ("--all",),
                    dest="all",
                    help="Purge cache, backups, and orphaned store directories",
                    default=False,
                ),
                Option(
                    ("--store", "--orphans"),
                    dest="store",
                    help="Clean untracked/orphaned package directories in store",
                    default=False,
                ),
            ),
            handler=lazy("ship.cli.commands.pkgs:run_clean"),
        ),
        Command(
            name="doctor",
            help="Diagnose and repair broken packages, missing linkers, and dangling symlinks",
            usage="doctor [--heal]",
            opts=(
                Option(
                    ("--heal",),
                    dest="heal",
                    help="Automatically repair detected issues and relink packages",
                    default=False,
                ),
            ),
            handler=lazy("ship.cli.commands.pkgs:run_doctor"),
        ),
        Command(
            name="export",
            help="Package a store directory into a distributable offline bundle",
            usage="export <package> [output_bundle]",
            args=(
                Argument("package", "Installed package name"),
                Argument("output", "Output bundle path (.ship.tar.gz)", required=False),
            ),
            handler=lazy("ship.cli.commands.pkgs:run_export"),
        ),
        Command(
            name="import",
            help="Install a pre-packaged offline ship bundle directly into store",
            usage="import <bundle>",
            args=(Argument("bundle", "Path to .ship.tar.gz bundle"),),
            handler=lazy("ship.cli.commands.pkgs:run_import"),
        ),
        Command(
            name="sandbox",
            aliases=("box",),
            help="Manage isolated sandbox areas for safe testing and execution",
            usage="sandbox [action] [target] [args...] [--keep] [--yes]",
            args=(
                Argument(
                    "action",
                    "list | create | enter | install | run | test | clean (default: list)",
                    required=False,
                ),
                Argument(
                    "target",
                    "Sandbox name, package name, or command to run",
                    required=False,
                ),
                Argument(
                    "cmd",
                    "Command arguments, package flags, or sub-arguments",
                    required=False,
                    variadic=True,
                ),
            ),
            opts=(
                Option(
                    ("--keep",),
                    dest="keep",
                    help="Keep ephemeral test sandbox instead of auto-destroying",
                    default=False,
                ),
                Option(
                    ("--yes", "-y"),
                    dest="yes",
                    help="Skip confirmation when cleaning all sandboxes",
                    default=False,
                ),
            ),
            handler=lazy("ship.cli.commands.pkgs:run_sandbox"),
        ),
        Command(
            name="call",
            help="Execute an internal ship package entrypoint",
            usage="call <module:function> [args...]",
            args=(
                Argument(
                    "entrypoint",
                    "Module and function, e.g. ship.packages.odin:run_odin",
                ),
                Argument(
                    "args",
                    "Arguments to pass to the function",
                    required=False,
                    variadic=True,
                ),
            ),
            handler=lazy("ship.cli.commands.pkgs:run_call"),
        ),
        Command(
            name="cache",
            aliases=("api-cache",),
            help="Manage the GitHub API response cache",
            usage="cache [clear|stats]",
            args=(
                Argument(
                    "action",
                    "stats (default) | clear",
                    required=False,
                ),
            ),
            handler=lazy("ship.cli.commands.pkgs:run_cache"),
        ),
    )
    return app
