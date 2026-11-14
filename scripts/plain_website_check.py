#!/usr/bin/env python3
"""Check the public entry with a throwaway website, without the server.

    python3 scripts/plain_website_check.py --host <name> --port <remote-port>

Nothing of the server is in the path: a throwaway HAProxy serves a
throwaway directory on the same local port the mux uses, the tunnel is
expected to point at that port, and the only question is whether the
public name shows the page. A page that arrives publicly with no Geyser,
no Paper and no mux involved isolates the provider, the tunnel and this
machine from everything the server does - and a page that does not arrive
means the fault is not in the server either.

Prerequisites: `haproxy` on PATH, and frpc running with a tunnel whose
localPort is --listen. The ASP scene binds the same port, so stop it first
and run frpc alone, for example
`tmux new -d -s plain-frpc 'frpc -c ~/asp-frpcs/frpc.toml'`.

Exit codes: 0 the page arrived over the public name, 1 it did not, 2 bad
usage.
"""

import argparse
import http.client
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import uuid


sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe_public_entry as probe  # noqa: E402  (same directory, by design)


HTTP_REQUEST = "GET / HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n"


def haproxy_config(listen, backend):
    """A very ordinary reverse proxy in front of a very ordinary website."""
    return f"""# Written by scripts/plain_website_check.py; a throwaway reverse proxy in
# front of a throwaway directory, with nothing of the server in the path.
global
    maxconn 64

defaults
    mode http
    timeout connect 5s
    timeout client 30s
    timeout server 30s

frontend plain_website
    bind {listen}
    default_backend plain_website_files

backend plain_website_files
    server files {backend}
"""


def endpoint(text):
    host, separator, port = text.rpartition(":")
    if not separator or not host or not port.isdigit() or not 1 <= int(port) <= 65535:
        raise argparse.ArgumentTypeError(f"not HOST:PORT: {text}")
    return host, int(port)


def port_is_free(host, port):
    with socket.socket() as probe_socket:
        # No SO_REUSEADDR: on Windows it would let this bind a port another
        # process is already listening on, and the check would answer "free".
        try:
            probe_socket.bind((host, port))
        except OSError:
            return False
    return True


def free_port():
    with socket.socket() as probe_socket:
        probe_socket.bind(("127.0.0.1", 0))
        return probe_socket.getsockname()[1]


def wait_for_port(host, port, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), 0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def local_get(host, port, timeout):
    connection = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        connection.request(
            "GET", "/", headers={"Host": f"{host}:{port}", "Connection": "close"},
        )
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


def classify(response, marker):
    if marker.encode() in response:
        return "OK", "the page came back"
    return probe.describe_http(response)


def stop(process):
    process.send_signal(signal.SIGTERM)
    try:
        process.wait(5)
    except subprocess.TimeoutExpired:
        process.kill()
        try:
            process.wait(5)
        except subprocess.TimeoutExpired:
            pass


def remove_directory(directory):
    """Remove the work directory, which Windows refuses while it is busy."""
    for _ in range(20):
        if not directory.exists():
            return
        shutil.rmtree(directory, ignore_errors=True)
        time.sleep(0.1)
    if directory.exists():
        print(f"note: could not remove {directory}; remove it by hand")


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", required=True, help="public entry host")
    parser.add_argument("--port", type=int, required=True, help="public entry port")
    parser.add_argument(
        "--listen", type=endpoint, default=endpoint("127.0.0.1:25566"),
        help="local port the tunnel forwards to, HOST:PORT (default 127.0.0.1:25566)",
    )
    parser.add_argument("--timeout", type=float, default=8.0, help="seconds per check (default 8)")
    parser.add_argument("--keep", action="store_true", help="keep the temporary directory")
    arguments = parser.parse_args(argv)

    listen_host, listen_port = arguments.listen
    if not port_is_free(listen_host, listen_port):
        print(f"FAIL: {listen_host}:{listen_port} is already in use.")
        print("      The ASP scene binds it: stop it first, or pass a --listen that")
        print("      matches the local port your tunnel forwards to.")
        return 1
    haproxy = shutil.which("haproxy")
    if not haproxy:
        print("FAIL: haproxy is not on PATH")
        return 1

    temporary = Path(tempfile.mkdtemp(prefix="asp-plain-website-"))
    marker = f"PLAIN-WEBSITE-OK-{uuid.uuid4().hex}"
    website = temporary / "www"
    website.mkdir()
    (website / "index.html").write_text(f"<html><body>{marker}</body></html>\n", encoding="utf-8")
    backend_port = free_port()
    backend = f"127.0.0.1:{backend_port}"
    config = temporary / "haproxy.cfg"
    config.write_text(haproxy_config(f"{listen_host}:{listen_port}", backend), encoding="utf-8")
    print(f"work dir: {temporary}")
    print(f"marker:   {marker}")
    print(f"website:  {backend}")
    print(f"proxy:    {listen_host}:{listen_port}")

    processes = []
    try:
        checked = subprocess.run(
            [haproxy, "-c", "-f", str(config)], capture_output=True, text=True,
        )
        if checked.returncode != 0:
            print("FAIL: haproxy rejected the generated configuration")
            print((checked.stdout + checked.stderr).strip())
            return 1

        files = subprocess.Popen(
            [sys.executable, "-B", "-m", "http.server", str(backend_port), "--bind", "127.0.0.1"],
            cwd=website, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        processes.append(files)
        log = (temporary / "haproxy.log").open("wb")
        haproxy_process = subprocess.Popen(
            [haproxy, "-db", "-f", str(config)], stdout=log, stderr=subprocess.STDOUT,
        )
        processes.append(haproxy_process)
        log.close()

        if not wait_for_port(listen_host, listen_port):
            print("FAIL: the proxy never accepted connections on its listen port")
            return 1

        status, body = local_get(listen_host, listen_port, arguments.timeout)
        local_ok = marker.encode() in body
        print(f"local    http://{listen_host}:{listen_port}/  {'OK' if local_ok else 'FAILED'}"
              f" (HTTP {status})")
        if not local_ok:
            print("      the proxy and the website do not work on their own; stop here")
            return 1

        request = HTTP_REQUEST.format(host=arguments.host).encode()
        results = {}
        try:
            response = probe.exchange(arguments.host, arguments.port, request, arguments.timeout)
        except OSError as error:
            label, why = "NO DATA", f"{type(error).__name__}: {error}"
        else:
            label, why = classify(response, marker)
        results["http"] = label
        print(f"public   http://{arguments.host}:{arguments.port}/  {label:<8} {why}")

        handshake, detail, response = probe.probe_tls(
            arguments.host, arguments.port, arguments.host, arguments.timeout,
            verify=False, request=request,
        )
        results["https"] = None
        results["trusted"] = None
        print(f"public   https handshake: {'ok' if handshake else 'FAILED'}: {detail}")
        if handshake:
            label, why = classify(response, marker)
            results["https"] = label
            print(f"public   https://{arguments.host}:{arguments.port}/  {label:<8} {why}")
            trusted, reason, _ = probe.probe_tls(
                arguments.host, arguments.port, arguments.host, arguments.timeout, verify=True,
            )
            results["trusted"] = trusted
            print(f"public   certificate: {'TRUSTED' if trusted else 'UNTRUSTED'}: {reason}")

        print()
        print("verdict")
        print("  local proxy + website: ok")
        if results["https"] == "OK":
            print("  the public name serves this page over HTTPS: the provider, the")
            print("  tunnel and the local port are all fine, so anything still broken")
            print("  is in the server and not in this path")
            if results["trusted"] is False:
                print("  the certificate is not trusted for that name, which a Bedrock")
                print("  client may refuse even though the path works")
            return 0
        if results["http"] == "OK":
            print("  the public name serves this page over plain HTTP only: TLS is")
            print("  either not terminated for this name, or not offered on this port")
            return 0
        if results["http"] == "EDGE":
            print("  the datacenter still answers instead of the tunnel: this name is")
            print("  not bound to the tunnel yet, so nothing here can be reached")
            return 1
        print("  the page never arrived: the tunnel is not delivering this port to")
        print("  this machine, which is independent of the server")
        return 1
    finally:
        for process in reversed(processes):
            stop(process)
        if arguments.keep:
            print(f"kept: {temporary}")
        elif temporary.name.startswith("asp-plain-website-") and temporary.is_dir():
            remove_directory(temporary)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
