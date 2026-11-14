#!/usr/bin/env python3
"""Keep the provider-issued certificate for a bound name where HAProxy reads it.

    NATFRP_TOKEN=... python3 scripts/sync_natfrp_cert.py \
        --domain <sub>.<account>.nyat.app \
        --out ~/asp-frpcs/tls/<sub>.<account>.nyat.app.pem \
        --reload-command 'sh scripts/scenes/frpc-shared-tcp.sh reload'

The optional shared-TCP scene in section 10.1 of docs/ASP-SOP.md can carry
Java Minecraft and Bedrock NetherNet signalling on one public port, but only
when it terminates TLS itself, and that needs the certificate and private
key for the name players type. A name bound to a NATFRP tunnel cannot get a
certificate from anywhere else: its DNS belongs to the provider, so no ACME
challenge can be run for it. The provider's own client (frpc) is handed that
certificate and key and terminates TLS with them inside `auto_https`, which
is exactly what keeps Java off such a port. The provider's API hands the
same pair to the account holder instead, and its documentation asks for the
written files to be updated when the certificate is renewed, so this script
is the supported arrangement rather than a workaround.

What it does, in order:

  1. reads the account's domain records and certificate state
     (GET /domain/get) and refuses a name the token's account does not own,
  2. asks the API for a renewal (POST /domain/cert) when the certificate
     expires inside the window, and waits for the new one,
  3. downloads certificate and private key (GET /domain/cert) only when the
     certificate really changed, because the API asks callers not to
     download it repeatedly,
  4. proves the certificate and the key belong together before anything is
     replaced, and (when openssl is installed) that the certificate covers
     the name it was fetched for,
  5. writes both into one PEM, the form a single HAProxy
     `bind ... ssl crt <file>` line reads, through a temporary file and a
     rename so a reader never sees half a file, and with no group or other
     permission bits, because the file holds a private key,
  6. runs --reload-command, and only when the file changed.

The certificate holds a private key and is not core content: it lives with
the frpc configuration outside the repository, outside the backup classes
of section 1 and the acceptance checklist of section 5. Exit codes: 0 the
file is current or was updated, 1 the API, the certificate or a command
failed, 2 usage.
"""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request


API = "https://api.natfrp.com/v4"
TOKEN_ENV = "NATFRP_TOKEN"
# The provider's edge bans some client signatures outright: the User-Agent
# urllib sends by default answers HTTP 403 "error code: 1010" before the
# request ever reaches the API, whatever the key is. This script says who it
# is instead, which the edge lets through.
USER_AGENT = "asp-natfrp-cert-sync/1.0"
RENEW_WINDOW_DAYS = 7
DAY = 86400.0
CREATED_SUFFIX = ".created"


class Failure(Exception):
    """A condition that stops the run with a message and exit code 1."""


def parse_arguments(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--domain", required=True, help="bound name the certificate is served for")
    parser.add_argument("--out", required=True, help="combined PEM to write (chain, then key)")
    parser.add_argument(
        "--token-file",
        help=f"file holding the account API key (default: the {TOKEN_ENV} environment variable)",
    )
    parser.add_argument("--api", default=API, help=f"API base (default: {API})")
    parser.add_argument(
        "--renew-window-days",
        type=int,
        default=RENEW_WINDOW_DAYS,
        help=f"ask for a renewal this many days before expiry (default: {RENEW_WINDOW_DAYS})",
    )
    parser.add_argument(
        "--issue-timeout",
        type=float,
        default=300.0,
        help="seconds to wait for a renewed certificate (default: 300)",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=15.0,
        help="seconds between checks while waiting for a renewed certificate (default: 15)",
    )
    parser.add_argument(
        "--reload-command",
        help="command to run after the PEM changed, e.g. a HAProxy reload or a tmux respawn",
    )
    parser.add_argument(
        "--timeout", type=float, default=30.0, help="seconds per API call (default: 30)",
    )
    parser.add_argument("--dry-run", action="store_true", help="report, download, write nothing")
    return parser.parse_args(argv)


def out_name_note(out_path, domain):
    """One line when `--out` does not carry the name it holds a certificate for.

    Advisory, not a refusal: a short file name works, and the certificate is
    checked against `--domain` before anything is written. But these files
    share one directory, several accounts can have the same subdomain, and the
    file holds a private key, so the file name is the only thing that keeps
    two accounts' `1-mc` apart at a glance.
    """
    name = Path(out_path).name
    if domain in name:
        return None
    return (
        f"note     {name} does not name {domain}; with more than one account in one "
        f"directory the convention is <sub>.<account>.pem, so {domain}.pem"
    )


def token_from(arguments):
    if arguments.token_file:
        try:
            token = Path(arguments.token_file).read_text(encoding="utf-8").strip()
        except OSError as error:
            raise Failure(f"cannot read the token file: {error}") from error
    else:
        token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        raise Failure(
            f"no API key: set {TOKEN_ENV} or pass --token-file. The key is in the panel "
            "on the account page, and it must not be given as a command line argument "
            "(every process on the host can read those)."
        )
    return token


def call(api_base, path, token, fields=None, timeout=30.0):
    """One API call. `fields` makes it a POST with a form body."""
    url = f"{api_base.rstrip('/')}{path}"
    body = urllib.parse.urlencode(fields).encode() if fields is not None else None
    request = urllib.request.Request(url, data=body)
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Accept", "application/json")
    request.add_header("User-Agent", USER_AGENT)
    if body is not None:
        request.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as answer:
            text = answer.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        raise Failure(f"{path}: {describe_error(error)}") from error
    except urllib.error.URLError as error:
        raise Failure(f"{path}: cannot reach {url}: {error.reason}") from error
    try:
        return json.loads(text)
    except ValueError as error:
        raise Failure(f"{path}: the API did not answer with JSON: {text[:200]!r}") from error


def describe_error(error):
    """What the API answered, including a body that is not JSON.

    A 403 can come from the API itself or from a gateway in front of it, and
    the two are told apart by the body: one carries the provider's own `msg`,
    the other is a page. Neither is worth losing, so the body is quoted.
    """
    try:
        body = error.read().decode("utf-8", "replace")
    except OSError:
        body = ""
    try:
        payload = json.loads(body)
    except ValueError:
        payload = None
    if isinstance(payload, dict) and payload.get("msg"):
        return f"HTTP {error.code}, API code {payload.get('code')}: {payload['msg']}"
    detail = " ".join(body.split())[:160]
    return f"HTTP {error.code}" + (f": {detail}" if detail else "")


def account_names(document):
    """Every fully qualified name the account can serve, with its record."""
    account = document.get("domain") or ""
    names = {}
    for record in document.get("records") or []:
        relative = record.get("rr")
        if relative in (None, "", "@"):
            full = account
        else:
            full = f"{relative}.{account}"
        names[full] = record
    return account, names


def record_for(document, domain):
    account, names = account_names(document)
    if domain in names:
        return names[domain]
    known = ", ".join(sorted(names)) or "none"
    raise Failure(
        f"{domain} is not a record of the account that owns {account or 'the account domain'} "
        f"(the account has: {known}). The API key and the name have to belong together."
    )


def certificate_state(document):
    state = document.get("ssl") or {}
    created = state.get("created") or 0
    expires = state.get("expires") or 0
    return int(created), int(expires)


def needs_renewal(expires, now, window_days):
    """True when the certificate expires inside the window, or already has."""
    if expires <= 0:
        return False
    return expires < now + window_days * DAY


def describe_expiry(expires, now):
    if expires <= 0:
        return "expiry unknown, the certificate is still being issued"
    days = (expires - now) / DAY
    if days < 0:
        return f"expired {-days:.0f} days ago"
    return f"in {days:.0f} days"


def day(stamp):
    return time.strftime("%Y-%m-%d", time.gmtime(stamp))


def request_renewal(api_base, token, created, timeout):
    return call(
        api_base, "/domain/cert", token,
        fields={"created": created, "renew": "true"}, timeout=timeout,
    )


def wait_for_new_certificate(api_base, token, previous, timeout, interval, call_timeout):
    """Poll until the account has a certificate that is not the old one."""
    deadline = time.monotonic() + timeout
    while True:
        document = call(api_base, "/domain/get", token, timeout=call_timeout)
        created, expires = certificate_state(document)
        if created and created != previous:
            return document
        if time.monotonic() >= deadline:
            raise Failure(
                f"the renewed certificate did not appear within {timeout:.0f}s; "
                "run this again later, the API keeps the old certificate until the new one is issued"
            )
        time.sleep(interval)


def download_certificate(api_base, token, created, timeout):
    query = urllib.parse.urlencode({"created": created})
    return call(api_base, f"/domain/cert?{query}", token, timeout=timeout)


def pem_pair(payload):
    certificate = (payload.get("cert") or "").strip()
    key = (payload.get("key") or "").strip()
    if "BEGIN CERTIFICATE" not in certificate:
        raise Failure("the API answered without a certificate")
    if "PRIVATE KEY" not in key:
        raise Failure("the API answered without a private key")
    return certificate, key


def check_pair(certificate, key, work_dir):
    """Refuse a certificate and a key that do not belong together.

    ssl loads both and fails when they do not match, which is the same check
    HAProxy would pass on the file much later, and much less visibly.
    """
    cert_file = Path(work_dir) / "cert.pem"
    key_file = Path(work_dir) / "key.pem"
    cert_file.write_bytes((certificate + "\n").encode())
    key_file.write_bytes((key + "\n").encode())
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    try:
        context.load_cert_chain(certfile=str(cert_file), keyfile=str(key_file))
    except (ssl.SSLError, OSError, ValueError) as error:
        raise Failure(f"the certificate and the private key do not belong together: {error}") from error


def openssl():
    """The openssl command line, on PATH or inside a POSIX shell (Git Bash)."""
    if shutil.which("openssl"):
        return ["openssl"]
    shell = shutil.which("sh")
    if shell:
        probe = subprocess.run(
            [shell, "-c", "command -v openssl"], capture_output=True, text=True, check=False,
        )
        if probe.returncode == 0:
            return [shell, "-c", 'exec openssl "$@"', "openssl"]
    return None


def covers(name, entry):
    """True when one certificate name covers the requested host name."""
    entry = entry.strip().lower().rstrip(".")
    name = name.strip().lower().rstrip(".")
    if entry == name:
        return True
    if not entry.startswith("*."):
        return False
    suffix = entry[2:]
    if not name.endswith("." + suffix):
        return False
    return "." not in name[: -len(suffix) - 1]


def certificate_names(certificate, work_dir, domain):
    """Report the names the leaf covers, and refuse a certificate for another name.

    Best effort: without openssl the names cannot be read out of the PEM
    with the standard library, so the check is reported as skipped. The
    account check in record_for() has already tied the name to the token.
    """
    command = openssl()
    if not command:
        return "not checked (openssl is not installed)"
    leaf = Path(work_dir) / "leaf.pem"
    leaf.write_bytes((certificate + "\n").encode())
    result = subprocess.run(
        command + ["x509", "-in", str(leaf), "-noout", "-ext", "subjectAltName"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        return f"not checked (openssl failed: {result.stderr.strip()[:120]})"
    names = re.findall(r"DNS:([^,\s]+)", result.stdout)
    if not names:
        return "none (the certificate carries no subject alternative name)"
    if not any(covers(domain, entry) for entry in names):
        raise Failure(
            f"the certificate covers {', '.join(names)} and not {domain}; "
            "the API key and the name have to belong together"
        )
    return ", ".join(names)


def compose(certificate, key):
    """One file: the chain first, then the key (what `ssl crt` reads)."""
    return f"{certificate.strip()}\n{key.strip()}\n"


def replace_file(path, text, mode=0o600):
    """Write `text` to `path` through a rename, with `mode` and nothing else.

    The PEM holds a private key, so the permissions are set explicitly rather
    than left to the umask: a 0644 file would hand the key to every account on
    the host, which is the opposite of keeping it out of the repository.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    # os.open applies the umask, os.chmod does not: only the second one makes
    # the mode independent of the operator's shell.
    handle = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(handle, "wb") as stream:
        stream.write(text.encode())
    os.chmod(temporary, mode)
    os.replace(temporary, path)


def recorded_created(path):
    try:
        return Path(str(path) + CREATED_SUFFIX).read_text(encoding="utf-8").strip()
    except OSError:
        return None


def run_reload(command):
    """Run the operator's own reload command, through the shell they wrote it for."""
    result = subprocess.run(command, shell=True, capture_output=True, text=True, check=False)
    detail = (result.stdout + result.stderr).strip()
    if result.returncode != 0:
        raise Failure(
            f"the file is updated, but the reload command failed with {result.returncode}"
            + (f": {detail[:400]}" if detail else "")
        )
    return detail


def main(argv):
    arguments = parse_arguments(argv)
    try:
        if arguments.renew_window_days < 0:
            raise Failure("--renew-window-days cannot be negative")
        token = token_from(arguments)
        document = call(arguments.api, "/domain/get", token, timeout=arguments.timeout)
        account, _ = account_names(document)
        record = record_for(document, arguments.domain)
        created, expires = certificate_state(document)
        now = time.time()

        print(f"account  {account}")
        print(f"domain   {arguments.domain} (record {record.get('rr')!r}, tunnel {record.get('tunnel')})")
        note = out_name_note(arguments.out, arguments.domain)
        if note:
            print(note, file=sys.stderr)
        if not created:
            raise Failure(
                "this account has no certificate yet: start frpc once with auto_https on so "
                "the first one is issued, then run this again"
            )
        print(f"cert     issued {day(created)}, expires {day(expires)} ({describe_expiry(expires, now)})")

        if needs_renewal(expires, now, arguments.renew_window_days):
            print(f"renew    inside {arguments.renew_window_days} days of expiry, asking the API")
            request_renewal(arguments.api, token, created, arguments.timeout)
            document = wait_for_new_certificate(
                arguments.api, token, created, arguments.issue_timeout,
                arguments.poll_interval, arguments.timeout,
            )
            created, expires = certificate_state(document)
            print(f"renew    reissued {day(created)}, expires {day(expires)}")

        current = Path(arguments.out).is_file() and recorded_created(arguments.out) == str(created)
        if current:
            print("action   none: the file already holds this certificate")
            return 0

        print("action   download")
        certificate, key = pem_pair(download_certificate(arguments.api, token, created, arguments.timeout))
        with tempfile.TemporaryDirectory() as work_dir:
            check_pair(certificate, key, work_dir)
            print("pair     the certificate and the private key match")
            print(f"names    {certificate_names(certificate, work_dir, arguments.domain)}")

        if arguments.dry_run:
            print(f"would    write {arguments.out} and run the reload command")
            return 0
        replace_file(arguments.out, compose(certificate, key))
        replace_file(str(arguments.out) + CREATED_SUFFIX, str(created) + "\n")
        print(f"out      {arguments.out} updated")

        if arguments.reload_command:
            detail = run_reload(arguments.reload_command)
            print(f"reload   ran: {detail[:200]}" if detail else "reload   ran")
        else:
            print("reload   not requested: reload or restart whatever reads the file")
        return 0
    except Failure as failure:
        print(f"FAIL     {failure}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
