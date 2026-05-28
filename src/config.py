"""TrustTunnel config manager — TOML read/write, server profiles, deep-link import."""

import os
import re
import subprocess
import ipaddress
from src._vendor import toml
import base64
from dataclasses import dataclass, field, asdict
from typing import Optional
from urllib.parse import parse_qs, urlparse


def _detect_egress_interface() -> str:
    """Detect the default egress network interface on macOS (e.g. en0, en1, utun3).

    Returns the interface name, or empty string if detection fails.
    Uses 'route get default' which works on all macOS versions.
    """
    try:
        result = subprocess.run(
            ["route", "-n", "get", "default"],
            capture_output=True, text=True, timeout=3,
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("interface:"):
                iface = line.split(":", 1)[1].strip()
                return iface
    except Exception:
        pass
    return ""


APP_DIR = os.path.expanduser("~/.trusttunnel-gui")
SERVERS_FILE = os.path.join(APP_DIR, "servers.toml")


@dataclass
class EndpointConfig:
    hostname: str
    addresses: list[str] = field(default_factory=list)
    username: str = ""
    password: str = ""
    has_ipv6: bool = True
    client_random: str = ""
    skip_verification: bool = False
    certificate: str = ""
    upstream_protocol: str = "http2"       # http2 | http3
    anti_dpi: bool = False
    dns_upstreams: list[str] = field(default_factory=list)


@dataclass
class TunConfig:
    bound_if: str = ""
    included_routes: list[str] = field(default_factory=lambda: ["0.0.0.0/0", "2000::/3"])
    excluded_routes: list[str] = field(default_factory=lambda: [
        "0.0.0.0/8", "10.0.0.0/8", "169.254.0.0/16",
        "172.16.0.0/12", "192.168.0.0/16", "224.0.0.0/3"
    ])
    mtu_size: int = 1280
    tcp_recv_buf_size: int = 0
    tcp_send_buf_size: int = 0
    change_system_dns: bool = True
    device_name: str = ""


@dataclass
class SocksConfig:
    address: str = "127.0.0.1:1080"
    username: str = ""
    password: str = ""


@dataclass
class ServerProfile:
    name: str
    endpoint: EndpointConfig = field(default_factory=EndpointConfig)
    tun: TunConfig = field(default_factory=TunConfig)
    socks: SocksConfig = field(default_factory=SocksConfig)
    vpn_mode: str = "general"              # general | selective
    killswitch_enabled: bool = True
    killswitch_allow_ports: list[int] = field(default_factory=list)
    post_quantum_group_enabled: bool = True
    exclusions: list[str] = field(default_factory=list)
    loglevel: str = "info"
    listener_type: str = "tun"              # tun | socks

    def to_client_toml(self) -> str:
        """Generate a valid trusttunnel_client TOML config string."""
        cfg = {
            "loglevel": self.loglevel,
            "vpn_mode": self.vpn_mode,
            "killswitch_enabled": self.killswitch_enabled,
            "killswitch_allow_ports": self.killswitch_allow_ports,
            "post_quantum_group_enabled": self.post_quantum_group_enabled,
            "exclusions": self.exclusions,
            "dns_upstreams": self.endpoint.dns_upstreams or ["1.1.1.1", "8.8.8.8"],
        }
        cfg["endpoint"] = {
            "hostname": self.endpoint.hostname,
            "addresses": self.endpoint.addresses,
            "has_ipv6": self.endpoint.has_ipv6,
            "username": self.endpoint.username,
            "password": self.endpoint.password,
            "client_random": self.endpoint.client_random,
            "skip_verification": self.endpoint.skip_verification,
            "upstream_protocol": self.endpoint.upstream_protocol,
            "anti_dpi": self.endpoint.anti_dpi,
            "dns_upstreams": self.endpoint.dns_upstreams,
        }
        if self.endpoint.certificate:
            cfg["endpoint"]["certificate"] = self.endpoint.certificate

        if self.listener_type == "tun":
            tun_dict = asdict(self.tun)
            # Auto-detect egress interface if not set — required for mactun route setup
            if not tun_dict.get("bound_if"):
                detected = _detect_egress_interface()
                if detected:
                    tun_dict["bound_if"] = detected
            # Exclude VPN server IPs from TUN routes so the initial connection
            # bypasses the tunnel (avoids chicken-and-egg deadlock with 0.0.0.0/0)
            server_ips = set()
            for addr in self.endpoint.addresses:
                # Extract IP from "host:port" format
                host = addr.split(":")[0] if ":" in addr else addr
                # Skip hostnames (not IPs) — DNS resolution needs the tunnel
                try:
                    ipaddress.ip_address(host)
                    server_ips.add(host)
                except ValueError:
                    pass
            if server_ips:
                existing = set(tun_dict.get("excluded_routes", []))
                existing.update(f"{ip}/32" for ip in server_ips)
                tun_dict["excluded_routes"] = sorted(existing)
            cfg["listener"] = {"tun": tun_dict}
        else:
            cfg["listener"] = {"socks": asdict(self.socks)}

        return toml.dumps(cfg)


def _parse_deeplink_toml_b64(qs: str) -> Optional[ServerProfile]:
    """Parse base64-encoded TOML (our preferred format)."""
    try:
        padding = "=" * (-len(qs) % 4)
        toml_str = base64.b64decode(qs + padding).decode("utf-8")
    except Exception:
        return None

    try:
        data = toml.loads(toml_str)
    except Exception:
        return None

    ep_data = data.get("endpoint", data)
    ep = EndpointConfig(
        hostname=ep_data.get("hostname", ""),
        addresses=ep_data.get("addresses", []),
        username=ep_data.get("username", ""),
        password=ep_data.get("password", ""),
        has_ipv6=ep_data.get("has_ipv6", True),
        client_random=ep_data.get("client_random_prefix",
                                 ep_data.get("client_random", "")),
        skip_verification=ep_data.get("skip_verification", False),
        certificate=ep_data.get("certificate", ""),
        upstream_protocol=ep_data.get("upstream_protocol", "http2"),
        anti_dpi=ep_data.get("anti_dpi", False),
        dns_upstreams=ep_data.get("dns_upstreams", []),
    )
    name = data.get("name", ep_data.get("name", "TrustTunnel Server"))
    return ServerProfile(name=name, endpoint=ep)


def _parse_deeplink_tlv(qs: str) -> Optional[ServerProfile]:
    """Parse TrustTunnel native binary TLV deep-link (best-effort, no cert)."""
    try:
        padding = "=" * (-len(qs) % 4)
        data = base64.b64decode(qs + padding)
    except Exception:
        return None

    if len(data) < 5:
        return None

    # Skip 4-byte header, first field is implicit hostname
    pos = 4
    hostname_len = data[pos]
    pos += 1
    if pos + hostname_len > len(data):
        return None
    hostname = data[pos:pos + hostname_len].decode("utf-8")
    pos += hostname_len

    # Remaining fields: [tag:1][len:1][value:N]
    fields: dict[int, str] = {9: hostname}
    while pos + 2 <= len(data):
        tag = data[pos]
        vlen = data[pos + 1]
        pos += 2
        if pos + vlen > len(data):
            break
        try:
            value = data[pos:pos + vlen].decode("utf-8", errors="replace")
        except Exception:
            value = ""
        fields[tag] = value
        pos += vlen

    # tag mapping: 2=address, 5=username, 6=password, 7=client_random,
    #               8=certificate, 9=hostname
    if 5 not in fields or 6 not in fields or 2 not in fields:
        return None

    ep = EndpointConfig(
        hostname=fields.get(9, ""),
        addresses=[a.strip() for a in fields.get(2, "").split(",") if a.strip()],
        username=fields.get(5, ""),
        password=fields.get(6, ""),
        client_random=fields.get(7, ""),
        # certificate (tag 8) unreliable at this offset — use skip_verification
        certificate="",
        skip_verification=True,
    )
    name = fields.get(9, "TrustTunnel Server")
    return ServerProfile(name=name, endpoint=ep)


def parse_deeplink(uri: str) -> Optional[ServerProfile]:
    """Parse a tt://? deeplink URI into a ServerProfile.

    Tries three formats in order:
      1. base64-encoded TOML (generated by endpoint --format toml | base64)
      2. TrustTunnel native binary TLV (endpoint default deep-link)
      3. URL-encoded key=value (deep-link with ?hostname=...&addresses=...)
    """
    if not uri.startswith("tt://?"):
        return None

    qs = uri[6:]  # strip "tt://?"

    # Format 1: base64-encoded TOML
    result = _parse_deeplink_toml_b64(qs)
    if result:
        return result

    # Format 2: TrustTunnel native binary TLV
    result = _parse_deeplink_tlv(qs)
    if result:
        return result

    # Format 3: URL-encoded key=value
    parsed = parse_qs(qs)
    if "hostname" in parsed:
        name = parsed.get("name", ["TrustTunnel Server"])[0]
        hostname = parsed.get("hostname", [""])[0]
        addresses_raw = parsed.get("addresses", [""])[0]
        addresses = [a.strip() for a in addresses_raw.split(",") if a.strip()]

        ep = EndpointConfig(
            hostname=hostname,
            addresses=addresses,
            username=parsed.get("username", [""])[0],
            password=parsed.get("password", [""])[0],
            client_random=parsed.get("client_random", [""])[0],
            certificate=parsed.get("certificate", [""])[0],
            skip_verification=parsed.get("skip_verification", ["false"])[0].lower() == "true",
            upstream_protocol=parsed.get("upstream_protocol", ["http2"])[0],
            anti_dpi=parsed.get("anti_dpi", ["false"])[0].lower() == "true",
        )
        if "dns_upstream" in parsed:
            ep.dns_upstreams = parsed["dns_upstream"]

        return ServerProfile(name=name, endpoint=ep)

    return None


def load_servers() -> list[ServerProfile]:
    """Load saved server profiles from disk."""
    os.makedirs(APP_DIR, exist_ok=True)
    if not os.path.exists(SERVERS_FILE):
        return []
    try:
        data = toml.load(SERVERS_FILE)
        profiles = []
        for s in data.get("servers", []):
            ep_data = s.get("endpoint", {})
            ep = EndpointConfig(
                hostname=ep_data.get("hostname", ""),
                addresses=ep_data.get("addresses", []),
                username=ep_data.get("username", ""),
                password=ep_data.get("password", ""),
                has_ipv6=ep_data.get("has_ipv6", True),
                client_random=ep_data.get("client_random", ""),
                skip_verification=ep_data.get("skip_verification", False),
                certificate=ep_data.get("certificate", ""),
                upstream_protocol=ep_data.get("upstream_protocol", "http2"),
                anti_dpi=ep_data.get("anti_dpi", False),
                dns_upstreams=ep_data.get("dns_upstreams", []),
            )
            tun_data = s.get("tun", {})
            tun = TunConfig(
                bound_if=tun_data.get("bound_if", ""),
                included_routes=tun_data.get("included_routes", ["0.0.0.0/0", "2000::/3"]),
                excluded_routes=tun_data.get("excluded_routes", []),
                mtu_size=tun_data.get("mtu_size", 1280),
                tcp_recv_buf_size=tun_data.get("tcp_recv_buf_size", 0),
                tcp_send_buf_size=tun_data.get("tcp_send_buf_size", 0),
                change_system_dns=tun_data.get("change_system_dns", True),
                device_name=tun_data.get("device_name", ""),
            )
            socks_data = s.get("socks", {})
            socks = SocksConfig(
                address=socks_data.get("address", "127.0.0.1:1080"),
                username=socks_data.get("username", ""),
                password=socks_data.get("password", ""),
            )
            profiles.append(ServerProfile(
                name=s.get("name", "Unnamed"),
                endpoint=ep, tun=tun, socks=socks,
                vpn_mode=s.get("vpn_mode", "general"),
                killswitch_enabled=s.get("killswitch_enabled", True),
                killswitch_allow_ports=s.get("killswitch_allow_ports", []),
                post_quantum_group_enabled=s.get("post_quantum_group_enabled", True),
                exclusions=s.get("exclusions", []),
                loglevel=s.get("loglevel", "info"),
                listener_type=s.get("listener_type", "tun"),
            ))
        return profiles
    except Exception:
        return []


def save_servers(profiles: list[ServerProfile]):
    """Save server profiles to disk."""
    os.makedirs(APP_DIR, exist_ok=True)
    data = {"servers": []}
    for p in profiles:
        data["servers"].append({
            "name": p.name,
            "vpn_mode": p.vpn_mode,
            "killswitch_enabled": p.killswitch_enabled,
            "killswitch_allow_ports": p.killswitch_allow_ports,
            "post_quantum_group_enabled": p.post_quantum_group_enabled,
            "exclusions": p.exclusions,
            "loglevel": p.loglevel,
            "listener_type": p.listener_type,
            "endpoint": {
                "hostname": p.endpoint.hostname,
                "addresses": p.endpoint.addresses,
                "username": p.endpoint.username,
                "password": p.endpoint.password,
                "has_ipv6": p.endpoint.has_ipv6,
                "client_random": p.endpoint.client_random,
                "skip_verification": p.endpoint.skip_verification,
                "certificate": p.endpoint.certificate,
                "upstream_protocol": p.endpoint.upstream_protocol,
                "anti_dpi": p.endpoint.anti_dpi,
                "dns_upstreams": p.endpoint.dns_upstreams,
            },
            "tun": asdict(p.tun),
            "socks": asdict(p.socks),
        })
    with open(SERVERS_FILE, "w") as f:
        toml.dump(data, f)
