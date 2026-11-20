# Execution

1. Implement shared raw host-schema parsing, consumer isolation and legacy URL
   compatibility. Update both direct launchers, the example and regression tests.
2. Update current contract docs/specs and separate-file migration instructions.
3. Independent scoped review with renderer, pack-selector, launcher and scene
   tests; fix mechanical errors and capture evidence.
4. Commit a fixup for 942b8ce, autosquash from parent616d07d, retaining independent
   map-doc and task commits. Record completed task without introducing a separate
   visible correction commit. Update journal references to rewritten commits.
5. Check clean tree, exact remote old HEAD cd40327bdd560b62c5d184201887ebe619790c55,
   then publish branch feat/single-world-start with explicit force-with-lease.
   Give safe pull/rebase instructions for either previously pulled state.

All changes stay in the existing single-world-start worktree. Check artifacts
are isolated under .tmp. No destructive production action or unstated branch
rewrite is authorized.
