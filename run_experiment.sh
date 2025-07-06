#!/bin/bash

files=(
#   "Chart_1"
   "Chart_5"
#  "Chart_12"
   "Lang_7"
   "Lang_16"
   "Lang_20"
   "Lang_22"
#   "Lang_35"
   "Lang_39"
  "Lang_41"
   "Lang_43"
   "Lang_45"
   "Lang_46"
#  "Lang_50"
   "Lang_51"
   "Lang_55"
   "Lang_59"
#  "Lang_61"
#  "Math_2"
   "Math_8"
  "Math_20"
#  "Math_22"
  "Math_39"
   "Math_49"
   "Math_50"
#   "Math_53"
  "Math_56"
   "Math_58"
   "Math_60"
   "Math_70"
   "Math_73"
  "Math_74"
#  "Math_81"
   "Math_95"
   "Math_98"
   "Math_103"
   "Time_4"
   "Time_11"
  "Time_14"
)

for f in "${files[@]}"; do
  echo "Running subject: $f"
  python3 ./Repair.py --oracle-extraction --llm-generation phi4_docker --llm-selection phi4_docker --random-seed 100 --config "d4j-subjects_no_instr/${f}_no_instr/config.json"
  pkill -9 -f java
done
mv output Base/Phi121

for f in "${files[@]}"; do
  echo "Running subject: $f"
  python3 ./Repair.py --oracle-extraction --llm-generation phi4_docker --llm-selection phi4_docker --random-seed 200 --config "d4j-subjects_no_instr/${f}_no_instr/config.json"
  pkill -9 -f java
done
mv output Base/Phi122

for f in "${files[@]}"; do
  echo "Running subject: $f"
  python3 ./Repair.py --oracle-extraction --llm-generation phi4_docker --llm-selection phi4_docker --random-seed 300 --config "d4j-subjects_no_instr/${f}_no_instr/config.json"
  pkill -9 -f java
done
mv output Base/Phi123



for f in "${files[@]}"; do
  echo "Running subject: $f"
  python3 ./Repair.py --oracle-extraction --llm-generation 2_0_flash --llm-selection 2_0_flash --random-seed 100 --config "d4j-subjects_no_instr/${f}_no_instr/config.json"
  pkill -9 -f java
done
mv output Base/Flash121

for f in "${files[@]}"; do
  echo "Running subject: $f"
  python3 ./Repair.py --oracle-extraction --llm-generation 2_0_flash --llm-selection 2_0_flash --random-seed 200 --config "d4j-subjects_no_instr/${f}_no_instr/config.json"
  pkill -9 -f java
done
mv output Base/Flash122

for f in "${files[@]}"; do
  echo "Running subject: $f"
  python3 ./Repair.py --oracle-extraction --llm-generation 2_0_flash --llm-selection 2_0_flash --random-seed 300 --config "d4j-subjects_no_instr/${f}_no_instr/config.json"
  pkill -9 -f java
done
mv output Base/Flash123



for f in "${files[@]}"; do
  echo "Running subject: $f"
  python3 ./Repair.py --oracle-extraction --llm-generation 1_5_pro --llm-selection 1_5_pro --random-seed 100 --config "d4j-subjects_no_instr/${f}_no_instr/config.json"
  pkill -9 -f java
done
mv output Base/Pro121

for f in "${files[@]}"; do
  echo "Running subject: $f"
  python3 ./Repair.py --oracle-extraction --llm-generation 1_5_pro --llm-selection 1_5_pro --random-seed 200 --config "d4j-subjects_no_instr/${f}_no_instr/config.json"
  pkill -9 -f java
done
mv output Base/Pro122

for f in "${files[@]}"; do
  echo "Running subject: $f"
  python3 ./Repair.py --oracle-extraction --llm-generation 1_5_pro --llm-selection 1_5_pro --random-seed 300 --config "d4j-subjects_no_instr/${f}_no_instr/config.json"
  pkill -9 -f java
done
mv output Base/Pro123
