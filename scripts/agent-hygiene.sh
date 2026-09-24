#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

changed_files() {
    {
        git diff --name-only -z --diff-filter=ACMR HEAD
        git ls-files --others --exclude-standard -z
    }
}

changed_files |
while IFS= read -r -d '' file; do
    [ -f "$file" ] || continue
    case "$file" in
        *.py|*.pyi|*.toml|*.yml|*.yaml|*.json|*.js|*.jsx|*.ts|*.tsx|*.css|*.html|*.sh)
            perl -0777 -pi -e '
                s/\r\n?/\n/g;
                s/[ \t]+(?=\n|\z)//g;
                $_ .= "\n" if length($_) && $_ !~ /\n\z/;
            ' "$file"
            ;;
        *.md)
            perl -0777 -pi -e '
                s/\r\n?/\n/g;
                $_ .= "\n" if length($_) && $_ !~ /\n\z/;
            ' "$file"
            ;;
    esac
done

git diff --check
