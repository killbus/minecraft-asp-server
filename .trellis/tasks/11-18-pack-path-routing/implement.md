# Implementation plan

## 1. Scene: input surface

File: `scripts/scenes/frpc-shared-tcp.sh`

- Add `PACKS_ENDPOINT=` and `PACKS_PREFIX=${MUX_PACKS_PREFIX:-/packs/}`.
- Parse `--packs HOST:PORT`.
- Extend `usage`.
- Add `is_packs_prefix()` beside `is_endpoint()`.
- Validate, all exit 2 with one line:
  - endpoint not `HOST:PORT`;
  - port equal to `LISTEN`, `JAVA`, `BEDROCK`, `TLS_LISTEN`, or `LAN_JAVA`;
  - prefix fails `is_packs_prefix`;
  - `--packs` with a hand-written `--haproxy-config` (the scene does not own
    that file).
- No `--tls-cert` requirement: this route is plaintext by construction.
- After the mux is confirmed listening, when enabled, probe
  `endpoint_listen_check "$PACKS_ENDPOINT"` and print one warning if nothing
  listens; do not fail the start.

## 2. Scene: configuration output

File: `scripts/scenes/frpc-shared-tcp.sh`, `print_haproxy_config`

- Accept endpoint and prefix as `${10}`/`${11}`.
- Disabled branch: byte-identical, including ACL order.
- Enabled branch adds, after the existing `is_java` ACLs:

  ```
  acl is_packs payload(0,<len>) -m beg "GET <prefix>"
  ```

  then, before `use_backend geyser_signaling ...`:

  ```
  use_backend packs if is_packs
  ```

  and at the end of the file:

  ```
  backend packs
      server packs <endpoint>
  ```

- `<len>` is `${#_ph_packs_match}` in POSIX sh.
- Thread both values through the two `generate_haproxy_config` call sites.

## 3. Tests

`tests/test_frpc_shared_tcp_scene.py`, dry-run only:

- enabled: exact ACL text, `use_backend packs` before the geyser line, backend
  block present, `mc_shared` still `mode tcp`.
- custom prefix changes both the ACL string and its length.
- disabled (with and without `--tls-cert`): exact same config as HEAD.
- refusals: bad endpoint, each colliding port, four bad prefixes, and
  `--haproxy-config`.

## 4. Documentation

- `docs/ASP-SOP.md` 10.1: subsection describing the plaintext route, its
  ordering before the Geyser line, the `GET`/offset-0 limitation, and rollback.
- `docs/ASP-SOP.md` endpoint table: packs backend row.
- `docs/PAPER-WORLD-SOP.md` §4: `http://<public-ip>:<port>/packs/pack-a.zip`.
- `scripts/serve_packs.py` + both launchers: map `server/packs/` to the URL
  prefix, because the backend sees the forwarded path unchanged.

## 5. Verification

```sh
python -m unittest tests.test_frpc_shared_tcp_scene -v
sh scripts/scenes/frpc-shared-tcp.sh up --config <cfg> --packs 127.0.0.1:8000 --dry-run
```

Deployed host: `haproxy -c -f`, then `curl` the pack through 127.0.0.1:25566
and through the public address; sha256 must match `72cafcfa...28bb`.

## 6. Rollback

Drop `--packs` and `reload`. The generated file returns to the frozen shape.
