# Package patches

Ship keeps package-specific adjustments separate from installation and platform
compatibility code. Add an optional Python module at
`ship/patches/<package_name>.py`, using a lowercase module name and underscores
for hyphens. For example, `tool-name` maps to `ship/patches/tool_name.py`.

Modules may define either or both install-stage callbacks:

```python
def post_extract(*, install_dir, target_key):
    """Adjust extracted package files before ship discovers commands."""


def pre_link(*, install_dir, target_key):
    """Perform package-specific setup immediately before command linking."""
```

Callbacks run for registry installs and direct GitHub release installs. They
receive the package's versioned store directory and selected target key. Keep
changes inside `install_dir` so removal and upgrades remain scoped to that
package version.

A patch module may also define `runtime_wrapper_hooks(binary_name)`, returning
`(before_exec, after_exec)` shell snippets. Platform adapters can include
these in generated launchers when that platform needs package-specific runtime
behavior. This is intended for exceptional compatibility cases; ordinary
environment behavior belongs in `ship/patchers/`.

For cases where one package command needs a distinct invocation path, a module
may define `runtime_exec_command(binary_name, real_binary, target_key)` and
return a shell command string, or `None` to use the platform default.

The registry's existing `hooks.post_install` shell command remains supported
for compatibility. New package-specific behavior should use a package patch
module so it can be reviewed and version controlled with ship.
