#!/usr/bin/env python3
"""Inspect what a UDP frpc tunnel delivers to its local service.

This is a transport-level probe, independent of Minecraft and NetherNet. A
frpc UDP proxy with PROXY protocol enabled sends a PROXY v2 header before the
forwarded payload. The payload can therefore be any bytes we choose; the
header is what says whether frpc supplied the request-side address.

The NATFRP 0.51 client sends that header as its own UDP datagram, followed by
a second datagram containing the payload. Other builds may coalesce the two.
The listener below accepts both shapes.

Run a listener on the host that owns the frpc process:

    python3 scripts/probe_public_udp.py listen --bind 127.0.0.1:19132

Then send one datagram from another machine, preferably outside the server's
LAN:

    python3 scripts/probe_public_udp.py send \
        --host <frp-node> --port <public-udp-port>

The listener prints the address frpc reported. If it prints "proxy none", the
local service saw only frpc's loopback socket and no request-side address was
forwarded.

The PROXY source is the request-side address. Its destination field is the
destination frp recorded for that session; it is metadata, not the address
frpc uses to choose the local service (`localPort` does that).

This does not prove that Geyser understands the header, that the advertised
relay is reachable by a Bedrock client, or which ICE path a client selected.
Those are NetherNet-level questions and need a Bedrock client or Geyser debug
logs. It does answer the narrow relay question: did frpc carry the sender's
address through the UDP tunnel?
"""

import argparse
import socket
import struct
import sys


PROXY_V2_SIGNATURE = b"\r\n\r\n\x00\r\nQUIT\n"
DEFAULT_PAYLOAD = b"asp-udp-probe"

FAMILIES = {
    0x0: "UNSPEC",
    0x1: "IPv4",
    0x2: "IPv6",
    0x3: "UNIX",
}
PROTOCOLS = {
    0x0: "UNSPEC",
    0x1: "STREAM",
    0x2: "DGRAM",
}


def parse_endpoint(text):
    """Split HOST:PORT as the probe's command line spells it."""
    if text.startswith("["):
        end = text.find("]")
        if end < 0 or text[end + 1:end + 2] != ":":
            raise ValueError("IPv6 endpoints need [HOST]:PORT")
        host = text[1:end]
        port_text = text[end + 2:]
    else:
        host, separator, port_text = text.rpartition(":")
        if not separator:
            raise ValueError("expected HOST:PORT")
        if ":" in host:
            raise ValueError("IPv6 endpoints need [HOST]:PORT")
    if not host:
        raise ValueError("host is empty")
    try:
        port = int(port_text)
    except ValueError as error:
        raise ValueError("port is not a number") from error
    if not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    return host, port


def parse_proxy_v2(packet):
    """Describe a PROXY v2 header and the payload behind it.

    The return value is a dictionary rather than an exception: an ordinary
    datagram and a malformed header are both useful observations here.
    """
    if not packet.startswith(PROXY_V2_SIGNATURE):
        return {
            "kind": "none",
            "payload": packet,
            "detail": "no PROXY v2 signature",
        }
    if len(packet) < 16:
        return {
            "kind": "incomplete",
            "payload": b"",
            "detail": "the datagram ended inside the 16-byte PROXY v2 header",
        }

    version_command = packet[12]
    family_protocol = packet[13]
    address_length = struct.unpack("!H", packet[14:16])[0]
    header_length = 16 + address_length
    if len(packet) < header_length:
        return {
            "kind": "incomplete",
            "payload": b"",
            "detail": (
                f"header says {address_length} address bytes, "
                f"but only {len(packet) - 16} arrived"
            ),
        }

    version = version_command >> 4
    command_number = version_command & 0x0F
    family_number = family_protocol >> 4
    protocol_number = family_protocol & 0x0F
    if version != 2:
        return {
            "kind": "malformed",
            "payload": packet[header_length:],
            "detail": f"PROXY version is {version}, not 2",
        }
    if command_number not in (0x0, 0x1):
        return {
            "kind": "malformed",
            "payload": packet[header_length:],
            "detail": f"unknown PROXY command 0x{command_number:x}",
        }

    result = {
        "kind": "header",
        "command": "LOCAL" if command_number == 0 else "PROXY",
        "family": FAMILIES.get(family_number, f"0x{family_number:x}"),
        "protocol": PROTOCOLS.get(protocol_number, f"0x{protocol_number:x}"),
        "source": None,
        "destination": None,
        "payload": packet[header_length:],
        "detail": "",
    }

    addresses = packet[16:header_length]
    if command_number == 0x0:
        # PROXY v2 LOCAL is how a proxy says it originated the connection.
        # Its address fields must be ignored, even when a sender fills them.
        result["detail"] = "LOCAL command carries no request-side endpoint"
    elif family_number == 0x1 and address_length >= 12:
        source_ip = socket.inet_ntop(socket.AF_INET, addresses[0:4])
        destination_ip = socket.inet_ntop(socket.AF_INET, addresses[4:8])
        source_port, destination_port = struct.unpack("!HH", addresses[8:12])
        result["source"] = f"{source_ip}:{source_port}"
        result["destination"] = f"{destination_ip}:{destination_port}"
    elif family_number == 0x2 and address_length >= 36:
        source_ip = socket.inet_ntop(socket.AF_INET6, addresses[0:16])
        destination_ip = socket.inet_ntop(socket.AF_INET6, addresses[16:32])
        source_port, destination_port = struct.unpack("!HH", addresses[32:36])
        result["source"] = f"[{source_ip}]:{source_port}"
        result["destination"] = f"[{destination_ip}]:{destination_port}"
    else:
        result["detail"] = "header has no IPv4 or IPv6 endpoint this probe decodes"

    return result


def capture_datagram(sock, timeout):
    """Receive one logical observation, including a separate payload."""
    sock.settimeout(timeout)
    packet, peer = sock.recvfrom(65535)
    parsed = parse_proxy_v2(packet)
    parsed["datagram_length"] = len(packet)
    parsed["payload_separate"] = False
    parsed["payload_timeout"] = False
    if parsed["kind"] == "header" and not parsed["payload"]:
        try:
            payload, payload_peer = sock.recvfrom(65535)
        except socket.timeout:
            parsed["payload_timeout"] = True
        else:
            parsed["payload"] = payload
            parsed["payload_peer"] = payload_peer
            parsed["payload_separate"] = True
    return parsed, peer


def show_datagram(parsed, peer):
    """Print one captured observation."""
    print(f"peer     {peer[0]}:{peer[1]}")
    print(f"received {parsed['datagram_length']} bytes")
    if parsed["kind"] == "none":
        print("proxy    none")
    elif parsed["kind"] == "incomplete":
        print(f"proxy    INCOMPLETE: {parsed['detail']}")
    elif parsed["kind"] == "malformed":
        print(f"proxy    MALFORMED: {parsed['detail']}")
    else:
        print(
            "proxy    "
            f"v2 {parsed['command']} {parsed['family']}/{parsed['protocol']}"
        )
        if parsed["source"]:
            print(f"source   {parsed['source']}")
        if parsed["destination"]:
            print(f"header-dst {parsed['destination']} (metadata; localPort routes)")
        if parsed["detail"]:
            print(f"detail   {parsed['detail']}")

    payload = parsed["payload"]
    if parsed.get("payload_timeout"):
        print("payload  no following datagram arrived before the timeout")
    elif parsed.get("payload_separate"):
        payload_peer = parsed["payload_peer"]
        print(
            f"payload-datagram {len(payload)} bytes from "
            f"{payload_peer[0]}:{payload_peer[1]}: {payload[:96]!r}"
        )
    else:
        print(f"payload  {len(payload)} bytes: {payload[:96]!r}")


def format_verdict(parsed):
    if parsed["kind"] == "header" and parsed["source"]:
        return "frpc supplied the request-side endpoint in a PROXY v2 header"
    if parsed["kind"] == "none":
        return (
            "no PROXY v2 header: the local service sees frpc, "
            "not the request-side endpoint"
        )
    if parsed["kind"] == "incomplete":
        return "the datagram contains an incomplete PROXY v2 header"
    if parsed["kind"] == "malformed":
        return "the datagram contains a malformed PROXY v2 header"
    return "a PROXY v2 header arrived, but it carries no request-side endpoint"


def listen(bind, timeout, count):
    host, port = bind
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_DGRAM)
    try:
        try:
            sock.bind((host, port))
        except OSError as error:
            print(f"bind     FAILED: {error}", file=sys.stderr)
            return 1
        sock.settimeout(timeout)
        print(f"listen   {host}:{port}")
        for index in range(count):
            try:
                parsed, peer = capture_datagram(sock, timeout)
            except socket.timeout:
                print(
                    f"timeout  no UDP datagram arrived within {timeout:g}s",
                    file=sys.stderr,
                )
                return 1
            print(f"datagram {index + 1}/{count}")
            show_datagram(parsed, peer)
            print(f"verdict  {format_verdict(parsed)}")
            if index + 1 < count:
                print()
        return 0
    finally:
        sock.close()


def send(host, port, payload, count):
    try:
        addresses = socket.getaddrinfo(
            host, port, type=socket.SOCK_DGRAM, proto=socket.IPPROTO_UDP
        )
    except OSError as error:
        print(f"resolve  FAILED: {error}", file=sys.stderr)
        return 1

    # Prefer IPv4: the frp deployment and Geyser's numeric-advertise policy do
    # too, and a resolver can otherwise return IPv6 first on some hosts.
    addresses.sort(key=lambda item: item[0] != socket.AF_INET)
    family, socket_type, protocol, _, target = addresses[0]
    print(f"target   {host}:{port}")
    for item in addresses:
        print(f"resolves {item[4][0]}")
    sock = socket.socket(family, socket_type, protocol)
    try:
        for index in range(count):
            sent = sock.sendto(payload, target)
            print(f"sent     {sent} bytes to {target[0]}:{target[1]} ({index + 1}/{count})")
        return 0
    except OSError as error:
        print(f"send     FAILED: {error}", file=sys.stderr)
        return 1
    finally:
        sock.close()


def main(argv):
    parser = argparse.ArgumentParser(
        description="Inspect a UDP frpc tunnel without Minecraft traffic"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    listen_parser = subparsers.add_parser(
        "listen", help="bind the local UDP service and inspect one datagram"
    )
    listen_parser.add_argument(
        "--bind", default="127.0.0.1:19132",
        help="local address frpc forwards to (default: 127.0.0.1:19132)",
    )
    listen_parser.add_argument(
        "--timeout", type=float, default=30.0,
        help="seconds to wait for a datagram (default: 30)",
    )
    listen_parser.add_argument(
        "--count", type=int, default=1,
        help="number of datagrams to inspect before exiting (default: 1)",
    )

    send_parser = subparsers.add_parser(
        "send", help="send a payload to the public frpc UDP entry"
    )
    send_parser.add_argument("--host", required=True, help="frp node host")
    send_parser.add_argument("--port", required=True, type=int, help="public UDP port")
    send_parser.add_argument(
        "--payload", default=DEFAULT_PAYLOAD.decode("ascii"),
        help=f"UTF-8 payload (default: {DEFAULT_PAYLOAD.decode('ascii')})",
    )
    send_parser.add_argument(
        "--count", type=int, default=1,
        help="number of datagrams to send (default: 1)",
    )

    arguments = parser.parse_args(argv)
    if getattr(arguments, "count", 1) < 1:
        parser.error("--count must be at least 1")
    if getattr(arguments, "timeout", 1) <= 0:
        parser.error("--timeout must be greater than zero")
    if arguments.command == "send" and not 1 <= arguments.port <= 65535:
        parser.error("--port must be between 1 and 65535")

    if arguments.command == "listen":
        try:
            bind = parse_endpoint(arguments.bind)
        except ValueError as error:
            parser.error(f"--bind: {error}")
        return listen(bind, arguments.timeout, arguments.count)

    return send(
        arguments.host,
        arguments.port,
        arguments.payload.encode("utf-8"),
        arguments.count,
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
