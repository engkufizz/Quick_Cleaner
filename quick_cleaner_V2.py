import os
import sys
import gc
import stat
import fnmatch
import ctypes
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QPoint
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap, QAction
from PySide6.QtWidgets import (
    QApplication, QWidget, QFrame, QLabel, QVBoxLayout, QHBoxLayout, QToolButton,
    QGraphicsDropShadowEffect, QSystemTrayIcon, QMenu, QProgressBar, QCheckBox
)

# ---------------------- Utilities ----------------------
def human_size(n: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    f = float(max(0, n))
    while f >= 1024.0 and i < len(units) - 1:
        f /= 1024.0
        i += 1
    return f"{int(f)} {units[i]}" if i == 0 else f"{f:.1f} {units[i]}"

def ensure_path(p):
    try:
        return Path(os.path.expandvars(p)).expanduser()
    except Exception:
        return Path(p)

def safe_remove_file(p: Path) -> int:
    try:
        if not p.exists() or p.is_symlink():
            return 0
        size = 0
        try:
            size = p.stat().st_size
        except Exception:
            pass
        try:
            os.chmod(p, stat.S_IWRITE | stat.S_IREAD)
        except Exception:
            pass
        p.unlink(missing_ok=True)
        return int(size)
    except Exception:
        return 0

def wipe_tree(path: Path) -> int:
    # Delete dir tree, ignore errors and symlinks. Return bytes freed.
    freed = 0
    try:
        if not path.exists() or path.is_symlink():
            return 0
        for root, dirs, files in os.walk(path, topdown=False):
            root_p = Path(root)
            for name in files:
                freed += safe_remove_file(root_p / name)
            for name in dirs:
                dp = root_p / name
                try:
                    dp.rmdir()
                except Exception:
                    pass
        try:
            path.rmdir()
        except Exception:
            pass
    except Exception:
        pass
    return freed

def wipe_dir_contents(path: Path) -> int:
    # Delete contents of a directory (not the directory itself).
    freed = 0
    if not path.exists() or not path.is_dir():
        return 0
    try:
        with os.scandir(path) as it:
            for entry in it:
                p = Path(entry.path)
                if p.is_dir() and not p.is_symlink():
                    freed += wipe_tree(p)
                elif p.is_file():
                    freed += safe_remove_file(p)
    except Exception:
        pass
    return freed

def delete_globs(folder: Path, patterns) -> int:
    freed = 0
    if not folder.exists() or not folder.is_dir():
        return 0
    try:
        with os.scandir(folder) as it:
            for entry in it:
                if entry.is_file():
                    name = entry.name
                    if any(fnmatch.fnmatch(name, pat) for pat in patterns):
                        freed += safe_remove_file(Path(entry.path))
    except Exception:
        pass
    return freed

# ---------------- Recycle Bin via Shell API ----------------
shell32 = ctypes.windll.shell32

class SHQUERYRBINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("i64Size", ctypes.c_longlong),
        ("i64NumItems", ctypes.c_longlong),
    ]

SHQueryRecycleBinW = shell32.SHQueryRecycleBinW
SHQueryRecycleBinW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(SHQUERYRBINFO)]
SHQueryRecycleBinW.restype = ctypes.HRESULT

SHEmptyRecycleBinW = shell32.SHEmptyRecycleBinW
SHEmptyRecycleBinW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.DWORD]
SHEmptyRecycleBinW.restype = ctypes.HRESULT

SHERB_NOCONFIRMATION = 0x00000001
SHERB_NOPROGRESSUI = 0x00000002
SHERB_NOSOUND = 0x00000004

def empty_recycle_bin() -> int:
    info = SHQUERYRBINFO()
    info.cbSize = ctypes.sizeof(SHQUERYRBINFO)
    before = 0
    try:
        res = SHQueryRecycleBinW(None, ctypes.byref(info))
        if res == 0:
            before = int(info.i64Size)
    except Exception:
        pass
    try:
        SHEmptyRecycleBinW(None, None, SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND)
    except Exception:
        pass
    return max(0, before)

# ---------------------- Cleaner Tasks ----------------------
def get_env(name, default=""):
    return os.environ.get(name, default)

LOCALAPPDATA = ensure_path(get_env("LOCALAPPDATA", ""))
APPDATA = ensure_path(get_env("APPDATA", ""))
WINDIR = ensure_path(get_env("WINDIR", r"C:\Windows"))

def clean_user_temp():
    return wipe_dir_contents(ensure_path(get_env("TEMP", "")))

def clean_recent_items():
    return wipe_dir_contents(APPDATA / "Microsoft" / "Windows" / "Recent")

def clean_thumbnails():
    folder = LOCALAPPDATA / "Microsoft" / "Windows" / "Explorer"
    return delete_globs(folder, ["thumbcache*.db", "iconcache*.db"])

# Chromium-family caches
def clean_chromium_user_data(root: Path) -> int:
    freed = 0
    if not root.exists():
        return 0
    candidates = [root]
    try:
        with os.scandir(root) as it:
            for e in it:
                if e.is_dir():
                    candidates.append(Path(e.path))
    except Exception:
        pass
    rels = [
        "Cache",
        "Code Cache",
        "GPUCache",
        "ShaderCache",
        "DawnCache",
        "Media Cache",
        os.path.join("Service Worker", "CacheStorage"),
    ]
    for base in candidates:
        for rel in rels:
            freed += wipe_dir_contents(base / rel)
    return freed

def clean_chrome():
    return clean_chromium_user_data(LOCALAPPDATA / "Google" / "Chrome" / "User Data")

def clean_edge():
    return clean_chromium_user_data(LOCALAPPDATA / "Microsoft" / "Edge" / "User Data")

def clean_brave():
    return clean_chromium_user_data(LOCALAPPDATA / "BraveSoftware" / "Brave-Browser" / "User Data")

def clean_vivaldi():
    return clean_chromium_user_data(LOCALAPPDATA / "Vivaldi" / "User Data")

def clean_opera():
    root = LOCALAPPDATA / "Opera Software" / "Opera Stable"
    freed = 0
    if root.exists():
        rels = [
            "Cache", "Code Cache", "GPUCache", "ShaderCache",
            "DawnCache", "Media Cache", os.path.join("Service Worker", "CacheStorage")
        ]
        for rel in rels:
            freed += wipe_dir_contents(root / rel)
    return freed

# Firefox caches
def clean_firefox():
    freed = 0
    for base in [
        LOCALAPPDATA / "Mozilla" / "Firefox" / "Profiles",
        APPDATA / "Mozilla" / "Firefox" / "Profiles",
    ]:
        if not base.exists():
            continue
        try:
            with os.scandir(base) as it:
                for e in it:
                    if e.is_dir():
                        p = Path(e.path)
                        freed += wipe_dir_contents(p / "cache2")
                        freed += wipe_dir_contents(p / "startupCache")
        except Exception:
            pass
    return freed

# For enabling/disabling checkboxes if browser data seems absent
def path_has_content(path: Path) -> bool:
    try:
        if not path.exists():
            return False
        with os.scandir(path) as it:
            for _ in it:
                return True
    except Exception:
        pass
    return False

def browser_presence():
    return {
        "Google Chrome": path_has_content(LOCALAPPDATA / "Google" / "Chrome" / "User Data"),
        "Microsoft Edge": path_has_content(LOCALAPPDATA / "Microsoft" / "Edge" / "User Data"),
        "Brave":          path_has_content(LOCALAPPDATA / "BraveSoftware" / "Brave-Browser" / "User Data"),
        "Vivaldi":        path_has_content(LOCALAPPDATA / "Vivaldi" / "User Data"),
        "Opera":          path_has_content(LOCALAPPDATA / "Opera Software" / "Opera Stable"),
        "Firefox":        path_has_content(APPDATA / "Mozilla" / "Firefox" / "Profiles") or
                          path_has_content(LOCALAPPDATA / "Mozilla" / "Firefox" / "Profiles"),
    }

BASE_TASKS = [
    ("Recycle Bin", empty_recycle_bin),
    ("User Temp", clean_user_temp),
    ("Recent Items", clean_recent_items),
    ("Windows Thumbnails", clean_thumbnails),
]

BROWSER_TASKS = {
    "Google Chrome": ("Google Chrome Cache", clean_chrome),
    "Microsoft Edge": ("Microsoft Edge Cache", clean_edge),
    "Brave": ("Brave Cache", clean_brave),
    "Vivaldi": ("Vivaldi Cache", clean_vivaldi),
    "Opera": ("Opera Cache", clean_opera),
    "Firefox": ("Firefox Cache", clean_firefox),
}

# ---------------------- Worker Thread ----------------------
class CleanerThread(QThread):
    stage = Signal(str, int, int)   # name, step_index, total_steps
    progress = Signal(int)          # total freed so far (bytes)
    done = Signal(int)              # total freed (bytes)

    def __init__(self, tasks):
        super().__init__()
        self.tasks = tasks

    def run(self):
        total_freed = 0
        steps = len(self.tasks)
        gc.collect()
        for i, (name, func) in enumerate(self.tasks, start=1):
            self.stage.emit(name, i, steps)
            try:
                freed = int(func() or 0)
            except Exception:
                freed = 0
            total_freed += max(0, freed)
            self.progress.emit(total_freed)
        self.done.emit(total_freed)

# ---------------------- UI helpers ----------------------
def emoji_icon(emoji: str, size: int = 128, bg=QColor(32, 48, 79), fg=QColor(220, 230, 255)) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setBrush(bg)
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(0, 0, size, size)
    f = QFont()
    f.setPointSize(int(size * 0.55))
    painter.setFont(f)
    painter.setPen(fg)
    painter.drawText(pm.rect(), Qt.AlignCenter, emoji)
    painter.end()
    return QIcon(pm)

# ---------------------- Main Window ----------------------
class QuickCleaner(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.drag_pos = QPoint()

        # Panel and style
        self.panel = QFrame(self)
        self.panel.setObjectName("panel")
        self.panel.setStyleSheet("""
            QFrame#panel {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(20,31,52,230), stop:1 rgba(13,24,42,230));
                border:1px solid rgba(255,255,255,22);
                border-radius:18px;
            }
            QLabel { color:#D6E2FF; font-size:11pt; font-weight:600; }
            QToolButton {
                background-color: rgba(255,255,255,18);
                border:1px solid rgba(255,255,255,22);
                border-radius:16px;
                color:#D6E2FF;
                font-weight:700;
                padding:6px 12px;
                min-width:110px; min-height:32px;
            }
            QToolButton:hover { background-color: rgba(255,255,255,26); }
            QToolButton:pressed { background-color: rgba(255,255,255,34); }
            QProgressBar {
                background-color: rgba(255,255,255,12);
                border:1px solid rgba(255,255,255,22);
                border-radius:8px;
                color:#D6E2FF;
                text-align:center;
                height:14px;
            }
            QProgressBar::chunk {
                background-color: #4FC3A1;
                border-radius:8px;
            }
            QCheckBox { color:#D6E2FF; font-size:10pt; }
        """)
        shadow = QGraphicsDropShadowEffect(self.panel)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 160))
        self.panel.setGraphicsEffect(shadow)

        # Controls
        self.clean_btn = QToolButton(self.panel)
        self.clean_btn.setText("Clean Now")
        self.clean_btn.clicked.connect(self.start_clean)

        self.status_label = QLabel("Ready", self.panel)
        self.total_label = QLabel("Freed: 0 B", self.panel)

        self.progress = QProgressBar(self.panel)
        self.progress.setRange(0, len(BASE_TASKS))
        self.progress.setValue(0)
        self.progress.setTextVisible(False)

        self.close_btn = QToolButton(self.panel)
        self.close_btn.setText("➜")
        self.close_btn.setToolTip("Close")
        self.close_btn.clicked.connect(QApplication.instance().quit)

        # Browser checkboxes
        self.browser_checks = {}
        b_layout = QHBoxLayout()
        b_layout.setSpacing(12)
        b_title = QLabel("Browsers:")
        b_title.setStyleSheet("font-size:10pt;")
        b_layout.addWidget(b_title)

        for name in ["Google Chrome", "Microsoft Edge", "Brave", "Vivaldi", "Opera", "Firefox"]:
            cb = QCheckBox(name, self.panel)
            cb.setChecked(True)
            self.browser_checks[name] = cb
            b_layout.addWidget(cb)
        b_layout.addStretch(1)

        # Layouts
        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(self.clean_btn)
        top.addStretch(1)
        top.addWidget(self.close_btn)

        v = QVBoxLayout(self.panel)
        v.setContentsMargins(10, 8, 10, 8)
        v.setSpacing(8)
        v.addLayout(top)
        v.addLayout(b_layout)
        v.addWidget(self.status_label)
        v.addWidget(self.progress)
        v.addWidget(self.total_label)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.addWidget(self.panel)

        # Tray
        self.tray = QSystemTrayIcon(emoji_icon("🧹"), self)
        self.tray.setToolTip("Quick Cleaner")
        tray_menu = QMenu()
        act_clean = QAction("Clean Now", self)
        act_quit = QAction("Quit", self)
        act_clean.triggered.connect(self.start_clean)
        act_quit.triggered.connect(QApplication.instance().quit)
        tray_menu.addAction(act_clean)
        tray_menu.addSeparator()
        tray_menu.addAction(act_quit)
        self.tray.setContextMenu(tray_menu)
        self.tray.show()

        # Size/pos
        self.resize(620, 160)
        self.move_to_corner()

        self.cleaner = None
        self.refresh_browser_presence()

    def refresh_browser_presence(self):
        present = browser_presence()
        for name, cb in self.browser_checks.items():
            # Enable if likely present; still allow manual check even if not detected
            cb.setEnabled(True)
            if not present.get(name, False):
                cb.setToolTip("No data found; skipping may have no effect")
            else:
                cb.setToolTip("")
        # Update progress max based on default selection
        self.update_progress_max()

    def update_progress_max(self):
        selected_browsers = sum(1 for cb in self.browser_checks.values() if cb.isChecked())
        self.progress.setRange(0, len(BASE_TASKS) + selected_browsers)

    def move_to_corner(self):
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - self.width() - 20,
                  screen.bottom() - self.height() - 20)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            e.accept()

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self.drag_pos)
            e.accept()

    def set_busy(self, busy: bool):
        self.clean_btn.setEnabled(not busy)
        self.close_btn.setEnabled(not busy)
        for cb in self.browser_checks.values():
            cb.setEnabled(not busy and cb.isEnabled())

    def build_task_list(self):
        tasks = list(BASE_TASKS)
        for name, cb in self.browser_checks.items():
            if cb.isChecked():
                tasks.append(BROWSER_TASKS[name])
        return tasks

    def start_clean(self):
        if self.cleaner and self.cleaner.isRunning():
            return
        tasks = self.build_task_list()
        self.progress.setRange(0, len(tasks))
        self.progress.setValue(0)
        self.total_label.setText("Freed: 0 B")
        self.status_label.setText("Starting…")
        self.set_busy(True)

        self.cleaner = CleanerThread(tasks)
        self.cleaner.stage.connect(self.on_stage)
        self.cleaner.progress.connect(self.on_progress)
        self.cleaner.done.connect(self.on_done)
        self.cleaner.start()

    def on_stage(self, name, step, total):
        self.status_label.setText(f"Cleaning: {name}")
        self.progress.setMaximum(total)
        self.progress.setValue(step - 1)

    def on_progress(self, total_bytes):
        self.total_label.setText(f"Freed: {human_size(total_bytes)}")

    def on_done(self, total_bytes):
        self.progress.setValue(self.progress.maximum())
        self.status_label.setText("Done")
        self.total_label.setText(f"Freed: {human_size(total_bytes)}")
        self.set_busy(False)
        self.refresh_browser_presence()
        self.update_progress_max()

def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setLayoutDirection(Qt.LeftToRight)
    app.setWindowIcon(emoji_icon("🧹"))

    w = QuickCleaner()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
