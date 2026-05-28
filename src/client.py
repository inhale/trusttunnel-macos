"""TrustTunnel client process manager — manages the trusttunnel_client subprocess.

Now with pre-flight checks, phased connection progress, and rich diagnostics.
"""

import os
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

        # ── Pre-flight 3: write config ──
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
                            self._status.error = line.strip()
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
