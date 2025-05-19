#!/bin/bash

Time=(4 11 14)
Chart=(1 5 12)
Math=(2 8 20 22 39 49 50 53 56 58 60 70 73 74 81 95 98 103)
Lang=(7 16 20 22 35 39 41 43 45 46 50 51 55 59 61)

identifiers=("Chart" "Time" "Math" "Lang")

# For each project in Defects4J...
for identifier in "${identifiers[@]}"; do
    eval "current=(\"\${${identifier}[@]}\")"
    # ... Check out every bug
    for bug_id in "${current[@]}"; do
        echo "Checking out $identifier-$bug_id"
        defects4j checkout -p "$identifier" -v "${bug_id}b" -w "./d4j-subjects_no_instr/${identifier}_${bug_id}_no_instr"

        # Copy config.json from instrumented subject to not-instrumented subject
        src="./d4j-subjects_no_instr/configs/${identifier}_${bug_id}_config.json"
        dest="./d4j-subjects_no_instr/${identifier}_${bug_id}_no_instr/config.json"
        echo "Copy $src to $dest"
        cp "$src" "$dest"

        # Copy bug report file to correct location
        src_bug="./d4j-subjects_no_instr/bug-reports/${identifier}_${bug_id}_bug_report.txt"
        dest_bug="./d4j-subjects_no_instr/${identifier}_${bug_id}_no_instr/bug-report.txt"
        echo "Copy $src_bug to $dest_bug"
        cp "$src_bug" "$dest_bug"
    done
done

