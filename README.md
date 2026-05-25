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
- Python 3.11+ with Tkinter 8.6+ (Homebrew or MacPorts)
- **Sudo setup** (one-time, see below)

## Install Python with Tkinter

### Homebrew (recommended)

```bash
brew install python-tk@3.11
```

### MacPorts

```bash
sudo port install python311 py311-tkinter
```

## Build from source

```bash
# 1. Clone
git clone https://github.com/inhale/trusttunnel-macos.git
cd trusttunnel-macos

# 2. Install Python with Tkinter (see above, one-time)

# 3. One-command build
./build-app.sh
```

## Dev run (no build)

```bash
# Run directly with any Python 3.11+ that has tkinter
python3.11 -m src
# or
python3 -m src
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
