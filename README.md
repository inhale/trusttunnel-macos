# TrustTunnel macOS GUI

A native macOS GUI client for the [TrustTunnel VPN protocol](https://github.com/TrustTunnel/TrustTunnel).
Dark-themed, with server management, tray icon, and embedded console.

## Features

- **Native PyQt6 UI** — clean dark theme, proper macOS look and feel (no tkinter)
- **Menu bar tray icon** — colored by status (grey/yellow/green/red), double-click to restore
- **Tray menu** — connect/disconnect servers, add server, import `tt://` links, show window, quit
- **Minimize to tray** — closing the window hides it to tray instead of quitting
- **Multi-server profiles** — add, edit, delete, import from `tt://` deep-links
- **Tabs** — Servers (manage connections) + Bypass (split tunneling exclusion masks)
- **Split tunneling** — bypass VPN for specific domains: `*.ru`, `*.example.com`, CIDR, `*:port`
- **Embedded console** — real-time VPN output in-app, no separate terminal
- **Kill switch, Post-Quantum, Anti-DPI** — full protocol feature support
- **HTTP/2 & HTTP/3 (QUIC)** protocol selection
- **DNS configuration** — plain UDP, DoT, DoH, DoQ, DoTCP
- **Deep-link import** — paste `tt://` URIs from endpoint exports (TOML-base64 + native TLV)

## Requirements

- macOS 11 (Big Sur) or later
- Python 3.11+ (Homebrew or MacPorts)
- **Sudo setup** (one-time, see below)

## Install Python

### Homebrew (recommended)

```bash
brew install python@3.12
```

### MacPorts

```bash
sudo port install python312
```

## Build from source

```bash
# 1. Clone
git clone https://github.com/inhale/trusttunnel-macos.git
cd trusttunnel-macos

# 2. Install Python 3.11+ (see above, one-time)

# 3. One-command build (installs deps, generates icon, builds .app, codesigns, installs)
./build-app.sh
```

Build output: `dist/TrustTunnel.app` → installed to `/Applications/TrustTunnel.app`

## Dev run (no build)

```bash
pip install PyQt6 Pillow
python3 -m src
```

## Usage

1. Launch TrustTunnel.app (or `python3 -m src`)
2. **Servers tab** → + Add — fill in name, hostname, address, username, password
3. Or **Import Link** — paste a `tt://` deep-link from your endpoint
4. Select a server → **Connect**
5. **Bypass tab** — add domain masks (`*.ru`, `*.example.com`) to exclude from VPN
6. **Close window** → app minimizes to tray; right-click tray icon for menu

### Tray icon states

| Color | Status |
|---|---|
| Grey | Disconnected |
| Yellow | Connecting / Checking |
| Green | Connected |
| Red | Error |

### Exporting deep-link from your endpoint

```bash
cd /opt/trusttunnel
sudo ./trusttunnel_endpoint vpn.toml hosts.toml -c myuser -a <PUBLIC_IP>:8443
```

Copy the `tt://` URI, use Import Link in the app.

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
- Installed app: `/Applications/TrustTunnel.app`

## Architecture

```
TrustTunnel.app
├── src/app.py            — PyQt6 main window, tray icon, server table, dialogs
├── src/client.py         — trusttunnel_client subprocess manager
├── src/config.py         — TOML profiles, deep-link parser
├── trusttunnel.spec      — PyInstaller build config
├── build-app.sh          — one-command .app builder
├── generate-icon.py      — shield icon generator (Pillow → .icns)
└── setup-sudo.sh         — one-time passwordless sudo config
```

## Sudo setup (one-time)

```bash
./setup-sudo.sh
```

Or manually:

```bash
sudo bash -c 'echo "$(whoami) ALL=(ALL) NOPASSWD: /Applications/TrustTunnel.app/Contents/Frameworks/bin/trusttunnel_client" > /etc/sudoers.d/trusttunnel'
```

## License

Apache 2.0 — same as TrustTunnel.
