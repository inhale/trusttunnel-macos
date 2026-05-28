"""TrustTunnel client process manager — manages the trusttunnel_client subprocess.

Now with pre-flight checks, phased connection progress, and rich diagnostics.
"""

import os
import ipaddress
import re
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from threading import Thread, Lock
from typing import Optional, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from .config import ServerProfile


def _find_project_root() -> str:
    """Find the project root directory, works in dev mode and py2app bundle."""
    # py2app: Resources/ is the bundle's resource directory
    if getattr(sys, 'frozen', False):
        # RESOURCEPATH is set by py2app to the bundle's Resources/ directory
        base = os.environ.get('RESOURCEPATH', os.path.dirname(sys.executable))
        # Contents/Resources/ -> Contents/ -> .app root
        if os.path.basename(base) == 'Resources':
            return os.path.dirname(base)
        # Fallback: go up from MacOS/ to Contents/
        if os.path.basename(base) == 'MacOS':
            return os.path.dirname(base)
        return base
    # Dev mode: src/client.py -> trusttunnel-macos/
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _find_resource_dir() -> str:
    """Return the Resources/ directory when running from py2app bundle."""
    if getattr(sys, 'frozen', False):
        base = os.environ.get('RESOURCEPATH', '')
        if base and os.path.basename(base) == 'Resources':
            return base
    return ''


def _get_binary_paths() -> list:
    """Return ordered list of paths to search for trusttunnel_client.

    py2app puts the binary at Contents/Resources/trusttunnel_client.
    Dev mode uses project bin/trusttunnel_client.
    """
    root = _find_project_root()
    paths = []
    # 1. py2app: Contents/Resources/trusttunnel_client
    resource_dir = _find_resource_dir()
    if resource_dir:
        paths.append(os.path.join(resource_dir, "trusttunnel_client"))
    # 2. Dev/project bin/
    paths.append(os.path.join(root, "bin", "trusttunnel_client"))
    # 3. System install
    paths.append("/opt/trusttunnel_client/trusttunnel_client")
    paths.append("/usr/local/bin/trusttunnel_client")
    # 4. Full PATH scan (resolve each candidate to absolute path)
    return paths


CLIENT_BINARY_PATHS = _get_binary_paths()

# Module-level DNS state for save/restore
_saved_dns_service: str = ""
_saved_dns_servers: list[str] = []


def _find_dns_proxy_port(log_lines: list[str]) -> str:
    """Extract the local DNS proxy port from binary log output.

    The binary logs lines like:
      System DNS proxy listening on 127.0.0.1:56255/TCP, 127.0.0.1:54920/UDP
    We return the UDP port since that's what macOS uses for DNS.
    """
    import re as _re
    for line in log_lines:
        m = _re.search(r"127\.0\.0\.1:(\d+)/UDP", line)
        if m:
            return m.group(1)
    return ""


def _get_primary_service() -> str:
    """Return the name of the primary active network service (e.g. 'Wi-Fi', 'Ethernet')."""
    try:
        result = subprocess.run(
            ["networksetup", "-listallnetworkservices"],
            capture_output=True, text=True, timeout=5,
        )
        services = [
            s.strip() for s in result.stdout.splitlines()
            if s.strip() and not s.strip().startswith("*")
        ]
        # Get the default interface to find the matching service
        route_result = subprocess.run(
            ["route", "-n", "get", "default"],
            capture_output=True, text=True, timeout=3,
        )
        default_iface = ""
        for line in route_result.stdout.splitlines():
            if line.strip().startswith("interface:"):
                default_iface = line.split(":", 1)[1].strip()
                break
        if default_iface:
            # Map interface to service name
            for svc in services:
                try:
                    info = subprocess.run(
                        ["networksetup", "-getinfo", svc],
                        capture_output=True, text=True, timeout=3,
                    )
                    if f"Device: {default_iface}" in info.stdout:
                        return svc
                except Exception:
                    pass
    except Exception:
        pass
    # Fallback: first service
    try:
        result = subprocess.run(
            ["networksetup", "-listallnetworkservices"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if line and not line.startswith("*"):
                return line
    except Exception:
        pass
    return ""


def _enforce_dns_through_tunnel(log_lines: list[str]) -> None:
    """Set macOS system DNS to the tunnel's local proxy to prevent DNS leaks.

    This ensures ALL DNS queries go through the VPN tunnel, not just those
    that happen to use the system resolver. Without this, apps using DoH
    or hard-coded DNS (Chrome, Firefox, etc.) can leak real location.
    """
    import re as _re

    port = _find_dns_proxy_port(log_lines)
    if not port:
        return

    dns_proxy = f"127.0.0.1"

    # Get primary network service
    service = _get_primary_service()
    if not service:
        return

    try:
        # Save current DNS settings for restore on disconnect
        current = subprocess.run(
            ["networksetup", "-getdnsservers", service],
            capture_output=True, text=True, timeout=5,
        )
        # Store in the last connect log for the ClientManager to pick up
        # (we don't have direct access to self here, so we use a module-level)
        _saved_dns_service = service
        _saved_dns_servers = [
            s.strip() for s in current.stdout.splitlines()
            if s.strip() and s.strip() != "There aren't any DNS Servers set on"
        ]
        if not _saved_dns_servers:
            _saved_dns_servers = ["empty"]

        # Set system DNS to the tunnel's local proxy only
        subprocess.run(
            ["networksetup", "-setdnsservers", service, dns_proxy],
            capture_output=True, text=True, timeout=5,
        )
        # Verify
        verify = subprocess.run(
            ["networksetup", "-getdnsservers", service],
            capture_output=True, text=True, timeout=5,
        )
        if dns_proxy in verify.stdout:
            log_lines.append(
                f"[{_ts()}] DNS locked to tunnel proxy ({dns_proxy}:{port}) on '{service}'"
            )
        else:
            log_lines.append(
                f"[{_ts()}] WARNING: DNS set may not have taken effect on '{service}'"
            )
    except Exception as e:
        log_lines.append(f"[{_ts()}] WARNING: failed to set system DNS: {e}")

    # Also block DNS-over-TLS (port 853) and common DoH endpoints
    # to prevent apps from bypassing the local proxy
    _block_outside_dns(log_lines)


def _block_outside_dns(log_lines: list[str]) -> None:
    """Add pf rules to force all DNS through the tunnel proxy.

    This blocks:
    - Plain DNS (port 53) to any non-local address
    - DNS-over-TLS (port 853) to any non-local address
    - Common DoH IPs (Google 8.8.8.8, Cloudflare 1.1.1.1, etc.)
    
    All DNS is redirected to 127.0.0.1 which is the tunnel's local proxy.
    """
    import re as _re

    # Find the DNS proxy UDP port from log lines
    port = _find_dns_proxy_port(log_lines)
    if not port:
        return

    # Build pf anchor rules
    pf_rules = f"""
# TrustTunnel DNS leak prevention
# Block all DNS outside tunnel, redirect to local proxy

# Allow local proxy
pass quick on lo0 proto udp from any to 127.0.0.1 port {port}
pass quick on lo0 proto tcp from any to 127.0.0.1 port {int(port) + 1}

# Block plain DNS (port 53) to non-local
block drop out proto udp from any to any port 53
block drop out proto tcp from any to any port 53

# Block DNS-over-TLS (port 853)
block drop out proto tcp from any to any port 853

# Block known DoH endpoints (redirect through tunnel)
# Google DNS DoH
block drop out proto tcp from any to 8.8.8.8 port 443
block drop out proto tcp from any to 8.8.4.4 port 443
# Cloudflare DoH
block drop out proto tcp from any to 1.1.1.1 port 443
block drop out proto tcp from any to 1.0.0.1 port 443
# Quad9 DoH
block drop out proto tcp from any to 9.9.9.9 port 443
block drop out proto tcp from any to 149.112.112.112 port 443
# AdGuard DoH
block drop out proto tcp from any to 94.140.14.14 port 443
block drop out proto tcp from any to 94.140.15.15 port 443
"""

    # Write to a temp anchor file
    anchor_file = os.path.join(tempfile.gettempdir(), "tt_dns_anchor.conf")
    try:
        with open(anchor_file, "w") as f:
            f.write(pf_rules)

        # Load the anchor (requires root, so use sudo)
        result = subprocess.run(
            ["sudo", "-n", "pfctl", "-a", "com.trusttunnel.dns", "-f", anchor_file],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            # Enable pf if not already enabled
            subprocess.run(
                ["sudo", "-n", "pfctl", "-e"],
                capture_output=True, text=True, timeout=5,
            )
            log_lines.append(
                f"[{_ts()}] DNS leak prevention: blocked outside DNS (port 53, 853, DoH)"
            )
        else:
            # pfctl failed — log but don't block the connection
            log_lines.append(
                f"[{_ts()}] WARNING: could not load pf DNS rules "
                f"(DNS leak prevention may be incomplete): {result.stderr.strip()}"
            )
    except Exception as e:
        log_lines.append(f"[{_ts()}] WARNING: DNS pf rules failed: {e}")


def _restore_dns(log_lines: list[str]) -> None:
    """Restore original DNS settings after VPN disconnect."""
    global _saved_dns_service, _saved_dns_servers
    if not _saved_dns_service:
        return
    try:
        if _saved_dns_servers == ["empty"]:
            subprocess.run(
                ["networksetup", "-setdnsservers", _saved_dns_service, "Empty"],
                capture_output=True, text=True, timeout=5,
            )
        else:
            subprocess.run(
                ["networksetup", "-setdnsservers", _saved_dns_service] + _saved_dns_servers,
                capture_output=True, text=True, timeout=5,
            )
        log_lines.append(
            f"[{_ts()}] DNS restored on '{_saved_dns_service}': {_saved_dns_servers}"
        )
    except Exception as e:
        log_lines.append(f"[{_ts()}] WARNING: failed to restore DNS: {e}")
    finally:
        _saved_dns_service = ""
        _saved_dns_servers = []

    # Remove pf DNS anchor
    try:
        subprocess.run(
            ["sudo", "-n", "pfctl", "-a", "com.trusttunnel.dns", "-F", "all"],
            capture_output=True, text=True, timeout=5,
        )
    except Exception:
        pass


def _detect_competing_vpn() -> list[str]:
    """Detect existing VPN interfaces and routes that may conflict with TrustTunnel.

    Returns a list of human-readable warnings about competing network configurations.
    """
    warnings = []

    # 1. Check for utun interfaces with active routes (sign of another VPN)
    try:
        result = subprocess.run(
            ["netstat", "-rn"],
            capture_output=True, text=True, timeout=5,
        )
        utun_gateways = set()
        utun_default = False
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) < 2:
                continue
            dest = parts[0]
            gateway = parts[1] if len(parts) > 1 else ""
            iface = parts[-1] if len(parts) > 2 else ""
            if iface.startswith("utun"):
                utun_gateways.add(iface)
                if dest in ("default", "0/1", "128.0/1", "0.0.0.0/0"):
                    utun_default = True
        if utun_default:
            warnings.append(
                f"Another VPN appears to be active ({', '.join(sorted(utun_gateways))}). "
                "Its routes may conflict with TrustTunnel."
            )
    except Exception:
        pass

    # 2. Check for common VPN interfaces (utun0-utun7 typically used by other VPNs)
    try:
        result = subprocess.run(
            ["ifconfig"],
            capture_output=True, text=True, timeout=5,
        )
        active_utun = set()
        for block in result.stdout.split("\n\n"):
            m = re.match(r"(utun\d+):", block)
            if m:
                iface = m.group(1)
                if "inet " in block or "RUNNING" in block:
                    active_utun.add(iface)
        if active_utun:
            warnings.append(
                f"Active utun interfaces detected: {', '.join(sorted(active_utun))}. "
                "These may belong to another VPN connection."
            )
    except Exception:
        pass

    # 3. Check for common VPN processes
    vpn_processes = []
    common_vpn_names = [
        "wireguard", "openvpn", "vpn", "nordvpn", "expressvpn",
        "surfshark", "mullvad", "protonvpn", "tunnelbear",
        "cisco", "anyconnect", "globalprotect", "forticlient",
        "wireguard-go", "tailscale",
    ]
    try:
        result = subprocess.run(
            ["ps", "aux"],
            capture_output=True, text=True, timeout=5,
        )
        seen = set()
        for line in result.stdout.splitlines():
            for vpn_name in common_vpn_names:
                if vpn_name in line.lower():
                    # Extract process name
                    parts = line.split()
                    if len(parts) >= 11:
                        proc_name = parts[10]
                        if proc_name not in seen:
                            seen.add(proc_name)
                            vpn_processes.append(proc_name)
        if vpn_processes:
            warnings.append(
                f"VPN-related processes running: {', '.join(sorted(vpn_processes))}. "
                "These may interfere with TrustTunnel."
            )
    except Exception:
        pass

    return warnings


class ClientState(Enum):
    DISCONNECTED = "disconnected"
    CHECKING = "checking"          # pre-flight checks
    CONNECTING = "connecting"       # process started, waiting for tunnel
    CONNECTED = "connected"
    ERROR = "error"


class ConnectPhase(Enum):
    """Granular connection phase for diagnostics."""
    IDLE = "idle"
    FINDING_BINARY = "finding binary"
    CHECKING_SUDO = "checking sudo"
    WRITING_CONFIG = "writing config"
    SPAWNING_PROCESS = "spawning process"
    WAITING_TUNNEL = "waiting for tunnel"
    TUNNEL_UP = "tunnel up"
    FAILED = "failed"


@dataclass
class ClientStatus:
    state: ClientState = ClientState.DISCONNECTED
    phase: ConnectPhase = ConnectPhase.IDLE
    server_name: str = ""
    uptime: float = 0.0
    error: str = ""
    rx_bytes: int = 0
    tx_bytes: int = 0
    log_lines: list[str] = field(default_factory=list)
    started_at: Optional[datetime] = None


class ClientManager:
    """Manages the trusttunnel_client process lifecycle."""

    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._status = ClientStatus()
        self._lock = Lock()
        self._start_time: float = 0.0
        self._state_callbacks: list[Callable[[ClientStatus], None]] = []
        self._reader_thread: Optional[Thread] = None
        self._config_path: Optional[str] = None
        self._last_connect_log: list[str] = []
        # Saved DNS settings for restore on disconnect
        self._saved_dns_service: str = ""
        self._saved_dns_servers: list[str] = []
    @property
    def status(self) -> ClientStatus:
        with self._lock:
            return ClientStatus(
                state=self._status.state,
                phase=self._status.phase,
                server_name=self._status.server_name,
                uptime=time.time() - self._start_time if self._start_time else 0.0,
                error=self._status.error,
                rx_bytes=self._status.rx_bytes,
                tx_bytes=self._status.tx_bytes,
                log_lines=list(self._status.log_lines),
                started_at=self._status.started_at,
            )

    def on_state_change(self, callback: Callable[[ClientStatus], None]):
        self._state_callbacks.append(callback)

    def _notify(self):
        status = self.status
        for cb in self._state_callbacks:
            try:
                cb(status)
            except Exception:
                pass

    def _set_phase(self, phase: ConnectPhase):
        with self._lock:
            self._status.phase = phase
            self._status.log_lines.append(
                f"[{_ts()}] {phase.value}"
            )
        self._notify()

    def _find_binary(self) -> Optional[str]:
        self._set_phase(ConnectPhase.FINDING_BINARY)
        for path in CLIENT_BINARY_PATHS:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                with self._lock:
                    self._status.log_lines.append(
                        f"[{_ts()}] binary: {path}"
                    )
                return path
        for path in os.environ.get("PATH", "").split(":"):
            candidate = os.path.join(path, "trusttunnel_client")
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                with self._lock:
                    self._status.log_lines.append(
                        f"[{_ts()}] binary: {candidate}"
                    )
                return candidate
        return None

    def _check_sudo(self) -> tuple[bool, str]:
        """Verify passwordless sudo works for the trusttunnel_client binary."""
        self._set_phase(ConnectPhase.CHECKING_SUDO)
        binary = self._find_binary()
        if not binary:
            return False, "trusttunnel_client binary not found (cannot test sudo)"
        try:
            result = subprocess.run(
                ["sudo", "-n", binary, "--version"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                return True, "sudo available (passwordless)"
            else:
                # sudo not configured — try to fix it in-app via osascript
                fixed, fix_msg = self._fix_sudo(binary)
                if fixed:
                    return True, f"sudo configured automatically for {binary}"
                import getpass as _gp
                try:
                    user = _gp.getuser()
                except Exception:
                    user = "YOUR_USER"
                return False, (
                    "sudo requires a password or is not configured.\n\n"
                    f"Binary path: {binary}\n\n"
                    "Fix: run this in Terminal:\n"
                    "  curl -fsSL https://raw.githubusercontent.com/"
                    "inhale/trusttunnel-macos/main/setup-sudo.sh | bash\n\n"
                    f"Or manually add to /etc/sudoers via 'sudo visudo':\n"
                    f"  {user}  ALL=(ALL) NOPASSWD: {binary}\n\n"
                    f"Auto-fix attempt: {fix_msg}\n"
                    f"sudo stderr: {result.stderr.strip()}"
                )
        except FileNotFoundError:
            return False, "'sudo' command not found on this system"
        except subprocess.TimeoutExpired:
            return False, "sudo check timed out (hung waiting for password prompt?)"

    def _fix_sudo(self, binary: str) -> tuple[bool, str]:
        """Try to write the sudoers entry automatically using osascript (macOS admin dialog)."""
        try:
            import getpass as _gp
            try:
                user = _gp.getuser()
            except Exception:
                return False, "could not determine username"

            sudoers_file = "/etc/sudoers.d/trusttunnel"
            sudoers_line = f"{user}  ALL=(ALL) NOPASSWD: {binary}"
            sudoers_content = f"# TrustTunnel VPN — passwordless sudo\\n{sudoers_line}\\n"

            # Build a shell script that writes the sudoers file and verifies syntax
            shell_script = (
                f"printf '{sudoers_content}' > {sudoers_file} && "
                f"chmod 440 {sudoers_file} && "
                f"visudo -c -f {sudoers_file} || rm -f {sudoers_file}"
            )

            # osascript runs the shell as admin — shows macOS password dialog
            result = subprocess.run(
                ["osascript", "-e",
                 f'do shell script "{shell_script}" with administrator privileges'],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                # Verify it actually works now
                verify = subprocess.run(
                    ["sudo", "-n", binary, "--version"],
                    capture_output=True, text=True, timeout=5,
                )
                if verify.returncode == 0:
                    return True, "sudoers entry written successfully"
                return False, "sudoers written but sudo -n still fails"
            else:
                err = result.stderr.strip() or result.stdout.strip()
                return False, f"osascript failed: {err}"
        except subprocess.TimeoutExpired:
            return False, "admin dialog timed out (user may have cancelled)"
        except Exception as e:
            return False, f"exception: {e}"

    def connect(self, profile: "ServerProfile") -> bool:
        """Start the VPN connection with full diagnostics."""

        if self.is_connected():
            self.disconnect()
            time.sleep(0.5)

        with self._lock:
            self._status.state = ClientState.CHECKING
            self._status.server_name = profile.name
            self._status.error = ""
            self._status.log_lines = []
            self._status.phase = ConnectPhase.IDLE
            self._status.started_at = datetime.now()
        self._notify()

        # ── Pre-flight 1: find binary ──
        binary = self._find_binary()
        if not binary:
            self._set_error(
                "trusttunnel_client not found.\n\n"
                "Searched:\n  " + "\n  ".join(CLIENT_BINARY_PATHS) + "\n"
                "and all directories in $PATH.\n\n"
                "Install: curl -fsSL https://raw.githubusercontent.com/"
                "TrustTunnel/TrustTunnelClient/refs/heads/master/scripts/install.sh | sh -s -"
            )
            return False

        # ── Pre-flight 2: sudo check ──
        sudo_ok, sudo_msg = self._check_sudo()
        if not sudo_ok:
            self._set_error(f"sudo check failed:\n{sudo_msg}")
            return False

        # ── Pre-flight 3: check for competing VPNs ──
        vpn_warnings = _detect_competing_vpn()
        if vpn_warnings:
            warning_text = "\n\n".join(vpn_warnings)
            with self._lock:
                self._status.log_lines.append(
                    f"[{_ts()}] WARNING: {warning_text}"
                )
            # Don't block — just warn. The connection might still work.

        # ── Pre-flight 4: write config ──
        self._set_phase(ConnectPhase.WRITING_CONFIG)
        toml_content = profile.to_client_toml()
        config_path = os.path.join(
            tempfile.gettempdir(), f"tt_gui_{os.getpid()}.toml"
        )
        try:
            with open(config_path, "w") as f:
                f.write(toml_content)
            # Log bound_if so user can see what interface was detected
            import re as _re
            m = _re.search(r'bound_if\s*=\s*"([^"]*)"', toml_content)
            bound_if_val = m.group(1) if m else ""
            with self._lock:
                if bound_if_val:
                    self._status.log_lines.append(
                        f"[{_ts()}] egress interface: {bound_if_val}"
                    )
                else:
                    self._status.log_lines.append(
                        f"[{_ts()}] WARNING: could not detect egress interface (bound_if empty)"
                    )
        except OSError as e:
            self._set_error(f"Failed to write config to {config_path}:\n{e}")
            return False
        self._config_path = config_path

        # ── Spawn process ──
        self._set_phase(ConnectPhase.SPAWNING_PROCESS)
        with self._lock:
            self._status.state = ClientState.CONNECTING
        self._notify()

        try:
            self._process = subprocess.Popen(
                ["sudo", "-n", binary, "-c", config_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            self._start_time = time.time()

            # Background reader
            self._reader_thread = Thread(
                target=self._read_output, daemon=True
            )
            self._reader_thread.start()

            # ── Wait for tunnel with phased checking ──
            self._set_phase(ConnectPhase.WAITING_TUNNEL)

            # Wait up to 10 seconds (some servers take time)
            deadline = time.time() + 10
            connected = False
            while time.time() < deadline:
                time.sleep(0.5)
                if self._process.poll() is not None:
                    # Process died
                    logs = _format_crash_log(self._status.log_lines)
                    self._set_error(
                        f"trusttunnel_client exited with code "
                        f"{self._process.returncode}.\n\n"
                        f"{logs}\n"
                        f"Config written to: {config_path}\n"
                        f"Command: sudo -n {binary} -c {config_path}"
                    )
                    return False
                # Check if output indicates connection
                with self._lock:
                    if self._status.state == ClientState.CONNECTED:
                        connected = True
                        break

            if connected:
                self._set_phase(ConnectPhase.TUNNEL_UP)
                return True
            else:
                # Check if reader already flagged an error
                with self._lock:
                    current_state = self._status.state
                if current_state == ClientState.ERROR:
                    return False
                # Process still running and no explicit tunnel-up signal yet.
                # Give it a bit more time — some slow connections take >10s.
                # But don't blindly declare success; wait up to 20s more.
                extended_deadline = time.time() + 20
                while time.time() < extended_deadline:
                    time.sleep(0.5)
                    if self._process.poll() is not None:
                        logs = _format_crash_log(self._status.log_lines)
                        self._set_error(
                            f"trusttunnel_client exited with code "
                            f"{self._process.returncode}.\n\n"
                            f"{logs}\n"
                            f"Config: {config_path}\n"
                            f"Command: sudo -n {binary} -c {config_path}"
                        )
                        return False
                    with self._lock:
                        s = self._status.state
                    if s == ClientState.CONNECTED:
                        self._set_phase(ConnectPhase.TUNNEL_UP)
                        return True
                    if s == ClientState.ERROR:
                        return False
                # Still alive after 30s total with no tunnel-up — give up
                logs = _format_crash_log(self._status.log_lines)
                self._set_error(
                    f"Tunnel did not come up after 30 seconds.\n\n"
                    f"{logs}\n\n"
                    f"Check the console for errors."
                )
                return False

        except Exception as e:
            self._set_error(f"Exception during connect:\n{type(e).__name__}: {e}")
            return False

    def _read_output(self):
        """Read subprocess output, parsing for status info."""
        if not self._process or not self._process.stdout:
            return
        try:
            for line in self._process.stdout:
                line = line.rstrip()
                with self._lock:
                    self._status.log_lines.append(f"[{_ts()}] {line}")
                    if len(self._status.log_lines) > 1000:
                        self._status.log_lines = self._status.log_lines[-400:]
                # Detect fatal errors — mark error state immediately
                lower = line.lower()
                if any(kw in lower for kw in [
                    "failed to initialize tunnel",
                    "unable to setup routes",
                    "failed to create listener",
                    "error at ag::",
                ]):
                    with self._lock:
                        if self._status.state in (
                            ClientState.CONNECTING, ClientState.CONNECTED
                        ):
                            self._status.state = ClientState.ERROR
                            self._status.phase = ConnectPhase.FAILED
                            # Build actionable error message
                            error_msg = line.strip()
                            if "unable to setup routes" in lower:
                                error_msg += (
                                    "\n\n"
                                    "This usually means another VPN or network "
                                    "configuration is conflicting with TrustTunnel.\n\n"
                                    "Try:\n"
                                    "  1. Disconnect any other VPN (check menu bar icons)\n"
                                    "  2. Check System Settings → Network for active VPN configs\n"
                                    "  3. If on a corporate network, contact IT about routing policies\n\n"
                                    "Diagnostic info:\n"
                                )
                                # Run diagnostics
                                vpn_warnings = _detect_competing_vpn()
                                if vpn_warnings:
                                    error_msg += "\n".join(f"  • {w}" for w in vpn_warnings)
                                else:
                                    error_msg += "  No competing VPN detected.\n"
                                # Check current routes
                                try:
                                    route_result = subprocess.run(
                                        ["netstat", "-rn"],
                                        capture_output=True, text=True, timeout=3,
                                    )
                                    default_routes = [
                                        l for l in route_result.stdout.splitlines()
                                        if l.split()[0] in ("default", "0/1", "128.0/1")
                                    ] if route_result.stdout else []
                                    if default_routes:
                                        error_msg += "  Active default routes:\n"
                                        for r in default_routes:
                                            error_msg += f"    {r.strip()}\n"
                                except Exception:
                                    pass
                            self._status.error = error_msg
                    self._notify()
                    continue
                # Detect connection established — only on explicit tunnel-up signals
                # (not generic "started"/"running" which fire before route setup)
                if any(kw in lower for kw in [
                    "tunnel up", "tunnel is up",
                    "vpn_ss_connected",
                ]):
                    with self._lock:
                        if self._status.state == ClientState.CONNECTING:
                            self._status.state = ClientState.CONNECTED
                            self._status.phase = ConnectPhase.TUNNEL_UP
                    # Force system DNS through the tunnel to prevent leaks
                    _enforce_dns_through_tunnel(self._status.log_lines)
                    self._notify()
        except Exception:
            pass

    def disconnect(self):
        """Stop the VPN connection."""
        if self._process:
            try:
                self._process.send_signal(signal.SIGTERM)
                try:
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    self._process.wait()
            except Exception:
                pass
            self._process = None

        if self._config_path and os.path.exists(self._config_path):
            try:
                os.unlink(self._config_path)
            except Exception:
                pass
        self._config_path = None

        # Restore original DNS settings
        _restore_dns(self._status.log_lines)

        self._start_time = 0.0
        with self._lock:
            self._status.state = ClientState.DISCONNECTED
            self._status.phase = ConnectPhase.IDLE
            self._status.server_name = ""
            self._status.started_at = None
        self._notify()

    def is_connected(self) -> bool:
        return (
            self._process is not None
            and self._process.poll() is None
            and self._status.state == ClientState.CONNECTED
        )

    def _set_error(self, msg: str):
        with self._lock:
            self._status.state = ClientState.ERROR
            self._status.phase = ConnectPhase.FAILED
            self._status.error = msg
            self._status.log_lines.append(
                f"[{_ts()}] ERROR: {msg[:200]}"
            )
        self._notify()

    def get_logs(self, n: int = 50) -> str:
        return "\n".join(self._status.log_lines[-n:])

    def get_full_logs(self) -> str:
        return "\n".join(self._status.log_lines)

    def restart(self, profile) -> bool:
        self.disconnect()
        time.sleep(1)
        return self.connect(profile)


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:12]


def _format_crash_log(log_lines: list) -> str:
    """Format crash log showing first 30 lines (where errors occur) + last 10 (shutdown context).

    The error/failure lines appear early in the log; the last lines are always
    clean shutdown noise (DNS teardown, vpn_close) that hides the real cause.
    """
    if not log_lines:
        return "--- no log output ---"
    head = log_lines[:30]
    tail = log_lines[-10:] if len(log_lines) > 30 else []
    parts = ["--- first 30 log lines (errors appear here) ---"]
    parts.extend(head)
    if tail:
        parts.append(f"--- last 10 lines (shutdown noise, {len(log_lines)} total) ---")
        parts.extend(tail)
    parts.append("--- end of log ---")
    return "\n".join(parts)
