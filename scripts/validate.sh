#!/usr/bin/env bash
# Local validation only: never plan/apply, contact a cluster, publish or push.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo"
python_bin="${PYTHON_BIN:-python3}"
gitops_root="${GITOPS_ROOT:-$repo/../tech-challenge-fase-4-gitops}"
"$python_bin" -m unittest discover -s scripts/tests -p 'test_*.py' -v
# Check source files only; do not format ignored environment parameters.
while IFS= read -r -d '' file; do
  [[ -f "$file" ]] && terraform fmt -check "$file"
done < <(git ls-files -z 'infra/*.tf' 'infra/**/*.tf')
for root in backend core platform; do
  terraform -chdir="infra/environments/homolog/$root" validate
done
"$python_bin" "$gitops_root/scripts/validate_structure.py"
docker compose config --quiet
git diff --check
git -C "$gitops_root" diff --check
printf '%s\n' 'Local preparation checks passed. This is not live deployment verification.'
