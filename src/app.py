"""TrustTunnel macOS GUI — PyQt6 main window with server table, CRUD, embedded console."""

import os
import sys
import threading
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QSize
from PyQt6.QtGui import QFont, QColor, QIcon, QAction, QPixmap, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QHeaderView, QPushButton,
    QLabel, QLineEdit, QTextEdit, QDialog, QFormLayout,
    QTabWidget, QSplitter, QMessageBox, QAbstractItemView,
    QFrame, QSizePolicy, QSpacerItem, QMenuBar, QMenu,
    QStatusBar, QToolBar, QComboBox, QCheckBox, QSpinBox,
    QSystemTrayIcon,
)

from .config import (
    ServerProfile, EndpointConfig,
    load_servers, save_servers, parse_deeplink,
)
from .client import ClientManager, ClientState, ClientStatus


# ── Dark palette ──────────────────────────────────────────────────────────
def _dark_palette():
    from PyQt6.QtGui import QPalette
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor(30, 30, 30))
    p.setColor(QPalette.ColorRole.WindowText, QColor(212, 212, 212))
    p.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(45, 45, 45))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(40, 40, 40))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor(212, 212, 212))
    p.setColor(QPalette.ColorRole.Text, QColor(212, 212, 212))
    p.setColor(QPalette.ColorRole.Button, QColor(58, 58, 58))
    p.setColor(QPalette.ColorRole.ButtonText, QColor(212, 212, 212))
    p.setColor(QPalette.ColorRole.BrightText, QColor(255, 128, 128))
    p.setColor(QPalette.ColorRole.Highlight, QColor(0, 120, 212))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    return p


# ── Signal bridge for thread-safe UI updates ──────────────────────────────
class _SignalBridge(QObject):
    status_changed = pyqtSignal(object)  # ClientState
    log_line = pyqtSignal(str)


# ── Add/Edit Server Dialog ────────────────────────────────────────────────
class AddEditDialog(QDialog):
    def __init__(self, parent, profile: Optional[ServerProfile] = None):
        super().__init__(parent)
        self.setWindowTitle("Edit Server" if profile else "Add Server")
        self.setMinimumWidth(440)
        self._profile = profile
        self.result: Optional[ServerProfile] = None
        self._build()

    def _build(self):
        layout = QFormLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        self._entries = {}
        fields = [
            ("Name",        "name",        False),
            ("Hostname",    "hostname",    False),
            ("Address",     "address",     False),
            ("Username",    "username",    False),
            ("Password",    "password",    True),
            ("Interface",   "bound_if",    False),
        ]
        for label, key, is_password in fields:
            edit = QLineEdit()
            if is_password:
                edit.setEchoMode(QLineEdit.EchoMode.Password)
            self._entries[key] = edit
            layout.addRow(label + ":", edit)

        # Certificate (multi-line)
        cert_edit = QTextEdit()
        cert_edit.setPlaceholderText("Paste PEM certificate here (optional)")
        cert_edit.setMaximumHeight(80)
        self._entries["certificate"] = cert_edit
        layout.addRow("Certificate:", cert_edit)

        if self._profile:
            ep = self._profile.endpoint
            self._entries["name"].setText(self._profile.name)
            self._entries["hostname"].setText(ep.hostname)
            self._entries["address"].setText(",".join(ep.addresses))
            self._entries["username"].setText(ep.username)
            self._entries["password"].setText(ep.password)
            self._entries["bound_if"].setText(self._profile.tun.bound_if)
            if ep.certificate:
                cert_edit.setPlainText(ep.certificate)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("Save")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addRow(btn_row)

    def _save(self):
        name = self._entries["name"].text().strip()
        hostname = self._entries["hostname"].text().strip()
        address = self._entries["address"].text().strip()
        username = self._entries["username"].text().strip()
        password = self._entries["password"].text()
        bound_if = self._entries["bound_if"].text().strip()
        certificate = self._entries["certificate"].toPlainText().strip()

        if not name or not hostname or not address or not username:
            QMessageBox.warning(self, "Missing Fields",
                                "Name, Hostname, Address, Username are required.")
            return

        ep = EndpointConfig(
            hostname=hostname,
            addresses=[a.strip() for a in address.split(",") if a.strip()],
            username=username,
            password=password,
            certificate=certificate,
            skip_verification=not bool(certificate),
        )
        self.result = ServerProfile(name=name, endpoint=ep)
        self.result.tun.bound_if = bound_if
        self.accept()


# ── Import Deep-Link Dialog ───────────────────────────────────────────────
class ImportDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Import tt://")
        self.setMinimumWidth(440)
        self.result: Optional[ServerProfile] = None
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)

        layout.addWidget(QLabel("Paste tt:// deep-link:"))
        self._text = QTextEdit()
        self._text.setMaximumHeight(60)
        layout.addWidget(self._text)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        import_btn = QPushButton("Import")
        import_btn.setDefault(True)
        import_btn.clicked.connect(self._do_import)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(import_btn)
        layout.addLayout(btn_row)

    def _do_import(self):
        uri = self._text.toPlainText().strip()
        if not uri:
            self.reject()
            return
        profile = parse_deeplink(uri)
        if profile:
            self.result = profile
            self.accept()
        else:
            QMessageBox.warning(self, "Error", "Could not parse deep-link.")


# ── Main Window ────────────────────────────────────────────────────────────
class TrustTunnelWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TrustTunnel VPN")
        self.setMinimumSize(520, 440)
        self.resize(860, 640)

        self.client = ClientManager()
        self.servers: list[ServerProfile] = load_servers()
        self._selected_index: Optional[int] = None
        self._last_state = None
        self._log_idx = 0

        # Signal bridge for thread-safe UI
        self._bridge = _SignalBridge()
        self._bridge.status_changed.connect(self._on_status_changed)
        self._bridge.log_line.connect(self._on_log_line)

        self._build()

        # Tray icon — created with placeholder, updated by _update_tray_icon
        self._tray_icon = QSystemTrayIcon(self)
        self._tray_icon.setToolTip("TrustTunnel VPN — Disconnected")
        self._tray_menu = QMenu()
        self._tray_icon.setContextMenu(self._tray_menu)
        self._tray_icon.activated.connect(self._tray_activated)
        self._update_tray_icon(ClientState.DISCONNECTED)
        self._tray_icon.show()

        # Store per-server action references for enable/disable
        self._tray_server_actions: list[tuple[QAction, int]] = []

        # Now refresh server list (which also rebuilds tray menu)
        self._refresh_server_list()

        # Poll timer
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_status)
        self._poll_timer.start(300)

        self._quitting = False

    # ── Build UI ──────────────────────────────────────────────────────

    def _build(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Title bar ──
        title_bar = QHBoxLayout()
        title_bar.setContentsMargins(8, 4, 8, 4)
        title_label = QLabel("TrustTunnel VPN")
        title_label.setFont(QFont("Helvetica", 12, QFont.Weight.Bold))
        title_bar.addWidget(title_label)
        self._status_dot = QLabel("●")
        self._status_dot.setStyleSheet("color: #666; font-size: 13px;")
        title_bar.addWidget(self._status_dot)
        self._status_text = QLabel("Disconnected")
        self._status_text.setStyleSheet("color: #888; font-size: 10px;")
        title_bar.addWidget(self._status_text)
        title_bar.addStretch()
        main_layout.addLayout(title_bar)

        # ── Splitter: notebook on top, console below ──
        splitter = QSplitter(Qt.Orientation.Vertical)
        main_layout.addWidget(splitter)

        # Top: notebook with tabs
        self._notebook = QTabWidget()
        splitter.addWidget(self._notebook)
        splitter.setStretchFactor(0, 2)

        # ── Servers tab ──
        servers_tab = QWidget()
        servers_layout = QVBoxLayout(servers_tab)
        servers_layout.setContentsMargins(8, 4, 8, 4)
        servers_layout.setSpacing(4)

        # Toolbar: Add Server + Import tt:// on the right
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Servers"))
        toolbar.addStretch()
        import_btn = QPushButton("Import tt://")
        import_btn.clicked.connect(self._import_deeplink)
        toolbar.addWidget(import_btn)
        add_btn = QPushButton("+ Add Server")
        add_btn.clicked.connect(self._add_server)
        toolbar.addWidget(add_btn)
        servers_layout.addLayout(toolbar)

        # Server table
        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["Server", "Connect", "Hostname", "Address", "Username", ""]
        )
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        self._table.setAlternatingRowColors(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        # Column widths
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)   # Server name
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)      # Connect btn
        hdr.resizeSection(1, 90)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)   # Hostname
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)   # Address
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)   # Username
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)     # Actions
        hdr.resizeSection(5, 70)

        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        servers_layout.addWidget(self._table)

        self._notebook.addTab(servers_tab, "Servers")

        # ── Bypass tab ──
        bypass_tab = QWidget()
        bypass_layout = QVBoxLayout(bypass_tab)
        bypass_layout.setContentsMargins(8, 8, 8, 8)

        bypass_layout.addWidget(QLabel(
            "Domains and IPs that will bypass the VPN tunnel.\n"
            "Use masks: *.ru, *.example.com, 192.168.0.0/16, *:443"
        ))

        self._bypass_list = QTableWidget(0, 1)
        self._bypass_list.setHorizontalHeaderLabels(["Mask"])
        self._bypass_list.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._bypass_list.verticalHeader().setVisible(False)
        bypass_layout.addWidget(self._bypass_list)

        bypass_btn_row = QHBoxLayout()
        self._bypass_entry = QLineEdit()
        self._bypass_entry.setPlaceholderText("Add exclusion mask...")
        self._bypass_entry.returnPressed.connect(self._add_exclusion)
        bypass_btn_row.addWidget(self._bypass_entry)
        add_exc_btn = QPushButton("Add")
        add_exc_btn.clicked.connect(self._add_exclusion)
        bypass_btn_row.addWidget(add_exc_btn)
        del_exc_btn = QPushButton("Delete")
        del_exc_btn.clicked.connect(self._delete_exclusion)
        bypass_btn_row.addWidget(del_exc_btn)
        bypass_layout.addLayout(bypass_btn_row)

        self._bypass_status = QLabel("Select a server to manage bypass rules.")
        self._bypass_status.setStyleSheet("color: #888;")
        bypass_layout.addWidget(self._bypass_status)

        self._notebook.addTab(bypass_tab, "Bypass")

        # ── Console (bottom pane) ──
        console_frame = QWidget()
        console_layout = QVBoxLayout(console_frame)
        console_layout.setContentsMargins(4, 4, 4, 4)

        console_header = QHBoxLayout()
        console_header.addWidget(QLabel("Console"))
        console_header.addStretch()
        copy_btn = QPushButton("Copy All")
        copy_btn.clicked.connect(self._copy_console)
        console_header.addWidget(copy_btn)
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear_console)
        console_header.addWidget(clear_btn)
        console_layout.addLayout(console_header)

        self._console = QTextEdit()
        self._console.setReadOnly(True)
        self._console.setFont(QFont("Menlo", 10))
        console_layout.addWidget(self._console)

        splitter.addWidget(console_frame)
        splitter.setStretchFactor(1, 3)

    # ── Server list ───────────────────────────────────────────────────

    def _refresh_server_list(self):
        self._table.setRowCount(0)
        connected_name = (
            self.client.status.server_name if self.client.is_connected() else None
        )
        state = self.client.status.state

        for i, s in enumerate(self.servers):
            self._table.insertRow(i)

            is_connected = (connected_name == s.name)
            is_busy = (state in (ClientState.CONNECTING, ClientState.CHECKING)
                       and connected_name == s.name)

            # Colors
            if is_connected:
                row_bg, text_fg = QColor(13, 40, 24), QColor(78, 201, 176)
            elif is_busy:
                row_bg, text_fg = QColor(42, 42, 26), QColor(204, 167, 0)
            else:
                row_bg, text_fg = QColor(26, 26, 26), QColor(255, 255, 255)

            # Column 0: Server name
            name_item = QTableWidgetItem(s.name)
            name_item.setForeground(text_fg)
            name_item.setFont(QFont("Helvetica", 11, QFont.Weight.Bold))
            name_item.setBackground(row_bg)
            self._table.setItem(i, 0, name_item)

            # Column 1: Connect / Disconnect button
            if is_busy:
                btn_text, btn_color, btn_fg = "…", "#2a2a00", "#cca700"
            elif is_connected:
                btn_text, btn_color, btn_fg = "Disconnect", "#4a0a0a", "#ff8080"
            else:
                btn_text, btn_color, btn_fg = "Connect", "#002040", "#80c8ff"

            conn_btn = QPushButton(btn_text)
            conn_btn.setStyleSheet(
                f"background: {btn_color}; color: {btn_fg}; "
                f"border: none; border-radius: 3px; padding: 3px 8px; "
                f"font-weight: bold; font-size: 9pt;"
            )
            conn_btn.clicked.connect(lambda checked, idx=i: self._toggle_connection(idx))
            self._table.setCellWidget(i, 1, conn_btn)

            # Column 2: Hostname
            host_item = QTableWidgetItem(s.endpoint.hostname)
            host_item.setForeground(text_fg)
            host_item.setBackground(row_bg)
            self._table.setItem(i, 2, host_item)

            # Column 3: Address
            addr = ",".join(s.endpoint.addresses) if s.endpoint.addresses else ""
            addr_item = QTableWidgetItem(addr)
            addr_item.setForeground(text_fg)
            addr_item.setBackground(row_bg)
            self._table.setItem(i, 3, addr_item)

            # Column 4: Username
            user_item = QTableWidgetItem(s.endpoint.username)
            user_item.setForeground(text_fg)
            user_item.setBackground(row_bg)
            self._table.setItem(i, 4, user_item)

            # Column 5: Edit + Delete icons
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(2, 0, 2, 0)
            actions_layout.setSpacing(2)

            edit_btn = QPushButton("✎")
            edit_btn.setFixedSize(28, 24)
            edit_btn.setStyleSheet(
                "background: transparent; color: #888; border: none; font-size: 14px;"
            )
            edit_btn.clicked.connect(lambda checked, idx=i: self._edit_server_by_index(idx))
            actions_layout.addWidget(edit_btn)

            del_btn = QPushButton("✕")
            del_btn.setFixedSize(28, 24)
            del_btn.setStyleSheet(
                "background: transparent; color: #888; border: none; font-size: 14px;"
            )
            del_btn.clicked.connect(lambda checked, idx=i: self._delete_server_by_index(idx))
            actions_layout.addWidget(del_btn)

            self._table.setCellWidget(i, 5, actions_widget)

        # Select current row
        if self._selected_index is not None and self._selected_index < len(self.servers):
            self._table.selectRow(self._selected_index)

        self._rebuild_tray_menu()

    def _on_selection_changed(self):
        selected = self._table.selectedItems()
        if selected:
            self._selected_index = selected[0].row()
        else:
            self._selected_index = None
        self._refresh_bypass_list()

    # ── CRUD ──────────────────────────────────────────────────────────

    def _add_server(self):
        dlg = AddEditDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result:
            self.servers.append(dlg.result)
            self._save_and_refresh()
            self._selected_index = len(self.servers) - 1
            self._refresh_server_list()

    def _edit_server_by_index(self, idx: int):
        if idx >= len(self.servers):
            return
        dlg = AddEditDialog(self, profile=self.servers[idx])
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result:
            self.servers[idx] = dlg.result
            self._save_and_refresh()

    def _delete_server_by_index(self, idx: int):
        if idx >= len(self.servers):
            return
        s = self.servers[idx]
        reply = QMessageBox.question(
            self, "Delete", f"Delete '{s.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.servers.pop(idx)
            if self._selected_index is not None:
                if self._selected_index == idx:
                    self._selected_index = None
                elif self._selected_index > idx:
                    self._selected_index -= 1
            self._save_and_refresh()

    def _import_deeplink(self):
        dlg = ImportDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result:
            self.servers.append(dlg.result)
            self._save_and_refresh()
            self._log(f"Imported: {dlg.result.name}")

    def _save_and_refresh(self):
        save_servers(self.servers)
        self._refresh_server_list()

    # ── Bypass ────────────────────────────────────────────────────────

    def _refresh_bypass_list(self):
        self._bypass_list.setRowCount(0)
        if self._selected_index is None:
            self._bypass_status.setText(
                "Select a server in the Servers tab to manage bypass rules."
            )
            return
        profile = self.servers[self._selected_index]
        self._bypass_status.setText(
            f"Bypass rules for: {profile.name} ({len(profile.exclusions)} rules)"
        )
        for i, exc in enumerate(profile.exclusions):
            self._bypass_list.insertRow(i)
            self._bypass_list.setItem(i, 0, QTableWidgetItem(f"  {exc}"))

    def _add_exclusion(self):
        mask = self._bypass_entry.text().strip()
        if not mask or self._selected_index is None:
            return
        profile = self.servers[self._selected_index]
        if mask not in profile.exclusions:
            profile.exclusions.append(mask)
            profile.exclusions.sort()
            self._bypass_entry.clear()
            save_servers(self.servers)
            self._refresh_bypass_list()

    def _delete_exclusion(self):
        row = self._bypass_list.currentRow()
        if row < 0 or self._selected_index is None:
            return
        profile = self.servers[self._selected_index]
        if 0 <= row < len(profile.exclusions):
            profile.exclusions.pop(row)
            save_servers(self.servers)
            self._refresh_bypass_list()

    # ── Connection ────────────────────────────────────────────────────

    def _toggle_connection(self, idx: int):
        connected_name = (
            self.client.status.server_name if self.client.is_connected() else None
        )
        if connected_name == self.servers[idx].name:
            self._disconnect()
        else:
            self._connect_by_index(idx)

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
            if not success:
                self._bridge.log_line.emit(f"ERROR: {self.client.status.error}")
            else:
                self._bridge.log_line.emit(f"Connected to {profile.name}")
            self._bridge.status_changed.emit(self.client.status)

        threading.Thread(target=do_connect, daemon=True).start()

    def _disconnect(self):
        self._log("--- Disconnecting ---")
        self.client.disconnect()
        self._refresh_server_list()

    # ── Console ───────────────────────────────────────────────────────

    def _log(self, text: str):
        self._console.append(text)

    def _clear_console(self):
        self._console.clear()

    def _copy_console(self):
        self._console.selectAll()
        self._console.copy()

    # ── Status polling ────────────────────────────────────────────────

    def _poll_status(self):
        status = self.client.status
        state = status.state

        dots = {
            ClientState.DISCONNECTED: ("", "#666", "Disconnected"),
            ClientState.CHECKING:     ("●", "#cca700", "Checking..."),
            ClientState.CONNECTING:   ("●", "#cca700", f"Connecting [{status.phase.value}]"),
            ClientState.CONNECTED:    ("●", "#4ec9b0", f"Connected — {status.server_name}"),
            ClientState.ERROR:        ("●", "#f44747", "Error"),
        }
        dot, color, label = dots.get(state, ("", "#666", state.value))
        self._status_dot.setText(dot)
        self._status_dot.setStyleSheet(f"color: {color}; font-size: 13px;")
        self._status_text.setText(label)
        self._status_text.setStyleSheet(f"color: {color}; font-size: 10px;")

        # Append new log lines
        lines = status.log_lines
        if not hasattr(self, "_log_idx"):
            self._log_idx = 0
        for line in lines[self._log_idx:]:
            self._log(line)
        self._log_idx = len(lines)

        if state != self._last_state:
            self._last_state = state
            self._refresh_server_list()
            self._update_tray_icon(state)

    def _on_status_changed(self, status):
        self._refresh_server_list()

    def _on_log_line(self, line):
        self._log(line)

    # ── Close ─────────────────────────────────────────────────────────

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show()
            self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
            self.raise_()
            self.activateWindow()

    def _quit(self):
        self._quitting = True
        self.client.disconnect()
        self._tray_icon.hide()
        QApplication.quit()

    def _update_tray_icon(self, state: ClientState):
        """Update tray icon color and tooltip based on connection state."""
        # 16x16 icon with a shield/tunnel shape
        pm = QPixmap(16, 16)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        if state == ClientState.CONNECTED:
            color = QColor(78, 201, 176)  # green
        elif state in (ClientState.CONNECTING, ClientState.CHECKING):
            color = QColor(204, 167, 0)   # yellow
        elif state == ClientState.ERROR:
            color = QColor(244, 71, 71)   # red
        else:
            color = QColor(102, 102, 102) # grey

        # Draw a rounded rect "shield" icon
        p.setPen(QPen(color, 1))
        p.setBrush(color)
        p.drawRoundedRect(2, 1, 12, 14, 2, 2)
        # Draw a small "tunnel" hole
        p.setPen(QPen(QColor(30, 30, 30), 1))
        p.setBrush(QColor(30, 30, 30))
        p.drawEllipse(5, 5, 6, 6)
        p.end()

        icon = QIcon(pm)
        self._tray_icon.setIcon(icon)

        labels = {
            ClientState.DISCONNECTED: "Disconnected",
            ClientState.CHECKING: "Checking...",
            ClientState.CONNECTING: f"Connecting to {self.client.status.server_name}",
            ClientState.CONNECTED: f"Connected — {self.client.status.server_name}",
            ClientState.ERROR: f"Error — {self.client.status.server_name}",
        }
        self._tray_icon.setToolTip(f"TrustTunnel VPN — {labels.get(state, 'Unknown')}")

    def _rebuild_tray_menu(self):
        """Rebuild the tray context menu with server list."""
        self._tray_menu.clear()
        self._tray_server_actions.clear()

        connected_name = (
            self.client.status.server_name if self.client.is_connected() else None
        )

        # Server entries
        for i, profile in enumerate(self.servers):
            action = QAction(profile.name, self)
            if profile.name == connected_name:
                action.setCheckable(True)
                action.setChecked(True)
            action.triggered.connect(lambda checked, idx=i: self._tray_toggle(idx))
            self._tray_menu.addAction(action)
            self._tray_server_actions.append((action, i))

        if self.servers:
            self._tray_menu.addSeparator()

        # Add Server
        add_action = QAction("+ Add Server", self)
        add_action.triggered.connect(self._add_server_from_tray)
        self._tray_menu.addAction(add_action)

        # Import tt://
        import_action = QAction("Import tt://", self)
        import_action.triggered.connect(self._import_from_tray)
        self._tray_menu.addAction(import_action)

        self._tray_menu.addSeparator()

        # Show
        show_action = QAction("Show Window", self)
        show_action.triggered.connect(self._show_from_tray)
        self._tray_menu.addAction(show_action)

        # Quit
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self._quit)
        self._tray_menu.addAction(quit_action)

    def _tray_toggle(self, idx: int):
        """Toggle connection for a server from tray menu."""
        self._toggle_connection(idx)
        self._show_from_tray()

    def _add_server_from_tray(self):
        self._add_server()
        self._show_from_tray()

    def _import_from_tray(self):
        self._import_deeplink()
        self._show_from_tray()

    def _show_from_tray(self):
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        if self._quitting:
            event.accept()
            return
        if self.client.is_connected():
            reply = QMessageBox.question(
                self, "Quit", "Disconnect and quit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.client.disconnect()
            self._quitting = True
            self._tray_icon.hide()
            event.accept()
            return
        # Not connected — minimize to tray
        event.ignore()
        self.hide()
        self._tray_icon.show()


# ── Entry point ───────────────────────────────────────────────────────────
def main():
    app = QApplication(sys.argv)
    app.setPalette(_dark_palette())
    app.setStyle("Fusion")

    # Global stylesheet for consistent dark theme
    app.setStyleSheet("""
        QMainWindow { background: #1e1e1e; }
        QWidget { background: #1e1e1e; color: #d4d4d4; }
        QTabWidget::pane { border: none; }
        QTabBar::tab { background: #2a2a2a; color: #d4d4d4; padding: 6px 16px; }
        QTabBar::tab:selected { background: #1e1e1e; }
        QTableWidget { background: #1a1a1a; border: none; gridline-color: #2a2a2a; }
        QTableWidget::item { padding: 4px; }
        QTableWidget::item:selected { background: #0078d4; color: white; }
        QHeaderView::section { background: #3a3a3a; color: #d4d4d4; border: none; padding: 4px 8px; font-weight: bold; }
        QTextEdit { background: #0d0d0d; color: #a0a0a0; border: none; }
        QLineEdit { background: #1a1a1a; color: #e0e0e0; border: 1px solid #3a3a3a; padding: 4px; }
        QPushButton { background: #3a3a3a; color: #d4d4d4; border: none; padding: 4px 12px; }
        QPushButton:hover { background: #4a4a4a; }
        QPushButton:pressed { background: #2a2a2a; }
        QDialog { background: #252525; }
        QLabel { color: #d4d4d4; }
        QStatusBar { background: #252525; }
    """)

    window = TrustTunnelWindow()
    window.show()
    sys.exit(app.exec())
