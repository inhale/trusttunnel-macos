# TrustTunnel macOS GUI

A native macOS windowed client for the [TrustTunnel VPN protocol](https://github.com/TrustTunnel/TrustTunnel).
Dark-themed, with server management, split tunneling, and embedded console.

## Features

- **Windowed UI** — traditional macOS window with resizable server list and console
- **Multi-server profiles** — add, edit, delete, import from `tt://?` deep-links
- **Tabs** — Servers (manage connections) + Bypass (split tunneling exclusion masks)
- **Split tunneling** — bypass VPN for specific domains: `*.ru`, `*.example.com`, CIDR, `*:port`
- **Embedded console** — real-time VPN output in-app, no separate terminal
- **Kill switch, Post-Quantum, Anti-DPI** — full protocol feature support
- **HTTP/2 & HTTP/3 (QUIC)** protocol selection
- **DNS configuration** — plain UDP, DoT, DoH, DoQ, DoTCP
- **Deep-link import** — paste `tt://?` URIs from endpoint exports (TOML-base64 + native TLV)

## Requirements

- macOS 11 (Big Sur) or later
- MacPorts (https://www.macports.org/)
- Python 3.11+ with Tkinter 8.6+ (via MacPorts)
- **Sudo setup** (one-time, see below)

## Why MacPorts?

macOS 13 (Ventura) and older are Tier 3 for Homebrew — builds fail.
MacPorts supports all macOS versions. TrustTunnel uses MacPorts Python 3.11.

## Install MacPorts

```bash
# Download from https://www.macports.org/install.php
# Then install:
sudo /opt/local/bin/port -v selfupdate
```

## Build from source

```bash
# 1. Clone
git clone https://github.com/inhale/trusttunnel-macos.git
cd trusttunnel-macos

# 2. Install MacPorts Python + Tkinter
sudo port install python311 py-tkinter

# 3. Install PyInstaller
/opt/local/bin/python3.11 -m pip install pyinstaller

# 4. One-command build
./build-app.sh
```

Output: `dist/TrustTunnel.app` — double-click to run.

## Dev run (no build)

```bash
# Install deps
/opt/local/bin/python3.11 -m pip install toml pyinstaller

# Run
/opt/local/bin/python3.11 -m src
```

## Usage

1. Launch TrustTunnel.app (or `python3 -m src`)
2. **Servers tab** → + Add — fill in name, hostname, address, username, password
3. Or **Import Link** — paste a `tt://?` deep-link from your endpoint
4. Select a server → **Connect**
5. **Bypass tab** — add domain masks (`*.ru`, `*.example.com`) to exclude from VPN

### Exporting deep-link from your endpoint

```bash
cd /opt/trusttunnel
sudo ./trusttunnel_endpoint vpn.toml hosts.toml -c myuser -a <PUBLIC_IP>:8443
```

Copy the `tt://?` URI, use Import Link in the app.

### Bypass / Split Tunneling

In the **Bypass** tab, add exclusion masks. These sites will NOT go through the VPN:

| Mask | Effect |
|---|---|
| `*.ru` | All `.ru` domains bypass |
| `*.google.com` | Google services bypass |
| `192.168.0.0/16` | Local network bypass |
| `*:443` | All HTTPS traffic bypass |

## File locations

- Settings: `~/.trusttunnel-gui/servers.toml`
- Build output: `dist/TrustTunnel.app`

## Architecture

```
TrustTunnel.app
├── src/app.py         — Tkinter window, tabs, UI
├── src/client.py      — trusttunnel_client subprocess manager
├── src/config.py      — TOML profiles, deep-link parser
├── trusttunnel.spec   — PyInstaller build config
└── build-app.sh       — one-command .app builder
```

## Sudo setup (one-time)

```bash
./setup-sudo.sh
```

Or manually:

```bash
sudo bash -c 'echo "$(whoami) ALL=(ALL) NOPASSWD: /Applications/TrustTunnel.app/Contents/Resources/bin/trusttunnel_client" > /etc/sudoers.d/trusttunnel'
```

## License

Apache 2.0 — same as TrustTunnel.
