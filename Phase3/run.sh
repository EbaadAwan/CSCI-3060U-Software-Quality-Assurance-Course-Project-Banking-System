#!/bin/bash

mkdir -p outputs

for f in inputs/*.in.txt; do
  t=$(basename "$f" .in.txt)

  python3 ../Phase2.py ../accounts.txt "outputs/$t.atf.txt" \
    < "$f" \
    > "outputs/$t.out.txt"

  echo "ran $t"
done