import ctypes
import os
import shutil
import subprocess
import sys


def fail(message):
    ctypes.windll.user32.MessageBoxW(
        None,
        message,
        "FiveM Farming",
        0x10,
    )


def main():
    app_dir = os.getcwd()
    pythonw = os.path.join(app_dir, "templates", "_runtime", "pythonw.exe")
    packaged_macro = os.path.join(app_dir, "templates", "_app", "gui_macro.py")
    macro = os.path.join(app_dir, "gui_macro.py")

    if not os.path.isfile(pythonw):
        fail("ไม่พบ Python Runtime กรุณาเปิด Launcher เพื่ออัปเดตใหม่")
        return 1
    if not os.path.isfile(packaged_macro):
        fail("ไม่พบไฟล์มาโคร กรุณาเปิด Launcher เพื่ออัปเดตใหม่")
        return 1

    # Keep the unchanged macro beside config.json and templates, exactly like
    # the working setup on the main PC.
    shutil.copy2(packaged_macro, macro)
    child_env = os.environ.copy()
    child_env["FIVEM_CAPTURE_BITBLT"] = "1"
    subprocess.Popen(
        [pythonw, macro],
        cwd=app_dir,
        env=child_env,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
