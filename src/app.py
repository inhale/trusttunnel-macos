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
    """Return (ok: bool, message: str). Does NOT show dialogs — caller decides."""
    if _TK_VERSION >= 8.6:
        return True, ""
    return False, _WARNING


# ── Entry widget factory (handles Tk 8.5 vs 8.6) ──────────────────
def _make_entry(parent, **kwargs):
    """Create an Entry that works on both Tk 8.5 (system) and 8.6 (Homebrew).

    On Tk 8.6+: uses ttk.Entry with 'Dark.TEntry' style for dark theme.
    On Tk 8.5:  falls back to tk.Entry WITHOUT bg/fg (system colors only)
                because Tk 8.5 ignores bg/fg on Entry on macOS, making
                it invisible on dark backgrounds.
    """
    if _TK_VERSION >= 8.6:
        # ttk.Entry respects fieldbackground/foreground via styles
        w = ttk.Entry(parent, style="Dark.TEntry", **kwargs)
    else:
        # tk.Entry on Tk 8.5: strip styling args — use system defaults
        safe_kwargs = {k: v for k, v in kwargs.items()
                       if k not in ('bg', 'fg', 'insertbackground', 'relief',
                                    'borderwidth', 'font')}
        # Keep font if provided (font works fine on 8.5)
        if 'font' in kwargs:
            safe_kwargs['font'] = kwargs['font']
        w = tk.Entry(parent, **safe_kwargs)
    return w


# ── Button factory (handles Tk 8.5 vs 8.6) ────────────────────────
# On Tk 8.5 the 'default' theme ignores custom style backgrounds/foregrounds
# on buttons — they render invisibly or with zero hit area.
# Fall back to plain tk.Button with explicit colours on 8.5.

_BUTTON_STYLES = {
    # style_name: (bg, fg, active_bg, font)
    "Accent.TButton":    ("#0078d4", "#ffffff", "#1a8ae8", ("Helvetica", 11, "bold")),
    "Dark.TButton":      ("#3a3a3a", "#ffffff", "#4a4a4a", ("Helvetica", 11)),
    "Red.TButton":       ("#f44747", "#ffffff", "#d63a3a", ("Helvetica", 11, "bold")),
    "SmallDark.TButton": ("#3a3a3a", "#ffffff", "#4a4a4a", ("Helvetica", 9)),
}

def _make_button(parent, text, command, style="Dark.TButton", **kwargs):
    """Create a Button that works on both Tk 8.5 and 8.6.

    On Tk 8.6+: uses ttk.Button with the given named style.
    On Tk 8.5:  uses tk.Button with explicit bg/fg colours because ttk
                custom styles render invisible/unclickable on macOS Tk 8.5.
    """
    if _TK_VERSION >= 8.6:
        return ttk.Button(parent, text=text, command=command,
                          style=style, **kwargs)
    # Tk 8.5 fallback — plain tk.Button with hardcoded colours
    bg, fg, active_bg, font = _BUTTON_STYLES.get(
        style, ("#3a3a3a", "#ffffff", "#4a4a4a", ("Helvetica", 11))
    )
    return tk.Button(
        parent, text=text, command=command,
        bg=bg, fg=fg, activebackground=active_bg, activeforeground=fg,
        font=font, relief="flat", borderwidth=0, cursor="hand2",
        **kwargs,
    )


def _setup_styles():
    style = ttk.Style()
    style.theme_use("default")  # 'aqua' has issues with custom colours

    style.configure("Dark.TFrame", background="#1e1e1e")
    style.configure("Dark.TLabel", background="#1e1e1e", foreground="#d4d4d4")
    style.configure("DarkTitle.TLabel", background="#252525", foreground="#d4d4d4")
    style.configure("DarkBold.TLabel", background="#1e1e1e", foreground="#d4d4d4",
                    font=("Helvetica", 11, "bold"))
    style.configure("Accent.TButton", background="#0078d4", foreground="#ffffff",
                    font=("Helvetica", 11, "bold"))
    style.map("Accent.TButton",
              background=[("active", "#1a8ae8")])

    style.configure("Dark.TButton", background="#3a3a3a", foreground="#ffffff",
                    font=("Helvetica", 11), borderwidth=0)
    style.map("Dark.TButton",
              background=[("active", "#4a4a4a")])

    style.configure("Red.TButton", background="#f44747", foreground="#ffffff",
                    font=("Helvetica", 11, "bold"))
    style.map("Red.TButton",
              background=[("active", "#d63a3a")])

    style.configure("SmallDark.TButton", background="#3a3a3a", foreground="#ffffff",
                    font=("Helvetica", 9), borderwidth=0)
    style.map("SmallDark.TButton",
              background=[("active", "#4a4a4a")])

    style.configure("Treeview", background="#2d2d2d", foreground="#d4d4d4",
                    fieldbackground="#2d2d2d", rowheight=26, borderwidth=0)
    style.configure("Treeview.Heading", background="#3a3a3a", foreground="#d4d4d4",
                    relief="flat", borderwidth=0,
                    font=("Helvetica", 10, "bold"))
    style.map("Treeview",
              background=[("selected", "#0078d4")],
              foreground=[("selected", "white")])

    style.configure("DarkConsole.TFrame", background="#0d0d0d")
    style.configure("TNotebook", background="#1e1e1e", borderwidth=0)
    style.configure("TNotebook.Tab", background="#2a2a2a", foreground="#d4d4d4",
                    padding=[16, 6], borderwidth=0)
    style.map("TNotebook.Tab",
              background=[("selected", "#1e1e1e")])

    # Dark entry fields
    style.configure("Dark.TEntry", fieldbackground="#1a1a1a",
                    foreground="#e0e0e0", insertcolor="#e0e0e0",
                    borderwidth=0)
    style.map("Dark.TEntry",
              fieldbackground=[("focus", "#1a1a1a")])

    # Dark text widget (simulated via style — actual Text styling is per-widget)
    style.configure("DarkConsole.TFrame", background="#0d0d0d")

# ── colours for tk widgets that don't use ttk ─────────────────────
BG = "#1e1e1e"
FG = "#d4d4d4"
INPUT_BG = "#3a3a3a"   # lighter for contrast
CONSOLE_BG = "#0d0d0d"
ACCENT = "#0078d4"
ERROR_RED = "#f44747"
SUCCESS_GREEN = "#4ec9b0"
WARNING_YELLOW = "#cca700"


class AddEditDialog(tk.Toplevel):
    """Modal form dialog using standard tk widgets (most reliable)."""

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

        # grab_set() AFTER widgets are built and window is mapped —
        # calling it before causes silent grab failure on some Tk versions,
        # making all fields and buttons unresponsive.
        self.update_idletasks()
        self.deiconify()
        self.lift()
        self.focus_force()
        self.grab_set()

    def _build(self):
        # Main form area — lighter background so inputs stand out
        form = tk.Frame(self, bg="#2a2a2a", padx=20, pady=16)
        form.pack(fill="both", expand=True)

        fields = [
            ("Name", "name", False),
            ("Hostname", "hostname", False),
            ("Address (ip:port)", "address", False),
            ("Username", "username", False),
            ("Password", "password", True),
            ("Bound Interface (optional)", "bound_if", False),
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
                w = tk.Text(row, height=4, width=42,
                            bg="#1a1a1a", fg="#e0e0e0",
                            insertbackground="#e0e0e0",
                            relief="solid", borderwidth=1,
                            font=("Menlo", 9))
                w.pack(side="left", fill="x", expand=True)
            elif is_password:
                w = _make_entry(row, show="*", width=42,
                                font=("Helvetica", 11))
                w.pack(side="left")
            else:
                w = _make_entry(row, width=42,
                                font=("Helvetica", 11))
                w.pack(side="left")

            self._entries[key] = w

        # Pre-fill
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

        # Buttons
        btn_frame = tk.Frame(form, bg="#2a2a2a")
        btn_frame.pack(fill="x", pady=(16, 0))

        _make_button(btn_frame, text="Cancel", command=self.destroy,
                     style="Dark.TButton").pack(side="left", padx=(0, 10))

        _make_button(btn_frame, text="Save", command=self._save,
                     style="Accent.TButton").pack(side="left")

    def _save(self):
        name = self._entries["name"].get().strip()
        hostname = self._entries["hostname"].get().strip()
        address = self._entries["address"].get().strip()
        username = self._entries["username"].get().strip()
        password = self._entries["password"].get()
        bound_if = self._entries["bound_if"].get().strip()
        cert = self._entries["certificate"]
        certificate = cert.get("1.0", "end-1c").strip() if isinstance(cert, tk.Text) else cert.get().strip()

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
        self.result = (self._profile or ServerProfile(name=name, endpoint=ep))
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

        self.client = ClientManager()
        self.servers: list[ServerProfile] = load_servers()
        self._selected_index: Optional[int] = None

        self._build()
        self._refresh_server_list()
        self.geometry("820x600")
        self.minsize(500, 400)

        # Tk version warning (non-blocking — shown in console, not as popup)
        ok, msg = _check_tk_version(self)
        if not ok:
            self._log("⚠ Tk version too old — widgets may be broken.")
            self._log("   Install Homebrew Python: brew install python@3.11")
            self._log("   Then: /usr/local/bin/python3.11 -m src")

        self._poll_status()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

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

        # ── Notebook: Servers + Bypass tabs ──
        # PanedWindow wraps notebook + console for resizable split
        self._main_pane = ttk.PanedWindow(self, orient="vertical")
        self._main_pane.pack(fill="both", expand=True, padx=8, pady=(4, 0))

        # Top pane: notebook
        notebook_frame = tk.Frame(self._main_pane, bg=BG)
        self._main_pane.add(notebook_frame, weight=3)

        self._notebook = ttk.Notebook(notebook_frame)
        self._notebook.pack(fill="both", expand=True)

        # ── Tab 1: Servers ──
        servers_tab = tk.Frame(self._notebook, bg=BG)
        self._notebook.add(servers_tab, text="Servers")

        table_frame = tk.LabelFrame(servers_tab, text=" Servers ", bg=BG, fg="#888",
                                    font=("Helvetica", 9, "bold"),
                                    padx=4, pady=4)
        table_frame.pack(fill="both", expand=True)

        cols = ("name", "hostname", "address", "username", "status")
        self._tree = ttk.Treeview(table_frame, columns=cols,
                                  show="headings", selectmode="browse")
        self._tree.heading("name", text="Name", anchor="w")
        self._tree.heading("hostname", text="Hostname", anchor="w")
        self._tree.heading("address", text="Address", anchor="w")
        self._tree.heading("username", text="Username", anchor="w")
        self._tree.heading("status", text="Status", anchor="w")
        self._tree.column("name", width=110, minwidth=60)
        self._tree.column("hostname", width=110, minwidth=60)
        self._tree.column("address", width=150, minwidth=80)
        self._tree.column("username", width=90, minwidth=50)
        self._tree.column("status", width=80, minwidth=60)
        self._tree.pack(fill="both", expand=True, side="left")

        vsb = ttk.Scrollbar(table_frame, orient="vertical",
                           command=self._tree.yview)
        vsb.pack(side="right", fill="y")
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.bind("<<TreeviewSelect>>", self._on_server_select)
        self._tree.bind("<Double-1>", lambda e: self._connect_selected())

        # ── Tab 2: Bypass ──
        bypass_tab = tk.Frame(self._notebook, bg=BG)
        self._notebook.add(bypass_tab, text="Bypass")

        bypass_info = tk.Label(bypass_tab, bg=BG, fg="#888",
                               text="Domains and IPs that will bypass the VPN tunnel.\n"
                                    "Use masks: *.ru, *.example.com, 192.168.0.0/16, *:443",
                               font=("Helvetica", 9), justify="left", anchor="w")
        bypass_info.pack(fill="x", padx=8, pady=(8, 4))

        # Exclusions list
        exc_list_frame = tk.Frame(bypass_tab, bg=BG)
        exc_list_frame.pack(fill="both", expand=True, padx=8)

        self._bypass_list = tk.Listbox(exc_list_frame, bg="#2d2d2d", fg=FG,
                                       selectbackground=ACCENT, selectforeground="white",
                                       relief="flat", borderwidth=4,
                                       font=("Menlo", 10), activestyle="none")
        self._bypass_list.pack(fill="both", expand=True, side="left")

        exc_sb = ttk.Scrollbar(exc_list_frame, orient="vertical",
                              command=self._bypass_list.yview)
        exc_sb.pack(side="right", fill="y")
        self._bypass_list.configure(yscrollcommand=exc_sb.set)

        # Add / Delete row
        exc_ctrl = tk.Frame(bypass_tab, bg=BG)
        exc_ctrl.pack(fill="x", padx=8, pady=(4, 8))

        self._bypass_entry = _make_entry(exc_ctrl, font=("Menlo", 10))
        self._bypass_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self._bypass_entry.bind("<Return>", lambda e: self._add_exclusion())

        _make_button(exc_ctrl, text="Add", command=self._add_exclusion,
                     style="Accent.TButton").pack(side="left", padx=2)

        _make_button(exc_ctrl, text="Delete", command=self._delete_exclusion,
                     style="Dark.TButton").pack(side="left", padx=2)

        self._bypass_status = tk.Label(bypass_tab, bg=BG, fg="#888",
                                       text="Select a server to manage bypass rules.",
                                       font=("Helvetica", 9), anchor="w")
        self._bypass_status.pack(fill="x", padx=8, pady=(0, 4))

        # Wire tab change to refresh bypass list
        self._notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        # ── Buttons (outside PanedWindow — always visible) ──
        btn_bar = tk.Frame(self, bg=BG)
        btn_bar.pack(fill="x", padx=8, pady=(4, 0))

        _make_button(btn_bar, text="+ Add", command=self._add_server,
                     style="Dark.TButton").pack(side="left", padx=1)
        _make_button(btn_bar, text="Edit", command=self._edit_server,
                     style="Dark.TButton").pack(side="left", padx=1)
        _make_button(btn_bar, text="Delete", command=self._delete_server,
                     style="Dark.TButton").pack(side="left", padx=1)
        _make_button(btn_bar, text="Import Link", command=self._import_deeplink,
                     style="Dark.TButton").pack(side="left", padx=1)

        self._btn_connect = _make_button(btn_bar, text="Connect",
                                         command=self._connect_selected,
                                         style="Accent.TButton")
        self._btn_connect.pack(side="right", padx=2)

        self._btn_disconnect = _make_button(btn_bar, text="Disconnect",
                                            command=self._disconnect,
                                            style="Red.TButton")

        # ── Console (bottom pane of PanedWindow) ──
        cons_frame = tk.LabelFrame(self._main_pane, text=" Console ", bg=BG, fg="#888",
                                   font=("Helvetica", 9, "bold"),
                                   padx=4, pady=4)
        self._main_pane.add(cons_frame, weight=1)

        self._console = tk.Text(cons_frame, bg=CONSOLE_BG, fg="#a0a0a0",
                                font=("Menlo", 10), wrap="word",
                                state="disabled", relief="flat",
                                borderwidth=4, insertbackground=FG,
                                height=7,
                                selectbackground="#3a5070",
                                selectforeground="#ffffff")
        self._console.pack(fill="both", expand=True, side="left")
        # Allow text selection and copy while keeping the widget read-only.
        # On macOS, state="disabled" blocks even selection — bind the standard
        # copy shortcuts explicitly so testers can copy error messages.
        def _allow_copy(event):
            # Let Ctrl-C / Cmd-C through; block everything else that would edit
            if event.keysym in ("c", "C") and (event.state & 0x8 or event.state & 0x4):
                return  # allow copy
            return "break"
        self._console.bind("<Key>", _allow_copy)
        # Also ensure clicking/dragging to select works (re-enable cursor)
        self._console.configure(cursor="arrow")

        csb = ttk.Scrollbar(cons_frame, orient="vertical",
                           command=self._console.yview)
        csb.pack(side="right", fill="y")
        self._console.configure(yscrollcommand=csb.set)

        btn_row = tk.Frame(cons_frame, bg=CONSOLE_BG)
        btn_row.pack(side="bottom", fill="x", padx=4, pady=2)
        _make_button(btn_row, text="Copy All", command=self._copy_console,
                     style="SmallDark.TButton").pack(side="right", padx=(2, 0))
        _make_button(btn_row, text="Clear", command=self._clear_console,
                     style="SmallDark.TButton").pack(side="right")

    # ── CRUD ──────────────────────────────────────────────────────

    def _refresh_server_list(self):
        for item in self._tree.get_children():
            self._tree.delete(item)
        for i, s in enumerate(self.servers):
            addr = ",".join(s.endpoint.addresses) if s.endpoint.addresses else ""
            active = self.client.is_connected() and self.client.status.server_name == s.name
            self._tree.insert("", "end", iid=str(i), values=(
                s.name, s.endpoint.hostname, addr,
                s.endpoint.username, "connected" if active else "idle",
            ), tags=("connected" if active else "",))
        self._tree.tag_configure("connected", background="#1a3a2a",
                                 foreground=SUCCESS_GREEN)

    def _save_and_refresh(self):
        save_servers(self.servers)
        self._refresh_server_list()

    def _on_server_select(self, event=None):
        sel = self._tree.selection()
        self._selected_index = int(sel[0]) if sel else None
        self._refresh_bypass_list()

    # ── Bypass (exclusions) ──────────────────────────────────────

    def _on_tab_changed(self, event=None):
        self._refresh_bypass_list()

    def _refresh_bypass_list(self):
        """Reload exclusions for the selected server."""
        self._bypass_list.delete(0, "end")
        if self._selected_index is None:
            self._bypass_status.configure(
                text="Select a server in the Servers tab to manage bypass rules.",
                fg="#888")
            return

        profile = self.servers[self._selected_index]
        exclusions = profile.exclusions

        self._bypass_status.configure(
            text=f"Bypass rules for: {profile.name} ({len(exclusions)} rules)",
            fg="#888")

        for exc in exclusions:
            self._bypass_list.insert("end", f"  {exc}")

    def _add_exclusion(self):
        """Add a new exclusion mask."""
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
        """Delete selected exclusion."""
        sel = self._bypass_list.curselection()
        if not sel:
            return
        if self._selected_index is None:
            return

        profile = self.servers[self._selected_index]
        idx = sel[0]
        if 0 <= idx < len(profile.exclusions):
            profile.exclusions.pop(idx)
            save_servers(self.servers)
            self._refresh_bypass_list()

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

        # Must update + grab AFTER widgets are packed and window is mapped.
        # Calling grab_set() before the window is visible causes it to fail
        # silently on some Tk versions — fields become unclickable.
        dlg.update_idletasks()
        dlg.deiconify()
        dlg.lift()
        dlg.focus_force()
        dlg.grab_set()
        e.focus_set()

    # ── Connection ─────────────────────────────────────────────────

    def _connect_selected(self):
        if self._selected_index is None:
            messagebox.showinfo("Note", "Select a server first.")
            return
        profile = self.servers[self._selected_index]
        self._log(f"--- Connecting to {profile.name} ---")

        def do_connect():
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

    # ── Console ────────────────────────────────────────────────────

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
        """Copy all console text to the system clipboard."""
        text = self._console.get("1.0", "end-1c")
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()  # flush clipboard on macOS

    # ── Polling ────────────────────────────────────────────────────

    def _poll_status(self):
        try:
            status = self.client.status
            state = status.state

            dots = {ClientState.DISCONNECTED: ("", "#666", "Disconnected"),
                    ClientState.CHECKING: ("\u25cf", WARNING_YELLOW, "Checking..."),
                    ClientState.CONNECTING: ("\u25cf", WARNING_YELLOW,
                                             f"Connecting [{status.phase.value}]"),
                    ClientState.CONNECTED: ("\u25cf", SUCCESS_GREEN,
                                            f"Connected - {status.server_name}"),
                    ClientState.ERROR: ("\u25cf", ERROR_RED, "Error")}
            dot, color, label = dots.get(state, ("", "#666", state.value))

            self._status_dot.configure(text=dot, fg=color)
            self._status_text.configure(text=label, fg=color)

            # Log new lines
            lines = status.log_lines
            if not hasattr(self, "_log_idx"):
                self._log_idx = 0
            for line in lines[self._log_idx:]:
                self._log(line)
            self._log_idx = len(lines)

            # Buttons
            if state == ClientState.CONNECTED:
                self._btn_connect.pack_forget()
                self._btn_disconnect.pack(side="right", padx=2)
            elif state == ClientState.CONNECTING:
                self._btn_connect.pack_forget()
                self._btn_disconnect.pack(side="right", padx=2)
            else:
                self._btn_disconnect.pack_forget()
                self._btn_connect.pack(side="right", padx=2)

        except Exception:
            pass
        self.after(300, self._poll_status)

    def _on_close(self):
        if self.client.is_connected():
            if messagebox.askyesno("Quit", "Disconnect and quit?", parent=self):
                self.client.disconnect()
            else:
                return
        self.destroy()


def main():
    app = TrustTunnelWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
