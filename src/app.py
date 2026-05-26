"""TrustTunnel macOS GUI — PyQt6 main window with server table, CRUD, embedded console."""

import os
import sys
import threading
import time
from typing import Optional

# ── Version safety check ──────────────────────────────────────────────────
# PyQt6 >= 6.10 has qdarwinpermissionplugin compiled into QtCore which crashes
# with console=False on macOS (CFBundleCopyBundleURL in C++ static initializer).
# Check BEFORE importing PyQt6 so we can show a clear error instead of a segfault.
if sys.platform == "darwin":
    try:
        import importlib.metadata as _meta
        _pyqt_ver = _meta.version("PyQt6")
        _pyqt_minor = int(_pyqt_ver.split(".")[1])
        if _pyqt_minor >= 10:
            # Try to show a GUI error; fall back to stderr
            try:
                import subprocess
                subprocess.run([
                    "osascript", "-e",
                    'display dialog "TrustTunnel requires PyQt6 < 6.10.\n'
                    'Current version: '
                    + _pyqt_ver
                    + '\n\nFix: pip3 install PyQt6==6.9.1 PyQt6-Qt6==6.9.1\n'
                    'Then rebuild: ./build-app.sh" '
                    'with title "TrustTunnel — PyQt6 Version Error" '
                    'buttons {"OK"} default button "OK" '
                    'with icon stop'
                ], capture_output=True, timeout=10)
            except Exception:
                print(
                    f"\n❌ FATAL: PyQt6 {_pyqt_ver} detected.\n"
                    f"   Versions >= 6.10 crash on macOS with console=False.\n"
                    f"   Fix: pip3 install 'PyQt6==6.9.1' 'PyQt6-Qt6==6.9.1'\n"
                    f"   Then rebuild: ./build-app.sh\n",
                    file=sys.stderr,
                )
            sys.exit(1)
    except Exception:
        pass  # Can't determine version — proceed and hope for the best

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
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
    from PyQt6.QtGui import QPalette, QColor
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor(60, 60, 60))
    p.setColor(QPalette.ColorRole.WindowText, QColor(220, 220, 220))
    p.setColor(QPalette.ColorRole.Base, QColor(50, 50, 50))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(70, 70, 70))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(55, 55, 55))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor(220, 220, 220))
    p.setColor(QPalette.ColorRole.Text, QColor(220, 220, 220))
    p.setColor(QPalette.ColorRole.Button, QColor(78, 78, 78))
    p.setColor(QPalette.ColorRole.ButtonText, QColor(220, 220, 220))
    p.setColor(QPalette.ColorRole.BrightText, QColor(255, 128, 128))
    p.setColor(QPalette.ColorRole.Highlight, QColor(0, 120, 212))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    return p


# ── Signal bridge for thread-safe UI updates ──────────────────────────────
class _SignalBridge:
    """Deferred — actual QObject created lazily."""
    def __init__(self):
        self._obj = None

    def _ensure(self):
        if self._obj is None:
            from PyQt6.QtCore import QObject, pyqtSignal
            class _Bridge(QObject):
                status_changed = pyqtSignal(object)  # ClientState
                log_line = pyqtSignal(str)
            self._obj = _Bridge()
        return self._obj

    @property
    def status_changed(self):
        return self._ensure().status_changed

    @property
    def log_line(self):
        return self._ensure().log_line


# ── Add/Edit Server Dialog ────────────────────────────────────────────────
class AddEditDialog:
    def __init__(self, parent, profile: Optional[ServerProfile] = None):
        from PyQt6.QtWidgets import QDialog, QFormLayout, QHBoxLayout, QLineEdit, QTextEdit, QPushButton, QMessageBox
        from PyQt6.QtCore import Qt
        self._profile = profile
        self._result: Optional[ServerProfile] = None
        self._dlg = QDialog(parent)
        self._dlg.setWindowTitle("Edit Server" if profile else "Add Server")
        self._dlg.setMinimumWidth(440)
        self._build()

    def _build(self):
        from PyQt6.QtWidgets import QFormLayout, QHBoxLayout, QLineEdit, QTextEdit, QPushButton, QMessageBox
        layout = QFormLayout(self._dlg)
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

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self._dlg.reject)
        save_btn = QPushButton("Save")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addRow(btn_row)

    def _save(self):
        from PyQt6.QtWidgets import QMessageBox
        from .config import EndpointConfig, ServerProfile
        name = self._entries["name"].text().strip()
        hostname = self._entries["hostname"].text().strip()
        address = self._entries["address"].text().strip()
        username = self._entries["username"].text().strip()
        password = self._entries["password"].text()
        bound_if = self._entries["bound_if"].text().strip()
        certificate = self._entries["certificate"].toPlainText().strip()

        if not name or not hostname or not address or not username:
            QMessageBox.warning(self._dlg, "Missing Fields",
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
        self._dlg.accept()

    def exec(self):
        return self._dlg.exec()

    @property
    def result(self):
        return self._result

    @result.setter
    def result(self, value):
        self._result = value


# ── Import Deep-Link Dialog ───────────────────────────────────────────────
class ImportDialog:
    def __init__(self, parent):
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton
        self.result: Optional[ServerProfile] = None
        self._dlg = QDialog(parent)
        self._dlg.setWindowTitle("Import tt://")
        self._dlg.setMinimumWidth(440)
        self._build()

    def _build(self):
        from PyQt6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton
        layout = QVBoxLayout(self._dlg)
        layout.setContentsMargins(16, 12, 16, 12)

        layout.addWidget(QLabel("Paste tt:// deep-link:"))
        self._text = QTextEdit()
        self._text.setMaximumHeight(60)
        layout.addWidget(self._text)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self._dlg.reject)
        import_btn = QPushButton("Import")
        import_btn.setDefault(True)
        import_btn.clicked.connect(self._do_import)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(import_btn)
        layout.addLayout(btn_row)

    def _do_import(self):
        from .config import parse_deeplink
        uri = self._text.toPlainText().strip()
        if not uri:
            self._dlg.reject()
            return
        profile = parse_deeplink(uri)
        if profile:
            self.result = profile
            self._dlg.accept()
        else:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self._dlg, "Invalid Link",
                                "Could not parse the tt:// link.\n\n"
                                "Make sure it's a valid TrustTunnel deep-link.")

    def exec(self):
        return self._dlg.exec()


# ── Main Window ────────────────────────────────────────────────────────────
class TrustTunnelWindow:
    def __init__(self, app):
        from PyQt6.QtWidgets import QMainWindow
        self._app = app
        self._init_ui()

    def _init_ui(self):
        from PyQt6.QtWidgets import (
            QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
            QTableWidget, QTableWidgetItem, QHeaderView, QPushButton,
            QLabel, QLineEdit, QTextEdit, QTabWidget, QSplitter,
            QAbstractItemView, QFrame, QSizePolicy, QSpacerItem,
            QMenuBar, QMenu, QStatusBar, QToolBar, QComboBox,
            QCheckBox, QSpinBox, QSystemTrayIcon, QMessageBox,
        )
        from PyQt6.QtCore import Qt, QTimer
        from PyQt6.QtGui import QFont, QColor, QIcon, QAction, QPixmap, QPainter, QPen

        self._bridge = _SignalBridge()
        self.client = ClientManager()
        self.servers: list[ServerProfile] = load_servers()
        self._selected_index: Optional[int] = None
        self._last_state = None
        self._log_idx = 0
        self._conn_buttons: list[QPushButton] = []
        self._quitting = False

        # Signal bridge
        self._bridge.status_changed.connect(self._on_status_changed)
        self._bridge.log_line.connect(self._on_log_line)

        # Build UI
        self._build()

        # Tray icon
        self._tray_icon = QSystemTrayIcon(self._main_window)
        self._tray_icon.setToolTip("TrustTunnel VPN — Disconnected")
        self._tray_menu = QMenu()
        self._tray_icon.setContextMenu(self._tray_menu)
        self._tray_icon.activated.connect(self._tray_activated)
        self._update_tray_icon(ClientState.DISCONNECTED)
        self._tray_icon.show()

        self._tray_server_actions = []
        self._rebuild_tray_menu()

        # Refresh server list (also rebuilds tray menu entries)
        self._refresh_server_list()

        # Poll timer
        self._poll_timer = QTimer(self._main_window)
        self._poll_timer.timeout.connect(self._poll_status)
        self._poll_timer.start(300)

    def _build(self):
        from PyQt6.QtWidgets import (
            QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
            QTableWidget, QTableWidgetItem, QHeaderView, QPushButton,
            QLabel, QLineEdit, QTextEdit, QTabWidget, QSplitter,
            QAbstractItemView, QFrame, QSizePolicy, QSpacerItem,
            QMenuBar, QMenu, QStatusBar, QToolBar, QComboBox,
            QCheckBox, QSpinBox, QMessageBox,
        )
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QFont, QColor

        self._main_window = QMainWindow()
        self._main_window.setWindowTitle("TrustTunnel VPN")
        self._main_window.setMinimumSize(520, 440)
        self._main_window.resize(860, 640)
        self._main_window.closeEvent = self._on_close_event

        central = QWidget()
        self._main_window.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Title bar
        title_bar = QHBoxLayout()
        title_bar.setContentsMargins(8, 4, 8, 4)
        title_label = QLabel("TrustTunnel VPN")
        title_label.setFont(QFont("Helvetica", 36, QFont.Weight.Bold))
        title_bar.addWidget(title_label)
        self._status_dot = QLabel("●")
        self._status_dot.setStyleSheet("color: #666; font-size: 13px;")
        title_bar.addWidget(self._status_dot)
        self._status_text = QLabel("Disconnected")
        self._status_text.setStyleSheet("color: #888; font-size: 10px;")
        title_bar.addWidget(self._status_text)
        title_bar.addStretch()
        main_layout.addLayout(title_bar)

        # Splitter: server list / console
        splitter = QSplitter(Qt.Orientation.Vertical)
        main_layout.addWidget(splitter, 1)

        # Notebook (tabs)
        self._notebook = QTabWidget()
        splitter.addWidget(self._notebook)

        # Servers tab
        servers_tab = QWidget()
        servers_layout = QVBoxLayout(servers_tab)
        servers_layout.setContentsMargins(0, 0, 0, 0)
        servers_layout.setSpacing(0)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(8, 4, 8, 4)
        add_btn = QPushButton("Add Server")
        add_btn.clicked.connect(self._add_server)
        toolbar.addWidget(add_btn)
        toolbar.addSpacing(8)
        import_btn = QPushButton("Import")
        import_btn.clicked.connect(self._import_deeplink)
        toolbar.addWidget(import_btn)
        toolbar.addStretch()
        servers_layout.addLayout(toolbar)

        # Server table
        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(["Server", " ", "Host", "Address", "User", " "])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        self._table.setAlternatingRowColors(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(1, 90)
        self._table.setColumnWidth(5, 70)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        servers_layout.addWidget(self._table)
        self._notebook.addTab(servers_tab, "Servers")

        # Bypass tab
        bypass_tab = QWidget()
        bypass_layout = QVBoxLayout(bypass_tab)
        bypass_layout.setContentsMargins(8, 8, 8, 8)
        self._bypass_list = QTableWidget(0, 1)
        self._bypass_list.setHorizontalHeaderLabels(["Mask"])
        self._bypass_list.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._bypass_list.verticalHeader().setVisible(False)
        bypass_layout.addWidget(self._bypass_list)
        bypass_btn_row = QHBoxLayout()
        self._bypass_entry = QLineEdit()
        self._bypass_entry.setPlaceholderText("Add exclusion mask...")
        self._bypass_entry.returnPressed.connect(self._add_exclusion)
        bypass_btn_row.addWidget(self._bypass_entry)
        add_exc_btn = QPushButton("+")
        add_exc_btn.clicked.connect(self._add_exclusion)
        bypass_btn_row.addWidget(add_exc_btn)
        del_exc_btn = QPushButton("−")
        del_exc_btn.clicked.connect(self._delete_exclusion)
        bypass_btn_row.addWidget(del_exc_btn)
        bypass_layout.addLayout(bypass_btn_row)
        self._bypass_status = QLabel("Select a server to manage bypass rules.")
        self._bypass_status.setStyleSheet("color: #888;")
        bypass_layout.addWidget(self._bypass_status)
        self._notebook.addTab(bypass_tab, "Bypass")

        # Console
        console_widget = QWidget()
        console_layout = QVBoxLayout(console_widget)
        console_layout.setContentsMargins(4, 4, 4, 4)
        console_toolbar = QHBoxLayout()
        copy_btn = QPushButton("Copy")
        copy_btn.clicked.connect(self._copy_console)
        console_toolbar.addWidget(copy_btn)
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear_console)
        console_toolbar.addWidget(clear_btn)
        console_toolbar.addStretch()
        console_layout.addLayout(console_toolbar)
        self._console = QTextEdit()
        self._console.setReadOnly(True)
        self._console.setFont(QFont("Menlo", 10))
        console_layout.addWidget(self._console)
        splitter.addWidget(console_widget)
        splitter.setSizes([320, 320])

    # ── Server list ──────────────────────────────────────────────────────

    def _refresh_server_list(self):
        from PyQt6.QtGui import QFont, QColor
        from PyQt6.QtWidgets import QTableWidgetItem

        self._table.setRowCount(0)
        connected_name = (
            self.client.status.server_name if self.client.is_connected() else None
        )
        state = self.client.status.state

        self._conn_buttons.clear()
        for i, s in enumerate(self.servers):
            self._table.insertRow(i)

            is_connected = (connected_name == s.name)
            is_busy = (state in (ClientState.CONNECTING, ClientState.CHECKING)
                       and connected_name == s.name)

            if is_connected:
                row_bg, text_fg = QColor(13, 40, 24), QColor(78, 201, 176)
            elif is_busy:
                row_bg, text_fg = QColor(42, 42, 26), QColor(204, 167, 0)
            else:
                row_bg, text_fg = QColor(26, 26, 26), QColor(255, 255, 255)

            name_item = QTableWidgetItem(s.name)
            name_item.setForeground(text_fg)
            name_item.setFont(QFont("Helvetica", 11, QFont.Weight.Bold))
            name_item.setBackground(row_bg)
            self._table.setItem(i, 0, name_item)

            if is_busy:
                btn_text = "…"
            elif is_connected:
                btn_text = "Disconnect"
            else:
                btn_text = "Connect"

            conn_btn = QPushButton(btn_text)
            conn_btn.setCheckable(True)
            conn_btn.setChecked(is_connected)
            conn_btn.setStyleSheet(
                "QPushButton {"
                "  border: none; border-radius: 3px; padding: 3px 8px;"
                "  font-weight: bold; font-size: 9pt;"
                "}"
                "QPushButton:!checked {"
                "  background: #666; color: #ccc;"
                "}"
                "QPushButton:checked {"
                "  background: #1a6b1a; color: #7dff7d;"
                "}"
                "QPushButton:!checked:hover {"
                "  background: #777; color: #eee;"
                "}"
            )
            conn_btn.clicked.connect(lambda checked, idx=i: self._toggle_connection(idx))
            self._table.setCellWidget(i, 1, conn_btn)
            self._conn_buttons.append(conn_btn)

            host_item = QTableWidgetItem(s.endpoint.hostname)
            host_item.setForeground(text_fg)
            host_item.setBackground(row_bg)
            self._table.setItem(i, 2, host_item)

            addr = ",".join(s.endpoint.addresses) if s.endpoint.addresses else ""
            addr_item = QTableWidgetItem(addr)
            addr_item.setForeground(text_fg)
            addr_item.setBackground(row_bg)
            self._table.setItem(i, 3, addr_item)

            user_item = QTableWidgetItem(s.endpoint.username)
            user_item.setForeground(text_fg)
            user_item.setBackground(row_bg)
            self._table.setItem(i, 4, user_item)

            from PyQt6.QtWidgets import QWidget, QHBoxLayout
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(2, 0, 2, 0)
            actions_layout.setSpacing(2)

            from PyQt6.QtGui import QPainter, QPen, QColor, QIcon, QPixmap

            def _make_icon(draw_fn, size=20):
                pm = QPixmap(size, size)
                pm.fill(QColor(0, 0, 0, 0))
                painter = QPainter(pm)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                draw_fn(painter, size)
                painter.end()
                return QIcon(pm)

            def _draw_pencil(painter, size):
                m = max(3, size // 5)
                pen = QPen(QColor("#aaa"), max(1, size // 10))
                painter.setPen(pen)
                # pencil body (diagonal)
                painter.drawLine(m, size - m, size - m, m)
                # tip
                painter.drawLine(size - m, m, size - m + 2, m - 2)
                # eraser end
                painter.drawLine(m, size - m, m - 2, size - m + 2)

            def _draw_trash(painter, size):
                m = max(3, size // 5)
                pen = QPen(QColor("#c44"), max(1, size // 10))
                painter.setPen(pen)
                # bin body
                painter.drawRect(m, m + 2, size - 2*m, size - 2*m - 2)
                # lid
                painter.drawLine(m - 1, m + 2, size - m + 1, m + 2)
                # handle
                painter.drawLine(size//2 - 2, m - 1, size//2 + 2, m - 1)
                painter.drawLine(size//2, m - 1, size//2, m + 2)
                # lines inside
                x1 = m + (size - 2*m) // 3
                x2 = m + 2*(size - 2*m) // 3
                painter.drawLine(x1, m + 5, x1, size - m - 3)
                painter.drawLine(x2, m + 5, x2, size - m - 3)

            pencil_icon = _make_icon(_draw_pencil)
            trash_icon = _make_icon(_draw_trash)

            edit_btn = QPushButton(pencil_icon, "")
            edit_btn.setFixedSize(30, 28)
            edit_btn.setStyleSheet(
                "background: transparent; border: none; padding: 2px;"
            )
            edit_btn.clicked.connect(lambda checked, idx=i: self._edit_server_by_index(idx))
            actions_layout.addWidget(edit_btn)

            del_btn = QPushButton(trash_icon, "")
            del_btn.setFixedSize(30, 28)
            del_btn.setStyleSheet(
                "background: transparent; border: none; padding: 2px;"
            )
            del_btn.clicked.connect(lambda checked, idx=i: self._delete_server_by_index(idx))
            actions_layout.addWidget(del_btn)

            self._table.setCellWidget(i, 5, actions_widget)

        if self._selected_index is not None and self._selected_index < len(self.servers):
            self._table.selectRow(self._selected_index)

        self._rebuild_tray_menu()

    def _on_selection_changed(self):
        from PyQt6.QtWidgets import QTableWidget
        selected = self._table.selectedItems()
        if selected:
            self._selected_index = selected[0].row()
        else:
            self._selected_index = None
        self._refresh_bypass_list()

    # ── CRUD ──────────────────────────────────────────────────────────

    def _add_server(self):
        from PyQt6.QtWidgets import QDialog
        dlg = AddEditDialog(self._main_window, None)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result:
            self.servers.append(dlg.result)
            self._save_and_refresh()
            self._selected_index = len(self.servers) - 1
            self._refresh_server_list()

    def _edit_server_by_index(self, idx):
        from PyQt6.QtWidgets import QDialog
        if idx >= len(self.servers):
            return
        dlg = AddEditDialog(self._main_window, self.servers[idx])
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result:
            self.servers[idx] = dlg.result
            self._save_and_refresh()
            self._refresh_server_list()

    def _delete_server_by_index(self, idx):
        from PyQt6.QtWidgets import QMessageBox
        if idx >= len(self.servers):
            return
        name = self.servers[idx].name
        reply = QMessageBox.question(
            self._main_window, "Delete", f"Delete server '{name}'?",
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
            self._refresh_server_list()

    def _save_and_refresh(self):
        from .config import save_servers
        save_servers(self.servers)

    def _import_deeplink(self):
        from PyQt6.QtWidgets import QDialog
        dlg = ImportDialog(self._main_window)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result:
            self.servers.append(dlg.result)
            self._save_and_refresh()
            self._log(f"Imported: {dlg.result.name}")
            self._refresh_server_list()

    # ── Bypass ─────────────────────────────────────────────────────────

    def _refresh_bypass_list(self):
        from PyQt6.QtWidgets import QTableWidgetItem
        self._bypass_list.setRowCount(0)
        if self._selected_index is None:
            self._bypass_status.setText("Select a server to manage bypass rules.")
            return
        profile = self.servers[self._selected_index]
        self._bypass_status.setText(f"Bypass rules for: {profile.name}")
        for i, exc in enumerate(profile.exclusions):
            self._bypass_list.insertRow(i)
            self._bypass_list.setItem(i, 0, QTableWidgetItem(f"  {exc}"))

    def _add_exclusion(self):
        from .config import save_servers
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
        from .config import save_servers
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

    # ── Console ────────────────────────────────────────────────────────

    def _log(self, text: str):
        self._console.append(text)

    def _copy_console(self):
        self._console.selectAll()
        self._console.copy()

    def _clear_console(self):
        self._console.clear()

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

    # ── Tray icon ─────────────────────────────────────────────────────

    def _update_tray_icon(self, state: ClientState):
        from PyQt6.QtGui import QPixmap, QPainter, QPen, QColor
        from PyQt6.QtCore import Qt

        pm = QPixmap(16, 16)
        pm.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx, cy = 8, 8

        # Status color for the accretion ring
        if state == ClientState.CONNECTED:
            ring_color = QColor(78, 201, 176)    # green
        elif state in (ClientState.CONNECTING, ClientState.CHECKING):
            ring_color = QColor(204, 167, 0)      # yellow
        elif state == ClientState.ERROR:
            ring_color = QColor(244, 71, 71)      # red
        else:
            ring_color = QColor(100, 100, 100)    # grey

        # Outer glow ring (thin)
        glow = QColor(ring_color)
        glow.setAlpha(80)
        painter.setPen(QPen(glow, 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(cx - 6, cy - 6, 12, 12)

        # Accretion ring (elliptical, tilted)
        painter.setPen(QPen(ring_color, 1))
        painter.drawEllipse(cx - 4, cy - 3, 8, 6)

        # Event horizon (black center)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0))
        painter.drawEllipse(cx - 2, cy - 2, 4, 4)

        painter.end()

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
        from PyQt6.QtGui import QAction
        self._tray_menu.clear()
        self._tray_server_actions.clear()

        connected_name = (
            self.client.status.server_name if self.client.is_connected() else None
        )

        for i, profile in enumerate(self.servers):
            action = QAction(profile.name, self._main_window)
            if profile.name == connected_name:
                action.setCheckable(True)
                action.setChecked(True)
            action.triggered.connect(lambda checked, idx=i: self._tray_toggle(idx))
            self._tray_menu.addAction(action)
            self._tray_server_actions.append((action, i))

        if self.servers:
            self._tray_menu.addSeparator()

        add_action = QAction("+ Add Server", self._main_window)
        add_action.triggered.connect(self._add_server_from_tray)
        self._tray_menu.addAction(add_action)

        import_action = QAction("Import tt://", self._main_window)
        import_action.triggered.connect(self._import_from_tray)
        self._tray_menu.addAction(import_action)

        self._tray_menu.addSeparator()

        show_action = QAction("Show Window", self._main_window)
        show_action.triggered.connect(self._show_from_tray)
        self._tray_menu.addAction(show_action)

        quit_action = QAction("Quit", self._main_window)
        quit_action.triggered.connect(self._quit)
        self._tray_menu.addAction(quit_action)

    def _tray_toggle(self, idx: int):
        self._toggle_connection(idx)
        self._show_from_tray()

    def _add_server_from_tray(self):
        self._add_server()
        self._show_from_tray()

    def _import_from_tray(self):
        self._import_deeplink()
        self._show_from_tray()

    def _show_from_tray(self):
        from PyQt6.QtCore import Qt
        mw = self._main_window
        mw.show()
        mw.setWindowState(mw.windowState() & ~Qt.WindowState.WindowMinimized)
        mw.raise_()
        mw.activateWindow()

    def _tray_activated(self, reason):
        from PyQt6.QtWidgets import QSystemTrayIcon
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_from_tray()

    def _quit(self):
        self._quitting = True
        self.client.disconnect()
        self._tray_icon.hide()
        from PyQt6.QtWidgets import QApplication
        QApplication.quit()

    # ── Close ─────────────────────────────────────────────────────────

    def _on_close_event(self, event):
        from PyQt6.QtWidgets import QMessageBox
        if self._quitting:
            event.accept()
            return
        if self.client.is_connected():
            reply = QMessageBox.question(
                self._main_window, "Quit", "Disconnect and quit?",
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
        event.ignore()
        self._main_window.hide()
        self._tray_icon.show()

    # ── Show ──────────────────────────────────────────────────────────

    def show(self):
        self._main_window.show()

    def exec(self):
        pass  # Compatibility


# ── Entry point ───────────────────────────────────────────────────────────
def _excepthook(exc_type, exc_val, exc_tb):
    import traceback
    log_path = os.path.expanduser("~/Library/Logs/TrustTunnel-crash.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a") as f:
        f.write("=" * 60 + "\n")
        f.write(time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
        traceback.print_exception(exc_type, exc_val, exc_tb, file=f)
        f.write("\n")
    traceback.print_exception(exc_type, exc_val, exc_tb)

sys.excepthook = _excepthook


def main():
    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setPalette(_dark_palette())
    app.setStyle("Fusion")

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

    window = TrustTunnelWindow(app)
    window.show()
    sys.exit(app.exec())
