#!/usr/bin/env python3
"""Probe a live public frpc entry and report which layer answered.

    python3 scripts/probe_public_entry.py --host <node> --port <remote-port>

This is an operator diagnostic, not a test: what it measures is whether the
node and the datacenter in front of it carry the port, which nothing local
can stand in for. Run it while the scene is up, from the machine that owns
the tunnel or from anywhere else that is not behind a proxy with a fake-IP
resolver. It opens the public TCP port three times, because the three things
that share it start differently:

  1. a Minecraft legacy ping (`0xFE 0x01`), which is what a Java client
     sends - a server answer proves the whole path,
  2. a plain HTTP GET, which is what NetherNet signalling starts with,
  3. a TLS handshake with SNI followed by the same HTTP request inside it,
     which is what a Bedrock client starts with when it is given a host
     name; the handshake is also repeated with certificate verification, so
     "the path is broken", "nothing answers inside TLS" and "the
     certificate is untrusted" cannot be confused.

`--local-mux HOST:PORT` repeats the Java and HTTP probes against a local
mux for comparison. With `--proxy-protocol` those two connections start
with a PROXY protocol v2 header, which is what a mux started with the
scene's `--proxy-protocol` requires; the public half is left alone,
because there frpc, not the client, writes the header.

Exit codes: 0 the Minecraft probe reached a server, 1 it did not, 2 bad
usage.
"""

import argparse
import ipaddress
import socket
import ssl
import struct
import sys
import time


JAVA_PING = b"\xfe\x01"
HTTP_REQUEST = "GET / HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n"
# ASCII markers of the datacenter page that answers unlisted hosts on some
# Chinese nodes ("please have the datacenter whitelist your domain").
EDGE_MARKERS = (b"0632idc.com", b"/sorry.png", b"is not allowed", b"ICP")
EDGE_TITLE = b"<title>"

# PROXY protocol version 2: the 12-byte signature,
# then version/command, family/protocol, a 16-bit length, and the address
# block that length counts. frpc writes this header ahead of every connection
# it opens once the tunnel sets proxy_protocol_version, and a mux bind with
# `accept-proxy` refuses a connection that does not start with it.
PROXY_V2_SIGNATURE = b"\r\n\r\n\x00\r\nQUIT\n"
PROXY_V2_VERSION_COMMAND = 0x21  # version 2, PROXY (a connection, not LOCAL)
PROXY_V2_FAMILY_PROTOCOL = 0x11  # AF_INET over STREAM


def resolve(host):
    try:
        return sorted({item[4][0] for item in socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)})
    except OSError as error:
        return [f"unresolved: {error}"]


def fake_ip(addresses):
    for address in addresses:
        try:
            if ipaddress.ip_address(address) in ipaddress.ip_network("198.18.0.0/15"):
                return True
        except ValueError:
            continue
    return False


def proxy_v2_header(source, destination):
    """A PROXY protocol v2 header for one TCP/IPv4 connection.

    The shape frpc sends when a tunnel sets `proxy_protocol_version = "v2"`:
    12 signature bytes, version/command, family/protocol, the length of the
    address block, then the IPv4 addresses and ports. The checksum kwarg is
    left off, which is legal and what HAProxy's `accept-proxy` reads.
    """
    source_host, source_port = source
    destination_host, destination_port = destination
    addresses = (
        socket.inet_aton(source_host)
        + socket.inet_aton(destination_host)
        + struct.pack("!HH", source_port, destination_port)
    )
    return (
        PROXY_V2_SIGNATURE
        + bytes([PROXY_V2_VERSION_COMMAND, PROXY_V2_FAMILY_PROTOCOL])
        + struct.pack("!H", len(addresses))
        + addresses
    )


def request_over(connection, payload, read=4096):
    """Send one payload and collect the answer, including over TLS."""
    connection.sendall(payload)
    chunks = []
    try:
        while sum(len(chunk) for chunk in chunks) < read:
            chunk = connection.recv(read)
            if not chunk:
                break
            chunks.append(chunk)
    except (socket.timeout, ConnectionResetError):
        pass
    return b"".join(chunks)


def exchange(host, port, payload, timeout, read=4096):
    with socket.create_connection((host, port), timeout) as connection:
        connection.settimeout(timeout)
        return request_over(connection, payload, read)


def looks_like_edge_page(response):
    lowered = response.lower()
    if any(marker.lower() in lowered for marker in EDGE_MARKERS):
        return True
    return EDGE_TITLE.lower() in lowered and b"apache" in lowered


def describe_java(response):
    if not response:
        return "NO DATA", "the connection was closed or reset without an answer"
    if response[:1] == b"\xff":
        return "JAVA", f"legacy ping answer, {len(response)} bytes"
    if b"<html" in response.lower() or b"<!" in response[:16]:
        return "EDGE", "HTML answered instead of the game: something in front of the tunnel"
    return "OTHER", f"{len(response)} bytes: {response[:48]!r}"


def describe_http(response):
    if not response:
        return "NO DATA", "the connection was closed or reset without an answer"
    if looks_like_edge_page(response):
        return "EDGE", "datacenter domain-whitelist page, not the tunnel"
    head = response.split(b"\r\n\r\n", 1)[0]
    status = head.split(b"\r\n", 1)[0].decode("latin-1", "replace")
    if status.startswith("HTTP/"):
        return "HTTP", f"{status} ({len(response)} bytes)"
    return "OTHER", f"{len(response)} bytes: {response[:48]!r}"


def probe_tls(host, port, sni, timeout, verify, request=b""):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = verify
    context.verify_mode = ssl.CERT_REQUIRED if verify else ssl.CERT_NONE
    try:
        with socket.create_connection((host, port), timeout) as raw:
            raw.settimeout(timeout)
            with context.wrap_socket(raw, server_hostname=sni) as tls:
                detail = f"{tls.version()} {tls.cipher()[0]}"
                return True, detail, request_over(tls, request) if request else b""
    except ssl.SSLCertVerificationError as error:
        return False, f"handshake ok, certificate rejected: {error.verify_message if hasattr(error, 'verify_message') else error}", b""
    except (ssl.SSLError, OSError) as error:
        return False, f"no handshake: {type(error).__name__}: {error}", b""


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", required=True, help="public entry host")
    parser.add_argument("--port", type=int, required=True, help="public entry port")
    parser.add_argument("--sni", help="name to send in the TLS handshake (default: --host)")
    parser.add_argument("--timeout", type=float, default=8.0, help="seconds per probe (default 8)")
    parser.add_argument(
        "--local-mux", help="also probe this local mux HOST:PORT, for comparison",
    )
    parser.add_argument(
        "--proxy-protocol", action="store_true",
        help=(
            "prefix the --local-mux connections with a PROXY protocol v2 "
            "header, for a mux started with --proxy-protocol; the public half "
            "is unaffected (frpc adds that header there)"
        ),
    )
    arguments = parser.parse_args(argv)

    addresses = resolve(arguments.host)
    print(f"target   {arguments.host}:{arguments.port}")
    print(f"resolves {', '.join(addresses)}")
    if fake_ip(addresses):
        print("WARNING  198.18.0.0/15 is a fake-IP range: these results describe your")
        print("         resolver or proxy, not the node. Re-run on a clean host.")

    started = time.monotonic()
    try:
        with socket.create_connection((arguments.host, arguments.port), arguments.timeout):
            print(f"connect  ok ({time.monotonic() - started:.2f}s)")
    except OSError as error:
        print(f"connect  FAILED: {type(error).__name__}: {error}")
        return 1

    results = {}
    for name, payload, describe in [
        ("java", JAVA_PING, describe_java),
        ("http", HTTP_REQUEST.format(host=arguments.host).encode(), describe_http),
    ]:
        try:
            response = exchange(arguments.host, arguments.port, payload, arguments.timeout)
        except OSError as error:
            label, detail = "NO DATA", f"{type(error).__name__}: {error}"
        else:
            label, detail = describe(response)
        results[name] = label
        print(f"{name:<8} {label:<8} {detail}")

    sni = arguments.sni or arguments.host
    request = HTTP_REQUEST.format(host=arguments.host).encode()
    handshake, detail, response = probe_tls(
        arguments.host, arguments.port, sni, arguments.timeout, verify=False, request=request,
    )
    print(f"tls      {'HANDSHAKE' if handshake else 'NO DATA':<8} {detail}")
    results["https"] = None
    if handshake:
        label, why = describe_http(response)
        results["https"] = label
        print(f"https    {label:<8} {why}")
        trusted, reason, _ = probe_tls(
            arguments.host, arguments.port, sni, arguments.timeout, verify=True,
        )
        print(f"tls-     {'TRUSTED' if trusted else 'UNTRUSTED':<8} {reason}")

    if arguments.local_mux:
        local_host, _, local_port_text = arguments.local_mux.partition(":")
        local_port = int(local_port_text)
        print()
        print(f"local mux {arguments.local_mux}"
              + (" (PROXY protocol v2)" if arguments.proxy_protocol else ""))
        if arguments.proxy_protocol:
            # The mux refuses a headerless connection here, so the header has
            # to carry a real source: what the Java backend prints back is the
            # only place the value it read is visible. The destination is
            # where the probe is actually going.
            source = ("203.0.113.7", 40777)
            destination = (local_host, local_port)
            try:
                header = proxy_v2_header(source, destination)
            except OSError as error:
                print(f"  ERROR: --proxy-protocol needs an IPv4 --local-mux: {error}")
                return 2
        else:
            header = b""
        for name, payload, describe in [
            ("java", JAVA_PING, describe_java),
            ("http", HTTP_REQUEST.format(host=arguments.host).encode(), describe_http),
        ]:
            try:
                response = exchange(local_host, local_port, header + payload, arguments.timeout)
            except OSError as error:
                label, detail = "NO DATA", f"{type(error).__name__}: {error}"
            else:
                label, detail = describe(response)
            print(f"{name:<8} {label:<8} {detail}")

    print()
    print("verdict")
    print(f"  Java over this port:  {'reached a Minecraft server' if results['java'] == 'JAVA' else 'did not reach a server (' + results['java'] + ')'}")
    if results["http"] == "EDGE":
        print("  HTTP over this port:  intercepted at the edge - NetherNet signalling")
        print("                        cannot use this port, with or without a certificate")
    else:
        print(f"  HTTP over this port:  {results['http']}")
    if not handshake:
        print("  HTTPS over this port: no handshake: the ClientHello never got an answer")
    elif results["https"] in (None, "NO DATA"):
        print("  HTTPS over this port: handshake, but nothing answered the request inside it")
    else:
        print(f"  HTTPS over this port: {results['https']}")
    return 0 if results["java"] == "JAVA" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
