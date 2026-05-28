"""TrustTunnel macOS GUI — PyQt6 main window with server table, CRUD, embedded console."""

import os
import sys
import threading
import time
from typing import Optional

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
    # Base dark level: ~30% lighter than before (was ~20% black, now ~30% black)
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor(78, 78, 78))
    p.setColor(QPalette.ColorRole.WindowText, QColor(220, 220, 220))
    p.setColor(QPalette.ColorRole.Base, QColor(65, 65, 65))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(88, 88, 88))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(72, 72, 72))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor(220, 220, 220))
    p.setColor(QPalette.ColorRole.Text, QColor(220, 220, 220))
    p.setColor(QPalette.ColorRole.Button, QColor(96, 96, 96))
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
        self._poll_timer.start(1000)

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
        title_bar.setContentsMargins(20, 20, 20, 20)

        # App icon
        app_icon = QIcon()
        icon_candidates = []
        if getattr(sys, 'frozen', False):
            # py2app: icon is in Contents/Resources/
            respath = os.environ.get('RESOURCEPATH', '')
            if not respath:
                executable_dir = os.path.dirname(sys.executable)
                respath = os.path.join(os.path.dirname(executable_dir), 'Resources')
            icon_candidates.extend([
                os.path.join(respath, 'icon.icns'),
            ])
        icon_candidates.extend([
            os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'icon.icns'),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'icon.icns'),
        ])
        for cand in icon_candidates:
            if os.path.exists(cand):
                app_icon = QIcon(cand)
                break
        if app_icon.isNull():
            # Fallback: simple colored square (no QPainter to avoid Rosetta issues)
            pm = QPixmap(24, 24)
            pm.fill(QColor(78, 201, 176))
            app_icon = QIcon(pm)

        icon_label = QLabel()
        icon_label.setPixmap(app_icon.pixmap(24, 24))
        icon_label.setFixedSize(24, 24)
        title_bar.addWidget(icon_label)

        title_label = QLabel("TrustTunnel VPN")
        title_label.setFont(QFont("Helvetica", 22, QFont.Weight.Bold))
        title_bar.addWidget(title_label)

        # Spacer before status
        title_bar.addSpacing(50)

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

    _pencil_icon = None
    _trash_icon = None

    @classmethod
    def _get_pencil_icon(cls):
        if cls._pencil_icon is None:
            from PyQt6.QtGui import QPainter, QPen, QColor, QPixmap
            pm = QPixmap(20, 20)
            pm.fill(QColor(0, 0, 0, 0))
            painter = QPainter(pm)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            pen = QPen(QColor("#aaa"), 1)
            painter.setPen(pen)
            painter.drawLine(3, 17, 17, 3)
            painter.drawLine(17, 3, 19, 1)
            painter.drawLine(3, 17, 1, 19)
            painter.end()
            cls._pencil_icon = QIcon(pm)
        return cls._pencil_icon

    @classmethod
    def _get_trash_icon(cls):
        if cls._trash_icon is None:
            from PyQt6.QtGui import QPainter, QPen, QColor, QPixmap
            pm = QPixmap(20, 20)
            pm.fill(QColor(0, 0, 0, 0))
            painter = QPainter(pm)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            pen = QPen(QColor("#c44"), 1)
            painter.setPen(pen)
            painter.drawRect(4, 6, 12, 12)
            painter.drawLine(3, 6, 17, 6)
            painter.drawLine(7, 3, 13, 3)
            painter.drawLine(7, 3, 7, 6)
            painter.drawLine(13, 3, 13, 6)
            painter.end()
            cls._trash_icon = QIcon(pm)
        return cls._trash_icon

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
                row_bg, text_fg = QColor(18, 55, 32), QColor(78, 201, 176)
            elif is_busy:
                row_bg, text_fg = QColor(55, 55, 34), QColor(204, 167, 0)
            else:
                row_bg, text_fg = QColor(34, 34, 34), QColor(255, 255, 255)

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

            pencil_icon = TrustTunnelWindow._get_pencil_icon()
            trash_icon = TrustTunnelWindow._get_trash_icon()

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
        # Status changed from background thread — just trigger a poll
        # Don't call _refresh_server_list here to avoid double rebuild
        pass

    def _on_log_line(self, line):
        self._log(line)

    # ── Tray icon ─────────────────────────────────────────────────────

    def _update_tray_icon(self, state: ClientState):
        from PyQt6.QtGui import QPixmap, QPainter, QColor
        from PyQt6.QtCore import Qt

        pm = QPixmap(16, 16)
        pm.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx, cy = 8, 8

        # Simple filled circle: grey when disconnected, white when connected
        if state == ClientState.CONNECTED:
            circle_color = QColor(255, 255, 255)  # white
        else:
            circle_color = QColor(128, 128, 128)  # grey

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(circle_color)
        painter.drawEllipse(cx - 4, cy - 4, 8, 8)

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
        * {
            background-color: #2c2c2c;
            color: #d4d4d4;
            border: none;
        }
        QMainWindow { background: #2c2c2c; }
        QWidget { background: #2c2c2c; color: #d4d4d4; }
        QFrame { background: #2c2c2c; border: none; }
        QTabWidget::pane { border: none; background: #2c2c2c; }
        QTabBar::tab { background: #383838; color: #d4d4d4; padding: 6px 16px; border: none; }
        QTabBar::tab:selected { background: #2c2c2c; border: none; }
        QTabBar::tab:!selected { background: #383838; border: none; }
        QTabBar::tab:hover { background: #444; }
        QTableWidget { background: #262626; border: none; gridline-color: #333; }
        QTableWidget::item { padding: 4px; border: none; }
        QTableWidget::item:selected { background: #0078d4; color: white; border: none; }
        QTableWidget::item:hover { background: #333; }
        QHeaderView::section { background: #3a3a3a; color: #d4d4d4; border: none; padding: 4px 8px; font-weight: bold; }
        QHeaderView::section:hover { background: #444; }
        QTextEdit { background: #1f1f1f; color: #a0a0a0; border: none; }
        QLineEdit { background: #262626; color: #e0e0e0; border: 1px solid #444; padding: 4px; }
        QPushButton { background: #444; color: #d4d4d4; border: none; padding: 4px 12px; }
        QPushButton:hover { background: #555; }
        QPushButton:pressed { background: #383838; }
        QPushButton:disabled { background: #333; color: #666; }
        QDialog { background: #303030; }
        QLabel { color: #d4d4d4; background: transparent; }
        QStatusBar { background: #2c2c2c; }
        QMenuBar { background: #2c2c2c; color: #d4d4d4; }
        QMenuBar::item:selected { background: #444; }
        QMenu { background: #2c2c2c; color: #d4d4d4; }
        QMenu::item:selected { background: #0078d4; }
        QComboBox { background: #262626; color: #e0e0e0; border: 1px solid #444; }
        QComboBox::drop-down { border: none; }
        QComboBox QAbstractItemView { background: #2c2c2c; color: #d4d4d4; }
        QCheckBox { color: #d4d4d4; }
        QScrollBar:vertical { background: #2c2c2c; }
        QScrollBar:horizontal { background: #2c2c2c; }
        QSplitter::handle { background: #383838; }
        QToolBar { background: #2c2c2c; border: none; }
        QToolButton { background: transparent; border: none; }
        QToolButton:hover { background: #444; }
    """)

    window = TrustTunnelWindow(app)
    window.show()
    sys.exit(app.exec())
