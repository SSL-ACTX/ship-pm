#!/bin/sh
set -eu

BASE="$(cd "$(dirname "$0")" && pwd)"
export PM_ROOT="$BASE/pm_root"
export PM_BIN_DIR="$BASE/fake_bin"
export PM_REGISTRY_URL="file://$BASE/registry_server/registry.json"
export PM_REGISTRY_CACHE="$PM_ROOT/cache/registry.json"
PM="$BASE/pm"

echo "=========================================================="
echo " Starting Full-Feature PM Validation in Isolated fake_env "
echo "=========================================================="

echo -e "\n--> 1. Version check"
"$PM" version

echo -e "\n--> 2. Help display"
"$PM" help | head -n 8

echo -e "\n--> 3. Central Registry Sync"
"$PM" registry update

echo -e "\n--> 4. Package Search"
"$PM" search
"$PM" search alpha

echo -e "\n--> 5. Package Info (before install)"
"$PM" info tool-alpha

echo -e "\n--> 6. Install Specific Version (tool-alpha@1.0.0)"
"$PM" install tool-alpha 1.0.0
"$BASE/fake_bin/alpha"
"$PM" info tool-alpha

echo -e "\n--> 7. List Installed Packages"
"$PM" list

echo -e "\n--> 8. Update to Latest Version (tool-alpha -> 1.2.0)"
"$PM" update tool-alpha
"$BASE/fake_bin/alpha"

echo -e "\n--> 9. Install Package with Post-Install Hook (tool-beta)"
"$PM" install tool-beta
"$BASE/fake_bin/beta"
test -f "$PM_ROOT/store/tool-beta@0.5.0/hook.log"
echo "Verified hook.log:"
cat "$PM_ROOT/store/tool-beta@0.5.0/hook.log"

echo -e "\n--> 10. Update All Packages ('pm update')"
"$PM" update

echo -e "\n--> 11. Verify Cache Clean"
ls -la "$PM_ROOT/cache"/*.tar.gz || true
"$PM" clean
if ls "$PM_ROOT/cache"/*.tar.gz 2>/dev/null; then
  echo "Error: cache not cleaned"
  exit 1
fi
echo "Cache successfully cleared."

echo -e "\n--> 12. Checksum Integrity Enforcement"
# Inject corrupted hash in registry cache
python3 -c "
import json
with open('$PM_REGISTRY_CACHE', 'r') as f:
    d = json.load(f)
d['packages']['tool-alpha']['versions']['1.2.0']['targets']['aarch64-linux-musl']['sha256'] = 'badhash0000000000000000000000000000000000000000000000000000000000'
with open('$PM_REGISTRY_CACHE', 'w') as f:
    json.dump(d, f)
"
if "$PM" install tool-alpha 1.2.0; then
  echo "FAIL: Expected checksum failure!"
  exit 1
fi
echo "SUCCESS: Bad checksum aborted installation correctly."
"$PM" registry update

echo -e "\n--> 13. Package Removal"
"$PM" remove tool-alpha
if [ -e "$BASE/fake_bin/alpha" ]; then
  echo "FAIL: Public symlink still exists!"
  exit 1
fi
echo "Symlink successfully removed."
"$PM" list

echo -e "\n--> 15. Direct GitHub URL Installation ('pm install <github_url>')"
MOCK_API_DIR="$BASE/mock_gh"
mkdir -p "$MOCK_API_DIR/testorg"
cp "$MOCK_API_DIR/release.json" "$MOCK_API_DIR/testorg/sample-tool"
export PM_GITHUB_API_BASE="file://$MOCK_API_DIR"

"$PM" install "https://github.com/testorg/sample-tool"
"$BASE/fake_bin/sample-tool"
"$PM" list | grep -q "sample-tool"
"$PM" remove sample-tool
[ ! -e "$BASE/fake_bin/sample-tool" ]
echo "GitHub direct installation and cleanup verified."

echo -e "\n=========================================================="
echo " ALL TESTS PASSED! Full PM feature set is verified!      "
echo "=========================================================="
