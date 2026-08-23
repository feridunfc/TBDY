#!/usr/bin/env bash
set +e
mkdir -p local_out

python -m compileall -q tbdy_engine tests tools > /tmp/vs4a_compile.log 2>&1
compile_rc=$?

python -m pytest -q tests/regulatory/test_structural_system.py tests/regulatory/test_vs4a_source_authority.py > /tmp/vs4a_targeted.log 2>&1
targeted_rc=$?

python -m pytest -q tests/regulatory/test_source_authority.py > /tmp/vs4a_f09.log 2>&1
f09_rc=$?

python -m pytest -q tests/regulatory/test_f0_semantic_contracts.py tests/regulatory/test_f0_registry.py tests/regulatory/test_f0_1_kernel.py > /tmp/vs4a_f0_core.log 2>&1
f0_core_rc=$?

python -m pytest -q tests/regulatory/test_f0_2_beam_min_width_parity.py tests/regulatory/test_f0_7_concrete_material_min_strength.py tests/regulatory/test_f0_8_b1_geometry_parity.py tests/regulatory/test_f0_8_wall_pack_a_geometry_parity.py tests/regulatory/test_seismic_response.py > /tmp/vs4a_f0_parity.log 2>&1
f0_parity_rc=$?

python -m pytest -q tests/regulatory > /tmp/vs4a_regulatory_all.log 2>&1
regulatory_all_rc=$?

python -m pytest -q tests/member_geometry > /tmp/vs4a_member_geometry.log 2>&1
member_geometry_rc=$?

python -m pytest -q tests/c13_1 > /tmp/vs4a_c13_1.log 2>&1
c13_1_rc=$?

python -m pytest -q tests/c13_4_p1 tests/c13_4_p2 > /tmp/vs4a_c13_4.log 2>&1
c13_4_rc=$?

python -m pytest -q tests/wall_inventory/test_wall_inventory_slice_1.py > /tmp/vs4a_wall_inventory.log 2>&1
wall_inventory_rc=$?

python -m pytest -q tests/wall_geometry/test_wall_check_pack_a.py tests/wall_geometry/test_wall_pack_a_catalog_contract.py > /tmp/vs4a_wall_a.log 2>&1
wall_a_rc=$?

python -m pytest -q tests/wall_geometry/test_wall_check_pack_b.py tests/wall_geometry/test_wall_pack_b_source_contracts.py > /tmp/vs4a_wall_b.log 2>&1
wall_b_rc=$?

python -m pytest -q tests/wall_geometry/test_wall_check_pack_c.py tests/wall_geometry/test_wall_pack_c_source_contracts.py > /tmp/vs4a_wall_c.log 2>&1
wall_c_rc=$?

python tools/run_offline_product_acceptance.py --out /tmp/vs4a_offline_acceptance > /tmp/vs4a_offline.log 2>&1
offline_rc=$?

python -m pytest -q > /tmp/vs4a_full_current.log 2>&1
current_full_rc=$?

git worktree add --detach /tmp/vs4a_frozen_base f774726513a81edaadb2a5d897539575538e0cd0 > /tmp/vs4a_worktree.log 2>&1
worktree_rc=$?
if [ "$worktree_rc" -eq 0 ]; then
  (
    cd /tmp/vs4a_frozen_base
    python -m pytest -q > /tmp/vs4a_full_base.log 2>&1
  )
  base_full_rc=$?
else
  base_full_rc=99
  cp /tmp/vs4a_worktree.log /tmp/vs4a_full_base.log
fi

grep -E '^(ERROR|FAILED) ' /tmp/vs4a_full_current.log | sort > /tmp/vs4a_current_failset.txt || true
grep -E '^(ERROR|FAILED) ' /tmp/vs4a_full_base.log | sort > /tmp/vs4a_base_failset.txt || true
diff -u /tmp/vs4a_base_failset.txt /tmp/vs4a_current_failset.txt > /tmp/vs4a_frozen_base_diff.txt
failset_diff_rc=$?
if [ "$current_full_rc" -ne "$base_full_rc" ]; then
  frozen_compare_rc=1
else
  frozen_compare_rc=$failset_diff_rc
fi

summary() {
  local file="$1"
  grep -E '([0-9]+ passed|[0-9]+ failed|[0-9]+ error|[0-9]+ skipped|[0-9]+ xfailed|[0-9]+ xpassed)' "$file" | tail -1
}

{
  echo "VS4A_ACCEPTANCE_TRIGGER_HEAD=${GITHUB_SHA}"
  echo "FROZEN_BASE=f774726513a81edaadb2a5d897539575538e0cd0"
  echo "COMPILEALL_EXIT=$compile_rc"
  echo "VS4A_TARGETED_EXIT=$targeted_rc"
  echo "F09_SOURCE_AUTHORITY_EXIT=$f09_rc"
  echo "F0_CORE_EXIT=$f0_core_rc"
  echo "F0_PARITY_EXIT=$f0_parity_rc"
  echo "REGULATORY_ALL_EXIT=$regulatory_all_rc"
  echo "MEMBER_GEOMETRY_EXIT=$member_geometry_rc"
  echo "C13_1_EXIT=$c13_1_rc"
  echo "C13_4_P1_P2_EXIT=$c13_4_rc"
  echo "WALL_INVENTORY_EXIT=$wall_inventory_rc"
  echo "WALL_PACK_A_EXIT=$wall_a_rc"
  echo "WALL_PACK_B_EXIT=$wall_b_rc"
  echo "WALL_PACK_C_EXIT=$wall_c_rc"
  echo "OFFLINE_PRODUCT_ACCEPTANCE_EXIT=$offline_rc"
  echo "CURRENT_FULL_PYTEST_EXIT=$current_full_rc"
  echo "FROZEN_BASE_FULL_PYTEST_EXIT=$base_full_rc"
  echo "FROZEN_BASE_FAILSET_COMPARE_EXIT=$frozen_compare_rc"
  echo
  echo "--- AUTHORITY-BOUNDARY FINGERPRINT DELTA ---"
  cat /tmp/vs4a_fingerprint_delta.txt
  echo
  echo "--- EXACT FRESH COUNTS ---"
  echo "VS4A_TARGETED: $(summary /tmp/vs4a_targeted.log)"
  echo "F09_SOURCE_AUTHORITY: $(summary /tmp/vs4a_f09.log)"
  echo "F0_CORE: $(summary /tmp/vs4a_f0_core.log)"
  echo "F0_PARITY: $(summary /tmp/vs4a_f0_parity.log)"
  echo "REGULATORY_ALL: $(summary /tmp/vs4a_regulatory_all.log)"
  echo "MEMBER_GEOMETRY: $(summary /tmp/vs4a_member_geometry.log)"
  echo "C13_1: $(summary /tmp/vs4a_c13_1.log)"
  echo "C13_4_P1_P2: $(summary /tmp/vs4a_c13_4.log)"
  echo "WALL_INVENTORY: $(summary /tmp/vs4a_wall_inventory.log)"
  echo "WALL_PACK_A: $(summary /tmp/vs4a_wall_a.log)"
  echo "WALL_PACK_B: $(summary /tmp/vs4a_wall_b.log)"
  echo "WALL_PACK_C: $(summary /tmp/vs4a_wall_c.log)"
  echo "CURRENT_FULL_PYTEST: $(summary /tmp/vs4a_full_current.log)"
  echo "FROZEN_BASE_FULL_PYTEST: $(summary /tmp/vs4a_full_base.log)"
  echo
  echo "--- TARGETED TAIL ---"
  tail -100 /tmp/vs4a_targeted.log
  echo
  echo "--- F0.9 TAIL ---"
  tail -80 /tmp/vs4a_f09.log
  echo
  echo "--- OFFLINE PRODUCT ACCEPTANCE TAIL ---"
  tail -40 /tmp/vs4a_offline.log
  echo
  echo "--- CURRENT FULL PYTEST TAIL ---"
  tail -80 /tmp/vs4a_full_current.log
  echo
  echo "--- FROZEN BASE FULL PYTEST TAIL ---"
  tail -80 /tmp/vs4a_full_base.log
  echo
  echo "--- FROZEN BASE FAILSET DIFF ---"
  cat /tmp/vs4a_frozen_base_diff.txt
} > local_out/vs4a_acceptance_result.txt

cat local_out/vs4a_acceptance_result.txt
printf '%s\n' \
  "$compile_rc $targeted_rc $f09_rc $f0_core_rc $f0_parity_rc $regulatory_all_rc $member_geometry_rc $c13_1_rc $c13_4_rc $wall_inventory_rc $wall_a_rc $wall_b_rc $wall_c_rc $offline_rc $current_full_rc $base_full_rc $frozen_compare_rc" \
  > /tmp/vs4a_exit_codes

git worktree remove /tmp/vs4a_frozen_base --force >/dev/null 2>&1 || true

focused_rc=0
for rc in "$compile_rc" "$targeted_rc" "$f09_rc" "$f0_core_rc" "$f0_parity_rc" "$regulatory_all_rc" "$member_geometry_rc" "$c13_1_rc" "$c13_4_rc" "$wall_inventory_rc" "$wall_a_rc" "$wall_b_rc" "$wall_c_rc" "$offline_rc" "$frozen_compare_rc"; do
  if [ "$rc" -ne 0 ]; then
    focused_rc=1
  fi
done
if [ "$current_full_rc" -ne "$base_full_rc" ]; then
  focused_rc=1
fi
exit "$focused_rc"
