#!/bin/bash

# Tests whose expected outputs include "Login successful ..." while most other tests do not.
LOGIN_EXPECT_TESTS=("FE-L02" "FE-L03" "FE-L04" "FE-L06" "FE-L07")

is_login_expect_test() {
  local t="$1"
  for x in "${LOGIN_EXPECT_TESTS[@]}"; do
    if [ "$x" = "$t" ]; then
      return 0
    fi
  done
  return 1
}

for expected in expected/*.out.txt; do
  t=$(basename "$expected" .out.txt)
  out="outputs/$t.out.txt"

  if [ ! -f "$out" ]; then
    echo "FAIL $t (missing output file)"
    continue
  fi

  if is_login_expect_test "$t"; then
    # Compare after removing any "Login successful ..." lines in BOTH files.
    diff -u <(grep -v '^Login successful' "$expected") <(grep -v '^Login successful' "$out") \
      && echo "PASS $t" || echo "FAIL $t"
  else
    # For all other tests, ignore "Login successful ..." in output only.
    # (Expected usually doesn't have it; your program may print it.)
    diff -u "$expected" <(grep -v '^Login successful' "$out") \
      && echo "PASS $t" || echo "FAIL $t"
  fi
done