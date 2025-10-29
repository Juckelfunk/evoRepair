#!/bin/bash
#
# Usage: ./script.sh [IN_BASE] [OUT_BASE]
#   IN_BASE  = where your configs/ bug-reports/ diffs/ live  (default: ./d4j-subjects_no_instr)
#   OUT_BASE = where to create the *_no_instr checkouts      (default: ./d4j-subjects_no_instr_work)

IN_BASE="${1:-./d4j-subjects_no_instr}"
OUT_BASE="${2:-./d4j-subjects_no_instr_work}"

Time=(4 11 14)
Chart=(1 5 12)
Math=(2 8 20 22 39 49 50 53 56 58 60 70 73 74 81 95 98 103)
Lang=(7 16 20 22 35 39 41 43 45 46 50 51 55 59 61)

identifiers=("Lang" "Chart" "Time" "Math")

for identifier in "${identifiers[@]}"; do
    eval "current=(\"\${${identifier}[@]}\")"
    for bug_id in "${current[@]}"; do
        echo "=== Checking out $identifier-$bug_id ==="
        workdir="$OUT_BASE/${identifier}_${bug_id}_no_instr"
        difffile="$IN_BASE/diffs/${identifier}_${bug_id}.diff"

        # 1) Checkout into OUT_BASE
        defects4j checkout -p "$identifier" -v "${bug_id}b" -w "$workdir"

        # 2) Copy config.json from IN_BASE to new workdir
        src_cfg="$IN_BASE/configs/${identifier}_${bug_id}_config.json"
        dest_cfg="$workdir/config.json"
        echo "Copy $src_cfg → $dest_cfg"
        cp "$src_cfg" "$dest_cfg"

        # 3) Copy bug-report.txt from IN_BASE
        src_bug="$IN_BASE/bug-reports/${identifier}_${bug_id}_bug_report.txt"
        dest_bug="$workdir/bug-report.txt"
        echo "Copy $src_bug → $dest_bug"
        cp "$src_bug" "$dest_bug"

        # 4) Apply patch from IN_BASE if it exists
        if [ -f "$difffile" ]; then
          echo "Apply patch $difffile"
          patch -p1 -d "$workdir" < "$difffile" \
            && echo "  → Patch applied successfully" \
            || echo "  → Patch FAILED!"
        fi
        echo
    done
done

