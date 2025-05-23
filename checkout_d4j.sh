#!/bin/bash

Time=(4 11 14)
Chart=(1 5 12)
Math=(2 8 20 22 39 49 50 53 56 58 60 70 73 74 81 95 98 103)
Lang=(7 16 20 22 35 39 41 43 45 46 50 51 55 59 61)

identifiers=("Lang" "Chart" "Time" "Math")

for identifier in "${identifiers[@]}"; do
    eval "current=(\"\${${identifier}[@]}\")"
    for bug_id in "${current[@]}"; do
        echo "=== Checking out $identifier-$bug_id ==="
        workdir="./d4j-subjects_no_instr/${identifier}_${bug_id}_no_instr"
        difffile="./d4j-subjects_no_instr/diffs/${identifier}_${bug_id}.diff"

        # 1) Checkout
        defects4j checkout -p "$identifier" -v "${bug_id}b" -w "$workdir"

        # 2) Copy config.json
        src_cfg="./d4j-subjects_no_instr/configs/${identifier}_${bug_id}_config.json"
        dest_cfg="$workdir/config.json"
        echo "Copy $src_cfg --> $dest_cfg"
        cp "$src_cfg" "$dest_cfg"

        # 3) Copy bug-report.txt
        src_bug="./d4j-subjects_no_instr/bug-reports/${identifier}_${bug_id}_bug_report.txt"
        dest_bug="$workdir/bug-report.txt"
        echo "Copy $src_bug --> $dest_bug"
        cp "$src_bug" "$dest_bug"

        # 4) Apply patch if it exists
        difffile="d4j-subjects_no_instr/diffs/${identifier}_${bug_id}.diff"
        if [ -f "$difffile" ]; then
          echo "Apply patch $difffile"
          patch -p1 -d "$workdir" < "$difffile" \
            && echo "  --> Patch applied successfully" \
            || echo "  --> Patch failed!"
        fi
        echo
    done
done

