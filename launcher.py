import hashlib
import json
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
import certifi
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QMessageBox, QProgressBar, QVBoxLayout, QWidget


REPOSITORY = "kantapol0409-coder/fivem-macro"
RELEASE_API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
MANIFEST_ASSET = "release-manifest.json"
PACKAGE_ASSET = "FiveM-Farming-Package.zip"
APP_EXE = "FiveM-Farming-Macro.exe"
APP_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "FiveM-Farming")
VERSION_FILE = os.path.join(APP_DIR, ".installed-version.json")
USER_AGENT = "FiveM-Farming-Launcher/1.0"
HTTPS_CONTEXT = ssl.create_default_context(cafile=certifi.where())


def request_bytes(url, timeout=30):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout, context=HTTPS_CONTEXT) as response:
        return response.read()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().lower()


def safe_extract(archive, destination):
    destination_abs = os.path.abspath(destination)
    with zipfile.ZipFile(archive) as zipped:
        for member in zipped.infolist():
            target = os.path.abspath(os.path.join(destination_abs, member.filename))
            if os.path.commonpath([destination_abs, target]) != destination_abs:
                raise ValueError("Unsafe path in update package")
        zipped.extractall(destination_abs)


class UpdateWorker(QThread):
    status = Signal(str, str, int)
    failed = Signal(str)
    ready = Signal(str)

    def get_installed_version(self):
        try:
            with open(VERSION_FILE, "r", encoding="utf-8") as stream:
                return str(json.load(stream).get("version", ""))
        except Exception:
            return ""

    def update_and_run(self):
        try:
            release = json.loads(request_bytes(RELEASE_API, timeout=15).decode("utf-8"))
            assets = {asset["name"]: asset["browser_download_url"] for asset in release.get("assets", [])}
            if MANIFEST_ASSET not in assets or PACKAGE_ASSET not in assets:
                raise RuntimeError("รีลีสล่าสุดมีไฟล์อัปเดตไม่ครบ")

            manifest = json.loads(request_bytes(assets[MANIFEST_ASSET], timeout=15).decode("utf-8"))
            remote_version = str(manifest["version"])
            expected_hash = str(manifest["package_sha256"]).lower()
            installed_version = self.get_installed_version()
            app_path = os.path.join(APP_DIR, APP_EXE)

            if installed_version != remote_version or not os.path.isfile(app_path):
                self.status.emit(
                    f"กำลังบังคับอัปเดตเป็นเวอร์ชัน {remote_version}",
                    "กำลังดาวน์โหลดแพ็กเกจล่าสุด…",
                    10,
                )
                os.makedirs(APP_DIR, exist_ok=True)
                with tempfile.TemporaryDirectory(prefix="fivem-update-") as temporary:
                    archive_path = os.path.join(temporary, PACKAGE_ASSET)
                    package = request_bytes(assets[PACKAGE_ASSET], timeout=120)
                    with open(archive_path, "wb") as stream:
                        stream.write(package)
                    self.status.emit(
                        f"กำลังบังคับอัปเดตเป็นเวอร์ชัน {remote_version}",
                        "กำลังตรวจสอบความถูกต้องของไฟล์…",
                        65,
                    )
                    actual_hash = sha256_file(archive_path)
                    if actual_hash != expected_hash:
                        raise RuntimeError("SHA-256 ของไฟล์อัปเดตไม่ตรง")

                    staging = os.path.join(temporary, "staging")
                    safe_extract(archive_path, staging)
                    staged_app = os.path.join(staging, APP_EXE)
                    if not os.path.isfile(staged_app):
                        raise RuntimeError("ไม่พบโปรแกรมหลักในแพ็กเกจ")

                    self.status.emit(
                        f"กำลังบังคับอัปเดตเป็นเวอร์ชัน {remote_version}",
                        "กำลังติดตั้งไฟล์เวอร์ชันใหม่…",
                        85,
                    )
                    for name in (APP_EXE, "config.json", "templates"):
                        source = os.path.join(staging, name)
                        target = os.path.join(APP_DIR, name)
                        if not os.path.exists(source):
                            continue
                        if os.path.isdir(source):
                            if os.path.isdir(target):
                                shutil.rmtree(target)
                            shutil.copytree(source, target)
                        else:
                            shutil.copy2(source, target)

                    with open(VERSION_FILE, "w", encoding="utf-8") as stream:
                        json.dump({"version": remote_version}, stream)

            self.status.emit(
                f"เวอร์ชัน {remote_version} พร้อมใช้งาน",
                "กำลังเปิดมาโคร…",
                100,
            )
            self.ready.emit(os.path.join(APP_DIR, APP_EXE))
        except Exception as error:
            self.failed.emit(str(error))

    def run(self):
        self.update_and_run()


class LauncherWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FiveM Farming Launcher")
        self.setFixedSize(500, 220)
        self.setStyleSheet(
            "QMainWindow, QWidget { background: #f8fafc; }"
            "QLabel { color: #0f172a; font-family: Tahoma; }"
            "QProgressBar { height: 20px; text-align: center; }"
            "QProgressBar::chunk { background: #10b981; }"
        )

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)
        self.title_label = QLabel("กำลังตรวจสอบเวอร์ชันล่าสุด…")
        self.title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.detail_label = QLabel("เชื่อมต่อ GitHub")
        self.detail_label.setStyleSheet("font-size: 12px;")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        layout.addWidget(self.title_label)
        layout.addWidget(self.progress)
        layout.addWidget(self.detail_label)
        self.setCentralWidget(central)

        self.worker = UpdateWorker()
        self.worker.status.connect(self.set_status)
        self.worker.failed.connect(self.show_failure)
        self.worker.ready.connect(self.launch_app)
        self.worker.start()

    def set_status(self, title, detail, progress):
        self.title_label.setText(title)
        self.detail_label.setText(detail)
        self.progress.setValue(progress)

    def show_failure(self, error):
        QMessageBox.critical(
            self,
            "อัปเดตไม่สำเร็จ",
            "ไม่สามารถตรวจสอบหรือติดตั้งเวอร์ชันล่าสุดได้\n"
            "ระบบบังคับอัปเดตจึงไม่เปิดมาโครเวอร์ชันเก่า\n\n"
            f"รายละเอียด: {error}",
        )
        self.close()

    def launch_app(self, app_path):
        subprocess.Popen([app_path], cwd=APP_DIR)
        self.close()


if __name__ == "__main__":
    application = QApplication(sys.argv)
    window = LauncherWindow()
    window.show()
    sys.exit(application.exec())
