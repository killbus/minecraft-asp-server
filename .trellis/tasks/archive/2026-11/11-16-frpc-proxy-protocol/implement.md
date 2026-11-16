# Implement

Ownership: this task edits the scene, the probe, their tests, and SOP 10.1.
Nothing else (`server/`, `~/asp-frpcs`, the LoginTo fork) is in scope.

## Steps

1. `scripts/scenes/frpc-shared-tcp.sh`
   - parse `--proxy-protocol` next to the other options (help text, validation,
     duplicate handling as the neighbours do);
   - `print_haproxy_config`: append ` accept-proxy` to the `bind` line of
     `frontend mc_shared` and ` send-proxy-v2` to the `server paper` line of
     `backend java` when the switch is on; leave every other line untouched;
   - `usage()` and the header comment: mention the switch, that the port then
     only accepts PROXY-protocol clients, and that frpc must send it.
2. `scripts/probe_public_entry.py`
   - new `--proxy-protocol` flag that prefixes the `--local-mux` connections
     with a PROXY v2 header (12-byte signature + version/command/family +
     length + src/dst addr+port). Keep it local-mux only and say so in help.
3. Tests
   - `tests/test_frpc_shared_tcp_scene.py`: a case for each generated line with
     the switch, and keep the existing plain-config equality test green;
     a misuse case (e.g. `--proxy-protocol` with `--dry-run` is fine, but an
     unknown `--proxy-protocol=x` value is not) - match the file's existing
     `assert_rejected` idiom.
   - `tests/smoke_frpc_shared_tcp_tls.py`: run the existing checks once with the
     switch and PROXY v2 headers, plus the current plain run. Reuse its
     `generate_haproxy_config`/`check_*` helpers; do not duplicate the harness.
   - `tests/test_probe_public_entry.py`: header bytes for the new flag.
   - check `tests/test_frpc_shared_tcp_mux_lifetime.py` and
     `tests/test_frpc_shared_tcp_reload.py`: they exercise lifecycle, not the
     generated text - only touch them if they actually assert the `bind` or
     `server paper` lines.
4. `docs/ASP-SOP.md` 10.1: a new subsection with the four switches
   (frpc `proxy_protocol_version = v2` / `transport.proxyProtocolVersion`,
   scene `--proxy-protocol`, Paper `proxies.proxy-protocol: true`, Geyser
   `advanced.java.use-haproxy-protocol: true`), the local-connection caveat,
   the acceptance line and the rollback.

## Validation

```sh
python -m unittest tests.test_frpc_shared_tcp_scene -v
python tests/smoke_frpc_shared_tcp_tls.py            # needs haproxy on PATH
python -m unittest tests.test_probe_public_entry -v
python -m unittest discover -s tests
```

If `haproxy` is not on PATH the smoke test skips itself; say so in the report
instead of claiming it ran.

## Review gates

- Plain mode byte-for-byte unchanged (R2) - this is the one that protects the
  running host.
- The four switches in SOP 10.1 must match the code and the natfrp page
  (`research/natfrp-realip.md`), or the next operator will mis-wire them.
