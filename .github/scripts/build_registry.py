#!/usr/bin/env python3
import json
import os
import sys

PKGS_DIR = "pkgs"
REGISTRY_FILE = "registry.json"


def main():
    if not os.path.isdir(PKGS_DIR):
        print(f"Error: Directory '{PKGS_DIR}' does not exist.", file=sys.stderr)
        sys.exit(1)

    packages = {}
    total_versions = 0

    # Read each sharded package definition
    for fname in sorted(os.listdir(PKGS_DIR)):
        if not fname.endswith(".json"):
            continue
        pkg_name = fname[:-5]
        file_path = os.path.join(PKGS_DIR, fname)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                packages[pkg_name] = data
                total_versions += len(data.get("versions", {}))
        except Exception as e:
            print(f"Warning: Failed to parse '{file_path}': {e}", file=sys.stderr)

    registry = {
        "repository": "https://github.com/SSL-ACTX/ship-pm",
        "packages": packages,
    }

    # Write unified registry.json
    with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, sort_keys=False)
        f.write("\n")

    print(
        f"Successfully compiled {len(packages)} packages ({total_versions} total versions) into {REGISTRY_FILE}"
    )


if __name__ == "__main__":
    main()
