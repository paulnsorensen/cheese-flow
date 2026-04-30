# Shell / Bash De-slop Patterns

Language-specific patterns the `age-deslop` dim looks for in shell script diffs.
Read alongside `protocol.md` (cross-language patterns).

---

## 1. Unquoted Variables

The #1 shell bug. Breaks on spaces, globs, and empty values.

**What to look for:** `$var` or `$array` without quotes in contexts where
word splitting or glob expansion would occur.

```bash
# SLOP
for file in $files; do
    rm $file
done

# CLEAN
for file in "${files[@]}"; do
    rm -- "$file"
done
```

Quote every variable expansion: `"$var"`, `"${array[@]}"`, `"$(command)"`.
The `--` stops option parsing (protects against filenames starting with `-`).

---

## 2. Missing or Incomplete `set -euo pipefail`

AI scripts either omit strict mode entirely or use partial `set -e` without
`-u` and `-o pipefail`.

**What to look for:** Scripts with `set -e` only; scripts with no `set` at
all; pipes through `jq`/`yq`/`grep` without `pipefail`.

```bash
# SLOP — no strict mode
#!/bin/bash
cd /some/directory    # Might fail silently
rm -rf build/         # Now you're deleting in the wrong place

# SLOP — partial strict mode (common AI output)
#!/bin/bash
set -e
yq '.items[]' file.yaml | while read -r item; do  # yq failure silently ignored
    process "$item"
done

# CLEAN
#!/bin/bash
set -euo pipefail
cd /some/directory
rm -rf build/
```

- `-e`: Exit on error
- `-u`: Error on undefined variables (catches typos like `$UESR`)
- `-o pipefail`: Pipeline fails if any command fails

All three flags together. `set -e` alone is a half-measure.

---

## 3. Parsing `ls` Output

`ls` output is not machine-readable. Filenames with spaces, newlines,
or special characters break everything.

**What to look for:** `for file in $(ls *.txt)` or similar.

```bash
# SLOP
for file in $(ls *.txt); do
    process "$file"
done

# CLEAN — glob directly
for file in *.txt; do
    [[ -f "$file" ]] && process "$file"
done
```

---

## 4. Useless Use of `cat`

**What to look for:** `cat file | grep`, `cat file | wc -l` — piping into
commands that accept file arguments directly.

```bash
# SLOP
cat file.txt | grep "pattern"
cat file.txt | wc -l

# CLEAN
grep "pattern" file.txt
wc -l < file.txt
```

---

## 5. Backticks Instead of `$()`

Backticks don't nest and are harder to read.

**What to look for:** Backtick command substitution in new code.

```bash
# SLOP
result=`command`
nested=`echo \`date\``

# CLEAN
result=$(command)
nested=$(echo "$(date)")
```

---

## 6. `[ ]` Instead of `[[ ]]`

`[[ ]]` is safer: no word splitting, supports regex, no quoting surprises.

**What to look for:** Single-bracket test expressions in bash scripts.

```bash
# SLOP
if [ $var = "value" ]; then
if [ -z $maybe_empty ]; then

# CLEAN
if [[ "$var" == "value" ]]; then
if [[ -z "${maybe_empty:-}" ]]; then
```

---

## 7. Hardcoded Paths

AI writes absolute paths or assumes CWD.

**What to look for:** Absolute paths to the author's home directory; relative
paths that assume the script runs from a specific directory.

```bash
# SLOP
source /home/user/project/lib/utils.sh
config_file=./config.yaml

# CLEAN
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/utils.sh"
config_file="${SCRIPT_DIR}/config.yaml"
```

---

## 8. Not Using `readonly` for Constants

**What to look for:** Constants assigned with `=` that could be accidentally
overwritten later in the script.

```bash
# SLOP
MAX_RETRIES=3
BASE_URL="https://api.example.com"

# CLEAN
readonly MAX_RETRIES=3
readonly BASE_URL="https://api.example.com"
```

---

## 9. Using `echo` for Error Messages

Errors go to stderr, not stdout.

**What to look for:** `echo "Error: ..."` followed by `exit 1` in error paths.

```bash
# SLOP
echo "Error: file not found"
exit 1

# CLEAN
echo >&2 "Error: file not found"
exit 1

# Or with a helper
die() { echo >&2 "$@"; exit 1; }
die "file not found"
```
