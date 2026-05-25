"""TrustTunnel macOS GUI — windowed app with server table, CRUD, embedded console."""

import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional

from .config import (
    ServerProfile, EndpointConfig,
    load_servers, save_servers, parse_deeplink,
)
from .client import ClientManager, ClientState, ClientStatus


# ── Tk version guard ───────────────────────────────────────────────
_TK_VERSION = tk.TkVersion

if _TK_VERSION < 8.6:
    _WARNING = (
        f"⚠ Tk {_TK_VERSION} detected — styled widgets will be broken.\n\n"
        "TrustTunnel requires Tk 8.6+ for proper rendering.\n"
        "Your system Python uses Tk 8.5 (deprecated).\n\n"
        "Fix (one-time):\n"
        "  brew install python@3.11\n"
        "  /usr/local/bin/python3.11 -m pip install toml\n"
        "  /usr/local/bin/python3.11 -m src\n\n"
        "Then make it default:\n"
        "  export PATH=\"/usr/local/bin:$PATH\"\n\n"
        "Continue anyway? (fields/buttons may be invisible)"
    )


def _check_tk_version(parent):
    if _TK_VERSION >= 8.6:
        return True, ""
    return False, _WARNING


# ── Entry widget factory ───────────────────────────────────────────
def _make_entry(parent, **kwargs):
    if _TK_VERSION >= 8.6:
        return ttk.Entry(parent, style="Dark.TEntry", **kwargs)
    safe_kwargs = {k: v for k, v in kwargs.items()
                   if k not in ('bg', 'fg', 'insertbackground', 'relief', 'borderwidth', 'font')}
    if 'font' in kwargs:
        safe_kwargs['font'] = kwargs['font']
    return tk.Entry(parent, **safe_kwargs)


# ── Button factory ─────────────────────────────────────────────────
_BUTTON_STYLES = {
    "Accent.TButton":      ("#0078d4", "#ffffff", "#1a8ae8", ("Helvetica", 11, "bold")),
    "Dark.TButton":        ("#3a3a3a", "#ffffff", "#4a4a4a", ("Helvetica", 11)),
    "Red.TButton":         ("#f44747", "#ffffff", "#d63a3a", ("Helvetica", 11, "bold")),
    "SmallDark.TButton":   ("#3a3a3a", "#ffffff", "#4a4a4a", ("Helvetica", 9)),
    "SmallRed.TButton":    ("#f44747", "#ffffff", "#d63a3a", ("Helvetica", 9, "bold")),
    "SmallAccent.TButton": ("#0078d4", "#ffffff", "#1a8ae8", ("Helvetica", 9, "bold")),
}

def _make_button(parent, text, command, style="Dark.TButton", **kwargs):
    if _TK_VERSION >= 8.6:
        return ttk.Button(parent, text=text, command=command, style=style, **kwargs)
    bg, fg, active_bg, font = _BUTTON_STYLES.get(
        style, ("#3a3a3a", "#ffffff", "#4a4a4a", ("Helvetica", 11)))
    return tk.Button(parent, text=text, command=command,
                     bg=bg, fg=fg, activebackground=active_bg, activeforeground=fg,
                     font=font, relief="flat", borderwidth=0, cursor="hand2", **kwargs)


# ── Styles ─────────────────────────────────────────────────────────
def _setup_styles():
    style = ttk.Style()
    # "clam" is the only ttk theme that reliably respects Treeview foreground
    # on macOS. "default" and "aqua" both ignore tag_configure/style.map
    # foreground for unselected rows — text renders as dark grey invisibly.
    try:
        style.theme_use("clam")
    except Exception:
        style.theme_use("default")

    style.configure("Dark.TFrame",      background="#1e1e1e")
    style.configure("Dark.TLabel",      background="#1e1e1e", foreground="#d4d4d4")
    style.configure("DarkTitle.TLabel", background="#252525", foreground="#d4d4d4")
    style.configure("DarkBold.TLabel",  background="#1e1e1e", foreground="#d4d4d4",
                    font=("Helvetica", 11, "bold"))

    style.configure("Accent.TButton", background="#0078d4", foreground="#ffffff",
                    font=("Helvetica", 11, "bold"))
    style.map("Accent.TButton", background=[("active", "#1a8ae8")])

    style.configure("Dark.TButton", background="#3a3a3a", foreground="#ffffff",
                    font=("Helvetica", 11), borderwidth=0)
    style.map("Dark.TButton", background=[("active", "#4a4a4a")])

    style.configure("Red.TButton", background="#f44747", foreground="#ffffff",
                    font=("Helvetica", 11, "bold"))
    style.map("Red.TButton", background=[("active", "#d63a3a")])

    style.configure("SmallDark.TButton", background="#3a3a3a", foreground="#ffffff",
                    font=("Helvetica", 9), borderwidth=0)
    style.map("SmallDark.TButton", background=[("active", "#4a4a4a")])

    style.configure("SmallRed.TButton", background="#f44747", foreground="#ffffff",
                    font=("Helvetica", 9, "bold"), borderwidth=0)
    style.map("SmallRed.TButton", background=[("active", "#d63a3a")])

    style.configure("SmallAccent.TButton", background="#0078d4", foreground="#ffffff",
                    font=("Helvetica", 9, "bold"), borderwidth=0)
    style.map("SmallAccent.TButton", background=[("active", "#1a8ae8")])

    style.configure("Treeview", background="#2d2d2d", foreground="#d4d4d4",
                    fieldbackground="#2d2d2d", rowheight=32, borderwidth=0)
    style.configure("Treeview.Heading", background="#3a3a3a", foreground="#d4d4d4",
                    relief="flat", borderwidth=0, font=("Helvetica", 10, "bold"))
    # macOS aqua theme overrides foreground even after configure() — must use
    # style.map to force the color for every widget state including the default.
    style.map("Treeview",
              background=[("selected", "#0078d4"), ("!selected", "#2d2d2d")],
              foreground=[("selected", "white"),   ("!selected", "#d4d4d4")])

    style.configure("TNotebook", background="#1e1e1e", borderwidth=0)
    style.configure("TNotebook.Tab", background="#2a2a2a", foreground="#d4d4d4",
                    padding=[16, 6], borderwidth=0)
    style.map("TNotebook.Tab", background=[("selected", "#1e1e1e")])

    style.configure("Dark.TEntry", fieldbackground="#1a1a1a",
                    foreground="#e0e0e0", insertcolor="#e0e0e0", borderwidth=0)
    style.map("Dark.TEntry", fieldbackground=[("focus", "#1a1a1a")])

    # Sash (divider) between panes — make it thin and dark
    style.configure("TPanedwindow", background="#1e1e1e")
    style.configure("Sash", sashthickness=4, relief="flat", background="#3a3a3a")


BG            = "#1e1e1e"
FG            = "#d4d4d4"
CONSOLE_BG    = "#0d0d0d"
ACCENT        = "#0078d4"
ERROR_RED     = "#f44747"
SUCCESS_GREEN = "#4ec9b0"
WARNING_YELLOW = "#cca700"


# ── macOS tray icon via PyObjC ─────────────────────────────────────
# PyObjC ships with every macOS Python install.
# The Tk mainloop on macOS pumps AppKit events, so NSStatusItem calls
# work fine from the main thread via after().
#
# KEY FIX for clickable menu items:
#   NSMenuItem with action=None is DISABLED by AppKit — it renders greyed
#   and won't fire any delegate callbacks.  Each item must have a real
#   selector set via setAction_() pointing to a method on a target object
#   set via setTarget_().  We use a single MenuTarget NSObject whose
#   itemClicked_() method dispatches by representedObject index.

def _build_tray_classes():
    """
    Build and return (TrayIcon class, available bool).
    Called once lazily so import errors on Linux are silenced.

    THREADING DESIGN
    ----------------
    itemClicked_ is called by AppKit on whatever thread it pleases.
    Calling any Tk API (including app.after()) from a non-Tk thread
    without the GIL held causes 'PyEval_RestoreThread: GIL released'
    abort (seen in practice with PyObjC 9+).

    performSelectorOnMainThread doesn't work either because PyObjC
    only exposes Python methods to ObjC if they follow strict naming
    conventions — _dispatch_: raises NSInvalidArgumentException.

    Safe solution: use an os.pipe as a lock-free message queue.
    itemClicked_ writes the key string to the write end (os.write is
    signal-safe and needs no GIL). The Tk mainloop polls the read end
    every 50 ms via after() on the main thread, reads the key, and
    dispatches — fully inside the Tk thread with the GIL held.
    """
    try:
        import AppKit
        import objc
        import os as _os

        class MenuTarget(AppKit.NSObject):
            """Receives NSMenuItem clicks; communicates back via a pipe."""

            def init(self):
                self = objc.super(MenuTarget, self).init()
                if self is None:
                    return None
                self._pipe_w = None   # write end; set by TrayIcon.setup()
                return self

            def itemClicked_(self, sender):
                # Pure Python + os.write — safe to call without GIL
                if self._pipe_w is None:
                    return
                try:
                    raw = sender.representedObject()
                    key = str(raw) if raw is not None else ""
                except Exception:
                    key = ""
                if not key:
                    return
                try:
                    data = (key + "\n").encode()
                    _os.write(self._pipe_w, data)
                except Exception:
                    pass

        class TrayIcon:
            _COLOR_MAP = {
                ClientState.DISCONNECTED: (0.40, 0.40, 0.40),
                ClientState.CHECKING:     (0.80, 0.67, 0.00),
                ClientState.CONNECTING:   (0.80, 0.67, 0.00),
                ClientState.CONNECTED:    (0.31, 0.79, 0.69),
                ClientState.ERROR:        (0.96, 0.28, 0.28),
            }

            def __init__(self, app):
                self._app = app
                self._AppKit = AppKit
                self._status_item = None
                self._target = None
                self._pipe_r = None
                self._pipe_w = None

            def setup(self):
                bar = AppKit.NSStatusBar.systemStatusBar()
                self._status_item = bar.statusItemWithLength_(
                    AppKit.NSVariableStatusItemLength)
                self._status_item.setHighlightMode_(True)

                # Pipe: itemClicked_ writes, Tk polls the read end
                self._pipe_r, self._pipe_w = _os.pipe()

                # Create and keep a permanent target object
                self._target = MenuTarget.alloc().init()
                self._target._pipe_w = self._pipe_w

                self._set_color(ClientState.DISCONNECTED)
                self._rebuild_menu()

                # Start polling the pipe from the Tk main thread
                self._app.after(50, self._poll_pipe)

            def _poll_pipe(self):
                """Read any pending keys from the pipe and dispatch. Tk main thread only."""
                import select
                try:
                    if self._pipe_r is None:
                        return
                    ready, _, _ = select.select([self._pipe_r], [], [], 0)
                    if ready:
                        data = _os.read(self._pipe_r, 4096).decode(errors="ignore")
                        for key in data.strip().splitlines():
                            key = key.strip()
                            if not key:
                                continue
                            app = self._app
                            if key == "__show__":
                                app.deiconify()
                            elif key == "__quit__":
                                app._on_close()
                            else:
                                try:
                                    idx = int(key)
                                    servers = list(app.servers)
                                    if idx < len(servers):
                                        connected_name = (
                                            app.client.status.server_name
                                            if app.client.is_connected() else None
                                        )
                                        if connected_name == servers[idx].name:
                                            app._disconnect()
                                        else:
                                            app._connect_by_index(idx)
                                except Exception:
                                    pass
                except Exception:
                    pass
                # Keep polling
                try:
                    self._app.after(50, self._poll_pipe)
                except Exception:
                    pass

            def _make_ns_image(self, r, g, b, size=18):
                img = AppKit.NSImage.alloc().initWithSize_((size, size))
                img.lockFocus()
                color = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
                    r, g, b, 1.0)
                color.set()
                path = AppKit.NSBezierPath.bezierPathWithOvalInRect_(
                    ((2, 2), (size - 4, size - 4)))
                path.fill()
                img.unlockFocus()
                img.setTemplate_(False)
                return img

            def _set_color(self, state):
                if not self._status_item:
                    return
                rgb = self._COLOR_MAP.get(state, (0.4, 0.4, 0.4))
                img = self._make_ns_image(*rgb)
                self._status_item.button().setImage_(img)
                self._status_item.button().setTitle_("")

            def _rebuild_menu(self):
                if not self._status_item or not self._target:
                    return
                AppKit = self._AppKit
                menu = AppKit.NSMenu.alloc().init()
                menu.setAutoenablesItems_(False)

                connected_name = (
                    self._app.client.status.server_name
                    if self._app.client.is_connected() else None
                )

                for i, server in enumerate(self._app.servers):
                    is_conn = (connected_name == server.name)
                    label = f"✓ {server.name}" if is_conn else f"   {server.name}"
                    item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                        label, "itemClicked:", "")
                    item.setTarget_(self._target)
                    item.setRepresentedObject_(str(i))
                    item.setEnabled_(True)
                    menu.addItem_(item)

                menu.addItem_(AppKit.NSMenuItem.separatorItem())

                for label, key in [("Show Window", "__show__"), ("Quit", "__quit__")]:
                    item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                        label, "itemClicked:", "")
                    item.setTarget_(self._target)
                    item.setRepresentedObject_(key)
                    item.setEnabled_(True)
                    menu.addItem_(item)

                self._status_item.setMenu_(menu)

            def update(self, state):
                if not self._status_item:
                    return
                self._set_color(state)
                self._rebuild_menu()

            def stop(self):
                if self._status_item:
                    try:
                        self._AppKit.NSStatusBar.systemStatusBar().removeStatusItem_(
                            self._status_item)
                    except Exception:
                        pass
                for fd in (self._pipe_r, self._pipe_w):
                    try:
                        if fd is not None:
                            _os.close(fd)
                    except Exception:
                        pass
                self._pipe_r = None
                self._pipe_w = None

        return TrayIcon, True

    except Exception:
        # PyObjC not available (Linux dev machine etc.)
        class _NoopTray:
            def __init__(self, app): pass
            def setup(self): pass
            def update(self, state): pass
            def stop(self): pass
        return _NoopTray, False


_TrayClass = None

def _get_tray_class():
    global _TrayClass
    if _TrayClass is None:
        _TrayClass, _ = _build_tray_classes()
    return _TrayClass


class AddEditDialog(tk.Toplevel):
    """Modal form dialog."""

    def __init__(self, parent, profile: Optional[ServerProfile] = None):
        super().__init__(parent)
        self.title("Edit Server" if profile else "Add Server")
        self.configure(bg="#252525")
        self.result: Optional[ServerProfile] = None
        self._profile = profile
        self.transient(parent)
        self._build()
        self.resizable(False, False)
        self.minsize(440, 360)
        self.update_idletasks()
        self.deiconify()
        self.lift()
        self.focus_force()
        self.grab_set()

    def _build(self):
        form = tk.Frame(self, bg="#2a2a2a", padx=20, pady=16)
        form.pack(fill="both", expand=True)

        fields = [
            ("Name",                       "name",        False),
            ("Hostname",                   "hostname",    False),
            ("Address (ip:port)",          "address",     False),
            ("Username",                   "username",    False),
            ("Password",                   "password",    True),
            ("Bound Interface (optional)", "bound_if",    False),
            ("Certificate PEM (optional)", "certificate", False),
        ]

        self._entries = {}
        for label_text, key, is_password in fields:
            row = tk.Frame(form, bg="#2a2a2a")
            row.pack(fill="x", pady=3)
            tk.Label(row, text=label_text + ":", bg="#2a2a2a", fg="#cccccc",
                     anchor="e", width=20, font=("Helvetica", 10)).pack(
                side="left", padx=(0, 8))
            if key == "certificate":
                w = tk.Text(row, height=4, width=42, bg="#1a1a1a", fg="#e0e0e0",
                            insertbackground="#e0e0e0", relief="solid", borderwidth=1,
                            font=("Menlo", 9))
                w.pack(side="left", fill="x", expand=True)
            elif is_password:
                w = _make_entry(row, show="*", width=42, font=("Helvetica", 11))
                w.pack(side="left")
            else:
                w = _make_entry(row, width=42, font=("Helvetica", 11))
                w.pack(side="left")
            self._entries[key] = w

        if self._profile:
            ep = self._profile.endpoint
            self._entries["name"].insert(0, self._profile.name)
            self._entries["hostname"].insert(0, ep.hostname)
            self._entries["address"].insert(0, ",".join(ep.addresses))
            self._entries["username"].insert(0, ep.username)
            self._entries["password"].insert(0, ep.password)
            self._entries["bound_if"].insert(0, self._profile.tun.bound_if)
            if ep.certificate:
                self._entries["certificate"].insert("1.0", ep.certificate)

        bf = tk.Frame(form, bg="#2a2a2a")
        bf.pack(fill="x", pady=(16, 0))
        _make_button(bf, text="Cancel", command=self.destroy,
                     style="Dark.TButton").pack(side="left", padx=(0, 10))
        _make_button(bf, text="Save", command=self._save,
                     style="Accent.TButton").pack(side="left")

    def _save(self):
        name        = self._entries["name"].get().strip()
        hostname    = self._entries["hostname"].get().strip()
        address     = self._entries["address"].get().strip()
        username    = self._entries["username"].get().strip()
        password    = self._entries["password"].get()
        bound_if    = self._entries["bound_if"].get().strip()
        cert        = self._entries["certificate"]
        certificate = (cert.get("1.0", "end-1c").strip()
                       if isinstance(cert, tk.Text) else cert.get().strip())
        if not name or not hostname or not address or not username:
            messagebox.showwarning("Missing Fields",
                                   "Name, Hostname, Address, Username are required.",
                                   parent=self)
            return
        ep = EndpointConfig(
            hostname=hostname,
            addresses=[a.strip() for a in address.split(",") if a.strip()],
            username=username, password=password,
            certificate=certificate,
            skip_verification=not bool(certificate),
        )
        self.result = self._profile or ServerProfile(name=name, endpoint=ep)
        if self._profile:
            self._profile.name = name
            self._profile.endpoint = ep
            self._profile.tun.bound_if = bound_if
        else:
            self.result.tun.bound_if = bound_if
        self.destroy()


class TrustTunnelWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("TrustTunnel VPN")
        self.configure(bg=BG)

        _setup_styles()

        self.client  = ClientManager()
        self.servers: list[ServerProfile] = load_servers()
        self._selected_index: Optional[int] = None
        self._last_state: Optional[ClientState] = None
        self._row_buttons: list[tk.Widget] = []

        self._build()
        self._refresh_server_list()
        self.geometry("860x640")
        self.minsize(520, 440)

        ok, msg = _check_tk_version(self)
        if not ok:
            self._log("⚠ Tk version too old — widgets may be broken.")
            self._log("   Install Homebrew Python: brew install python@3.11")
            self._log("   Then: /usr/local/bin/python3.11 -m src")

        self._tray = _get_tray_class()(self)
        self.after(200, self._tray.setup)

        self._poll_status()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Layout ────────────────────────────────────────────────────

    def _build(self):
        # ── Title bar ──
        title = tk.Frame(self, bg="#252525", height=34)
        title.pack(fill="x")
        title.pack_propagate(False)

        tk.Label(title, text="  TrustTunnel VPN", bg="#252525", fg=FG,
                 font=("Helvetica", 12, "bold")).pack(side="left", pady=4)
        self._status_dot = tk.Label(title, text="", bg="#252525", fg="#666",
                                    font=("Helvetica", 13))
        self._status_dot.pack(side="left", padx=(8, 0))
        self._status_text = tk.Label(title, text="Disconnected", bg="#252525",
                                     fg="#888", font=("Helvetica", 10))
        self._status_text.pack(side="left", padx=4)

        # ── Servers button bar — packed LAST at bottom so PanedWindow
        #    can never cover it regardless of sash position ──
        servers_btn_bar = tk.Frame(self, bg=BG)
        servers_btn_bar.pack(side="bottom", fill="x", padx=8, pady=(0, 4))

        _make_button(servers_btn_bar, text="+ Add",       command=self._add_server,
                     style="Dark.TButton").pack(side="left", padx=1)
        _make_button(servers_btn_bar, text="Edit",        command=self._edit_server,
                     style="Dark.TButton").pack(side="left", padx=1)
        _make_button(servers_btn_bar, text="Delete",      command=self._delete_server,
                     style="Dark.TButton").pack(side="left", padx=1)
        _make_button(servers_btn_bar, text="Import Link", command=self._import_deeplink,
                     style="Dark.TButton").pack(side="left", padx=1)

        # ── PanedWindow: notebook on top, console below — both resizable ──
        self._pane = ttk.PanedWindow(self, orient="vertical")
        self._pane.pack(fill="both", expand=True, padx=8, pady=(4, 0))

        # ── Top pane: notebook ──
        nb_frame = tk.Frame(self._pane, bg=BG)
        self._pane.add(nb_frame, weight=2)   # notebook gets 2/5

        self._notebook = ttk.Notebook(nb_frame)
        self._notebook.pack(fill="both", expand=True)

        # ── Tab 1: Servers ──
        servers_tab = tk.Frame(self._notebook, bg=BG)
        self._notebook.add(servers_tab, text="Servers")

        # tree_frame holds the Treeview + transparent overlay frame for buttons
        tree_frame = tk.Frame(servers_tab, bg=BG)
        tree_frame.pack(fill="both", expand=True)

        cols = ("name", "hostname", "address", "username")
        self._tree = ttk.Treeview(tree_frame, columns=cols,
                                  show="headings", selectmode="browse")
        self._tree.heading("name",     text="Server",   anchor="w")
        self._tree.heading("hostname", text="Hostname", anchor="w")
        self._tree.heading("address",  text="Address",  anchor="w")
        self._tree.heading("username", text="Username", anchor="w")
        self._tree.column("name",     width=200, minwidth=100)
        self._tree.column("hostname", width=160, minwidth=80)
        self._tree.column("address",  width=170, minwidth=80)
        self._tree.column("username", width=110, minwidth=50)
        self._tree.pack(fill="both", expand=True)

        # Transparent overlay — a plain tk.Frame placed OVER the tree
        # using .place(). Buttons are children of this frame, NOT of the
        # Treeview, so the ttk theme cannot hijack their colors.
        self._btn_overlay = tk.Frame(tree_frame, bg="#2d2d2d",
                                     highlightthickness=0, bd=0)
        # Initial placement; updated by _place_row_buttons
        self._btn_overlay.place(x=0, y=0, width=0, height=0)

        self._tree.bind("<<TreeviewSelect>>", self._on_server_select)
        self._tree.bind("<Configure>",   lambda e: self.after(10, self._reposition_overlay))
        self._tree.bind("<MouseWheel>",  lambda e: self.after(10, self._place_row_buttons))
        self._tree.bind("<Button-4>",    lambda e: self.after(10, self._place_row_buttons))
        self._tree.bind("<Button-5>",    lambda e: self.after(10, self._place_row_buttons))

        # ── Tab 2: Bypass ──
        bypass_tab = tk.Frame(self._notebook, bg=BG)
        self._notebook.add(bypass_tab, text="Bypass")

        tk.Label(bypass_tab, bg=BG, fg="#888",
                 text="Domains and IPs that will bypass the VPN tunnel.\n"
                      "Use masks: *.ru, *.example.com, 192.168.0.0/16, *:443",
                 font=("Helvetica", 9), justify="left", anchor="w"
                 ).pack(fill="x", padx=8, pady=(8, 4))

        exc_list_frame = tk.Frame(bypass_tab, bg=BG)
        exc_list_frame.pack(fill="both", expand=True, padx=8)

        self._bypass_list = tk.Listbox(exc_list_frame, bg="#2d2d2d", fg=FG,
                                       selectbackground=ACCENT, selectforeground="white",
                                       relief="flat", borderwidth=4,
                                       font=("Menlo", 10), activestyle="none")
        self._bypass_list.pack(fill="both", expand=True)

        exc_ctrl = tk.Frame(bypass_tab, bg=BG)
        exc_ctrl.pack(fill="x", padx=8, pady=(4, 8))

        self._bypass_entry = _make_entry(exc_ctrl, font=("Menlo", 10))
        self._bypass_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self._bypass_entry.bind("<Return>", lambda e: self._add_exclusion())
        _make_button(exc_ctrl, text="Add",    command=self._add_exclusion,
                     style="Accent.TButton").pack(side="left", padx=2)
        _make_button(exc_ctrl, text="Delete", command=self._delete_exclusion,
                     style="Dark.TButton").pack(side="left", padx=2)

        self._bypass_status = tk.Label(bypass_tab, bg=BG, fg="#888",
                                       text="Select a server to manage bypass rules.",
                                       font=("Helvetica", 9), anchor="w")
        self._bypass_status.pack(fill="x", padx=8, pady=(0, 4))

        self._notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        # ── Bottom pane: console ──
        cons_frame = tk.LabelFrame(self._pane, text=" Console ", bg=BG, fg="#888",
                                   font=("Helvetica", 9, "bold"), padx=4, pady=4)
        self._pane.add(cons_frame, weight=3)   # console gets 3/5

        cons_inner = tk.Frame(cons_frame, bg=CONSOLE_BG)
        cons_inner.pack(fill="both", expand=True)

        csb = ttk.Scrollbar(cons_inner, orient="vertical")
        csb.pack(side="right", fill="y")

        self._console = tk.Text(cons_inner, bg=CONSOLE_BG, fg="#a0a0a0",
                                font=("Menlo", 10), wrap="word",
                                state="disabled", relief="flat", borderwidth=0,
                                insertbackground=FG,
                                selectbackground="#3a5070",
                                selectforeground="#ffffff",
                                yscrollcommand=csb.set)
        self._console.pack(fill="both", expand=True, side="left")
        csb.configure(command=self._console.yview)

        def _allow_copy(event):
            if event.keysym in ("c", "C") and (event.state & 0x8 or event.state & 0x4):
                return
            return "break"
        self._console.bind("<Key>", _allow_copy)
        self._console.configure(cursor="arrow")

        btn_row = tk.Frame(cons_frame, bg=CONSOLE_BG)
        btn_row.pack(side="bottom", fill="x", padx=4, pady=2)
        _make_button(btn_row, text="Copy All", command=self._copy_console,
                     style="SmallDark.TButton").pack(side="right", padx=(2, 0))
        _make_button(btn_row, text="Clear", command=self._clear_console,
                     style="SmallDark.TButton").pack(side="right")

        # Set initial sash position after window is drawn (40% notebook / 60% console)
        self.after(50, self._set_initial_sash)

    def _set_initial_sash(self):
        try:
            total = self._pane.winfo_height()
            if total > 10:
                self._pane.sashpos(0, int(total * 0.40))
        except Exception:
            self.after(100, self._set_initial_sash)

    # ── Overlay buttons ───────────────────────────────────────────

    def _reposition_overlay(self):
        """Resize the overlay frame to cover the tree area, then redraw buttons."""
        try:
            x = self._tree.winfo_x()
            y = self._tree.winfo_y()
            w = self._tree.winfo_width()
            h = self._tree.winfo_height()
            self._btn_overlay.place(x=x, y=y, width=w, height=h)
        except Exception:
            pass
        self._place_row_buttons()

    def _place_row_buttons(self):
        """
        Place tk.Button widgets inside _btn_overlay, aligned to each tree row.

        Buttons are children of _btn_overlay (a plain tk.Frame), NOT of the
        Treeview. This bypasses the ttk theme that would override bg/fg on
        tk.Button children of ttk widgets on macOS.
        """
        for w in self._row_buttons:
            try:
                w.destroy()
            except Exception:
                pass
        self._row_buttons = []

        connected_name = (
            self.client.status.server_name if self.client.is_connected() else None
        )
        state = self.client.status.state
        is_busy = state in (ClientState.CONNECTING, ClientState.CHECKING)

        # The overlay is positioned at (tree.x, tree.y) in the parent frame,
        # so button coords are relative to the tree origin.
        name_col_width = self._tree.column("name", option="width")
        btn_w, btn_h = 94, 22

        for iid in self._tree.get_children():
            bbox = self._tree.bbox(iid, "name")
            if not bbox:
                continue
            x, y, col_w, row_h = bbox

            idx = int(iid)
            if idx >= len(self.servers):
                continue
            server = self.servers[idx]
            is_conn = (connected_name == server.name)
            this_busy = is_busy and (connected_name == server.name)

            if this_busy:
                text, bg, fg, abg = "…",          "#444400", "#cca700", "#444400"
            elif is_conn:
                text, bg, fg, abg = "Disconnect",  "#6b1212", "#ff8080", "#d63a3a"
            else:
                text, bg, fg, abg = "Connect",     "#003060", "#80c8ff", "#0078d4"

            # Position at right edge of the name column, vertically centred
            bx = x + col_w - btn_w - 6
            by = y + (row_h - btn_h) // 2

            btn = tk.Button(
                self._btn_overlay,
                text=text,
                font=("Helvetica", 9, "bold"),
                bg=bg, fg=fg,
                activebackground=abg, activeforeground=fg,
                relief="flat", borderwidth=0, cursor="hand2",
                command=lambda i=idx: self._toggle_connection(i),
            )
            btn.place(x=bx, y=by, width=btn_w, height=btn_h)
            self._row_buttons.append(btn)

    # ── Server list ───────────────────────────────────────────────

    def _refresh_server_list(self):
        for item in self._tree.get_children():
            self._tree.delete(item)
        connected_name = (
            self.client.status.server_name if self.client.is_connected() else None
        )
        state = self.client.status.state
        for i, s in enumerate(self.servers):
            is_connected = (connected_name == s.name)
            is_busy = (state in (ClientState.CONNECTING, ClientState.CHECKING)
                       and connected_name == s.name)
            tag = "connected" if is_connected else ("busy" if is_busy else "normal")
            self._tree.insert("", "end", iid=str(i), values=(
                s.name,
                s.endpoint.hostname,
                ",".join(s.endpoint.addresses) if s.endpoint.addresses else "",
                s.endpoint.username,
            ), tags=(tag,))
        self._tree.tag_configure("normal",    background="#2d2d2d",  foreground="#d4d4d4")
        self._tree.tag_configure("connected", background="#1a3a2a",  foreground=SUCCESS_GREEN)
        self._tree.tag_configure("busy",      background="#2a2a1a",  foreground=WARNING_YELLOW)
        self.after(20, self._reposition_overlay)

    def _save_and_refresh(self):
        save_servers(self.servers)
        self._refresh_server_list()

    def _on_server_select(self, event=None):
        sel = self._tree.selection()
        self._selected_index = int(sel[0]) if sel else None
        self._refresh_bypass_list()

    def _toggle_connection(self, idx: int):
        connected_name = (
            self.client.status.server_name if self.client.is_connected() else None
        )
        if connected_name == self.servers[idx].name:
            self._disconnect()
        else:
            self._connect_by_index(idx)

    # ── Bypass ────────────────────────────────────────────────────

    def _on_tab_changed(self, event=None):
        self._refresh_bypass_list()

    def _refresh_bypass_list(self):
        self._bypass_list.delete(0, "end")
        if self._selected_index is None:
            self._bypass_status.configure(
                text="Select a server in the Servers tab to manage bypass rules.",
                fg="#888")
            return
        profile = self.servers[self._selected_index]
        self._bypass_status.configure(
            text=f"Bypass rules for: {profile.name} ({len(profile.exclusions)} rules)",
            fg="#888")
        for exc in profile.exclusions:
            self._bypass_list.insert("end", f"  {exc}")

    def _add_exclusion(self):
        mask = self._bypass_entry.get().strip()
        if not mask:
            return
        if self._selected_index is None:
            messagebox.showinfo("Note", "Select a server in the Servers tab first.")
            return
        profile = self.servers[self._selected_index]
        if mask not in profile.exclusions:
            profile.exclusions.append(mask)
            profile.exclusions.sort()
            self._bypass_entry.delete(0, "end")
            save_servers(self.servers)
            self._refresh_bypass_list()

    def _delete_exclusion(self):
        sel = self._bypass_list.curselection()
        if not sel or self._selected_index is None:
            return
        profile = self.servers[self._selected_index]
        idx = sel[0]
        if 0 <= idx < len(profile.exclusions):
            profile.exclusions.pop(idx)
            save_servers(self.servers)
            self._refresh_bypass_list()

    # ── CRUD ──────────────────────────────────────────────────────

    def _add_server(self):
        dlg = AddEditDialog(self)
        self.wait_window(dlg)
        if dlg.result:
            self.servers.append(dlg.result)
            self._save_and_refresh()
            idx = len(self.servers) - 1
            self._tree.selection_set(str(idx))
            self._tree.focus(str(idx))

    def _edit_server(self):
        if self._selected_index is None:
            messagebox.showinfo("Note", "Select a server to edit first.")
            return
        dlg = AddEditDialog(self, profile=self.servers[self._selected_index])
        self.wait_window(dlg)
        if dlg.result:
            self.servers[self._selected_index] = dlg.result
            self._save_and_refresh()

    def _delete_server(self):
        if self._selected_index is None:
            messagebox.showinfo("Note", "Select a server to delete first.")
            return
        s = self.servers[self._selected_index]
        if messagebox.askyesno("Delete", f"Delete '{s.name}'?", parent=self):
            self.servers.pop(self._selected_index)
            self._selected_index = None
            self._save_and_refresh()

    def _import_deeplink(self):
        dlg = tk.Toplevel(self)
        dlg.title("Import Deep-Link")
        dlg.configure(bg="#252525")
        dlg.transient(self)
        dlg.resizable(False, False)
        f = tk.Frame(dlg, bg="#252525", padx=16, pady=12)
        f.pack(fill="both", expand=True)
        tk.Label(f, text="Paste tt://? deep-link:", bg="#252525", fg="#ccc",
                 anchor="w", font=("Helvetica", 10)).pack(fill="x")
        e = tk.Text(f, height=2, width=55, bg="#1a1a1a", fg="#e0e0e0",
                    insertbackground="#e0e0e0", relief="solid", borderwidth=1,
                    font=("Menlo", 9))
        e.pack(fill="x", pady=6)
        try:
            e.insert("1.0", self.clipboard_get())
        except Exception:
            pass

        def do_import():
            uri = e.get("1.0", "end-1c").strip()
            if not uri:
                dlg.destroy(); return
            profile = parse_deeplink(uri)
            if profile:
                self.servers.append(profile)
                self._save_and_refresh()
                self._log(f"Imported: {profile.name}")
                dlg.destroy()
            else:
                messagebox.showwarning("Error", "Could not parse deep-link.", parent=dlg)

        bf = tk.Frame(f, bg="#252525")
        bf.pack(fill="x", pady=(8, 0))
        _make_button(bf, text="Cancel", command=dlg.destroy,
                     style="Dark.TButton").pack(side="left", padx=(0, 10))
        _make_button(bf, text="Import", command=do_import,
                     style="Accent.TButton").pack(side="left")
        dlg.update_idletasks()
        dlg.deiconify()
        dlg.lift()
        dlg.focus_force()
        dlg.grab_set()
        e.focus_set()

    # ── Connection ────────────────────────────────────────────────

    def _connect_by_index(self, idx: int):
        if idx >= len(self.servers):
            return
        profile = self.servers[idx]
        self._log(f"--- Connecting to {profile.name} ---")
        self._selected_index = idx

        def do_connect():
            if self.client.is_connected():
                self.client.disconnect()
            success = self.client.connect(profile)
            self.after(0, lambda: self._log(
                f"ERROR: {self.client.status.error}" if not success
                else f"Connected to {profile.name}"))
            self.after(0, self._refresh_server_list)

        threading.Thread(target=do_connect, daemon=True).start()

    def _disconnect(self):
        self._log("--- Disconnecting ---")
        self.client.disconnect()
        self._refresh_server_list()

    # ── Console ───────────────────────────────────────────────────

    def _log(self, text: str):
        self._console.configure(state="normal")
        self._console.insert("end", text + "\n")
        self._console.see("end")
        self._console.configure(state="disabled")

    def _clear_console(self):
        self._console.configure(state="normal")
        self._console.delete("1.0", "end")
        self._console.configure(state="disabled")

    def _copy_console(self):
        text = self._console.get("1.0", "end-1c")
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()

    # ── Polling ───────────────────────────────────────────────────

    def _poll_status(self):
        try:
            status = self.client.status
            state  = status.state

            dots = {
                ClientState.DISCONNECTED: ("",       "#666",         "Disconnected"),
                ClientState.CHECKING:     ("\u25cf", WARNING_YELLOW, "Checking..."),
                ClientState.CONNECTING:   ("\u25cf", WARNING_YELLOW,
                                           f"Connecting [{status.phase.value}]"),
                ClientState.CONNECTED:    ("\u25cf", SUCCESS_GREEN,
                                           f"Connected — {status.server_name}"),
                ClientState.ERROR:        ("\u25cf", ERROR_RED,      "Error"),
            }
            dot, color, label = dots.get(state, ("", "#666", state.value))
            self._status_dot.configure(text=dot, fg=color)
            self._status_text.configure(text=label, fg=color)

            lines = status.log_lines
            if not hasattr(self, "_log_idx"):
                self._log_idx = 0
            for line in lines[self._log_idx:]:
                self._log(line)
            self._log_idx = len(lines)

            if state != self._last_state:
                self._last_state = state
                self._refresh_server_list()
                self._tray.update(state)

        except Exception:
            pass
        self.after(300, self._poll_status)

    def _on_close(self):
        if self.client.is_connected():
            if messagebox.askyesno("Quit", "Disconnect and quit?", parent=self):
                self.client.disconnect()
            else:
                return
        self._tray.stop()
        self.destroy()


def main():
    app = TrustTunnelWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
