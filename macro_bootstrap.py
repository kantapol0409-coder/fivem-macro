import ctypes
import os
import shutil
import subprocess
import sys
import time


def fail(message):
    ctypes.windll.user32.MessageBoxW(None, message, "FiveM Farming", 0x10)


def main():
    # Explorer and remote-control tools do not always start an EXE with its
    # containing folder as cwd. Resolve everything from the EXE itself.
    if getattr(sys, "frozen", False):
        app_dir = os.path.dirname(os.path.abspath(sys.executable))
    else:
        app_dir = os.path.dirname(os.path.abspath(__file__))

    python_exe = os.path.join(app_dir, "templates", "_runtime", "python.exe")
    packaged_macro = os.path.join(app_dir, "templates", "_app", "gui_macro.py")
    macro = os.path.join(app_dir, "gui_macro.py")
    log_path = os.path.join(app_dir, "macro-startup.log")

    if not os.path.isfile(python_exe):
        fail(f"ไม่พบ Python Runtime\n\nตำแหน่งที่ตรวจหา:\n{python_exe}")
        return 1
    if not os.path.isfile(packaged_macro):
        fail(f"ไม่พบไฟล์มาโคร\n\nตำแหน่งที่ตรวจหา:\n{packaged_macro}")
        return 1

    try:
        shutil.copy2(packaged_macro, macro)
        child_env = os.environ.copy()
        child_env["FIVEM_CAPTURE_BITBLT"] = "1"
        with open(log_path, "w", encoding="utf-8") as log:
            process = subprocess.Popen(
                [python_exe, macro],
                cwd=app_dir,
                env=child_env,
                stdout=log,
                stderr=log,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        time.sleep(1.5)
        if process.poll() is not None:
            fail(f"มาโครเริ่มทำงานไม่สำเร็จ\n\nดูรายละเอียดที่:\n{log_path}")
            return int(process.returncode or 1)
    except Exception as error:
        try:
            with open(log_path, "a", encoding="utf-8") as log:
                log.write(f"Bootstrap error: {type(error).__name__}: {error}\n")
        except Exception:
            pass
        fail(f"เปิดมาโครไม่สำเร็จ\n\n{type(error).__name__}: {error}\n\nLog:\n{log_path}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
