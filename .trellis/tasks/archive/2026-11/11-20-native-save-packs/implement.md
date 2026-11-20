# Execution

1. Verify native pack/cache behavior and original map provenance in research.
2. Implement the optional pack policy helper and connect both launchers.
3. Test global fallback, save override, null, invalid policy, repeated selection,
   Java-properties parsing, unchanged source/save state, and native arguments.
4. Prepare a disposable full Trials copy, boot pinned Paper on an unused loopback
   port, inspect errors and metadata, then stop gracefully. Prepare an untouched
   original copy and document reproducing it from the existing archive; keep
   test mutations out of that deployment copy.
5. Update operator docs/specs and independently review scoped changes. Report
   actual validation limits, especially gameplay and client reconnect testing.

Validation uses `python -B -m unittest discover -s tests -p
'test_resource_pack_selection.py'` and the existing launcher/scene tests.
Test scratch remains under `.tmp/`. Root runtime and user services are protected.
No production SSH or branch replacement. Policy removal restores native behavior.
