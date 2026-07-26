import sys
import os
import time
import ctypes
import json
import numpy as np
import cv2
import win32gui
import win32ui
import win32con
import win32api
import keyboard

# Keep Qt screen coordinates, Win32 window coordinates, and captured pixels in
# the same (physical-pixel) coordinate space.  Without this, Windows display
# scaling can make a freshly cropped template differ from PrintWindow output.
try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

from PySide6.QtCore import Qt, QThread, Signal, Slot, QTimer, QPoint, QRect
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QSlider, QTextEdit, QFrame, QGridLayout, 
    QGroupBox, QSystemTrayIcon, QMenu, QCheckBox, QTabWidget, QScrollArea
)
from PySide6.QtGui import QIcon, QAction, QColor, QFont, QPainter, QPen, QPixmap, QImage

def get_resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

def get_writable_path(filename):
    if getattr(sys, 'frozen', False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, filename)

# ==========================================
# HARDWARE-LEVEL SCANCODE KEYBOARD SENDER (SendInput API)
# ==========================================
class KeyBdInput(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort), ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

class HardwareInput(ctypes.Structure):
    _fields_ = [("uMsg", ctypes.c_ulong), ("wParamL", ctypes.c_short), ("wParamH", ctypes.c_ushort)]

class MouseInput(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long), ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

class Input_I(ctypes.Union):
    _fields_ = [("ki", KeyBdInput), ("mi", MouseInput), ("hi", HardwareInput)]

class Input(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("ii", Input_I)]

KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_KEYUP = 0x0002

SCANCODES = {"esc": 0x01, "x": 0x2D, "6": 0x07, "7": 0x08, "e": 0x12, "t": 0x14, "h": 0x23}

def press_key(scancode):
    extra = ctypes.c_ulong(0)
    ii_ = Input_I()
    ii_.ki = KeyBdInput(0, scancode, KEYEVENTF_SCANCODE, 0, ctypes.pointer(extra))
    x = Input(ctypes.c_ulong(1), ii_)
    ctypes.windll.user32.SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))

def release_key(scancode):
    extra = ctypes.c_ulong(0)
    ii_ = Input_I()
    ii_.ki = KeyBdInput(0, scancode, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, 0, ctypes.pointer(extra))
    x = Input(ctypes.c_ulong(1), ii_)
    ctypes.windll.user32.SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))

def send_key_direct(key_name, duration=0.10):
    scancode = SCANCODES.get(key_name.lower())
    if scancode is not None:
        press_key(scancode)
        time.sleep(duration)
        release_key(scancode)

def press_key_hold(key_name):
    scancode = SCANCODES.get(key_name.lower())
    if scancode is not None:
        press_key(scancode)

def release_key_hold(key_name):
    scancode = SCANCODES.get(key_name.lower())
    if scancode is not None:
        release_key(scancode)

# ==========================================
# REGION SELECTOR OVERLAY
# ==========================================
class RegionSelector(QWidget):
    def __init__(self, callback, close_callback=None):
        super().__init__()
        self.callback = callback
        self.close_callback = close_callback
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setWindowState(Qt.WindowFullScreen)
        self.setCursor(Qt.CrossCursor)
        screen = QApplication.primaryScreen()
        self.background_pixmap = screen.grabWindow(0)
        self.start_pos = None
        self.end_pos = None
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self.background_pixmap)
        overlay_color = QColor(0, 0, 0, 60)
        if self.start_pos and self.end_pos:
            rect = QRect(self.start_pos, self.end_pos).normalized()
            painter.fillRect(0, 0, self.width(), rect.top(), overlay_color)
            painter.fillRect(0, rect.bottom(), self.width(), self.height() - rect.bottom(), overlay_color)
            painter.fillRect(0, rect.top(), rect.left(), rect.height(), overlay_color)
            painter.fillRect(rect.right(), rect.top(), self.width() - rect.right(), rect.height(), overlay_color)
            pen = QPen(QColor(239, 68, 68), 2, Qt.SolidLine)
            painter.setPen(pen)
            painter.drawRect(rect)
        else:
            painter.fillRect(self.rect(), overlay_color)
            
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start_pos = event.position().toPoint()
            self.end_pos = self.start_pos
            self.update()
            
    def mouseMoveEvent(self, event):
        if self.start_pos:
            self.end_pos = event.position().toPoint()
            self.update()
            
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.start_pos and self.end_pos:
            x1, y1 = self.start_pos.x(), self.start_pos.y()
            x2, y2 = self.end_pos.x(), self.end_pos.y()
            x, y = min(x1, x2), min(y1, y2)
            w, h = abs(x2 - x1), abs(y2 - y1)
            if w > 5 and h > 5:
                self.callback(x, y, w, h)
            self.close()
            
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()

    def closeEvent(self, event):
        if self.close_callback:
            self.close_callback()
        event.accept()

WINDOW_NAME = "FiveM"
TEMPLATES = {
    "gold": "templates/gold.png",
    "destroy": "templates/destroy.png",
    "all": "templates/all.png",
    "confirm": "templates/confirm.png"
}

# ==========================================
# WORKER THREAD FOR BACKGROUND MACRO
# ==========================================
class MacroWorker(QThread):
    log_signal = Signal(str)
    connection_signal = Signal(bool, str)
    match_signal = Signal(dict)
    running_state_signal = Signal(bool)
    hud_preview_signal = Signal(np.ndarray, np.ndarray, int, int)
    gold_preview_signal = Signal(np.ndarray, np.ndarray, float, float, float)
    diamond_preview_signal = Signal(np.ndarray, float, bool, str)

    def __init__(self):
        super().__init__()
        self.is_running = False
        self.is_exiting = False
        self.hwnd = None
        self.thresholds = {"gold": 0.84, "destroy": 0.75, "all": 0.65, "confirm": 0.65}
        self.delays = {"gold": 0.8, "destroy": 0.8, "all": 0.8, "confirm": 8.0}
        self.hud_region = None
        self.auto_farm_region = None
        self.bag_region = None
        self.gold_search_region = None
        self.destroy_search_region = None
        self.all_search_region = None
        self.confirm_search_region = None
        self.diamond_search_region = None
        self.diamond_trunk_search_region = None
        self.trunk_ready_search_region = None
        self.all_trunk_search_region = None
        self.confirm_trunk_search_region = None
        self.hunger_limit = 20
        self.thirst_limit = 20
        self.force_feed_test = False
        self.force_store_test = False
        self.last_hud_check_time = 0.0
        self.last_diamond_check_time = 0.0
        self.last_diamond_storage_time = 0.0
        self.diamond_pass_streak = 0
        self.auto_feed_enabled = True
        self.auto_store_enabled = True
        self.reference_resolution = None
        self.template_reference_sizes = {}
        self.last_runtime_error = ""
        self.last_runtime_error_time = 0.0
        self.last_gold_debug_capture_time = 0.0

    def set_config(self, key, config_type, value):
        if config_type == "threshold": self.thresholds[key] = value
        elif config_type == "delay": self.delays[key] = value
        elif config_type == "region":
            if key == "hud": self.hud_region = value
            elif key == "auto_farm": self.auto_farm_region = value
            elif key == "bag": self.bag_region = value
            elif key == "gold_search": self.gold_search_region = value
            elif key == "destroy_search": self.destroy_search_region = value
            elif key == "all_search": self.all_search_region = value
            elif key == "confirm_search": self.confirm_search_region = value
            elif key == "diamond_search": self.diamond_search_region = value
            elif key == "diamond_trunk_search": self.diamond_trunk_search_region = value
            elif key == "trunk_ready_search": self.trunk_ready_search_region = value
            elif key == "all_trunk_search": self.all_trunk_search_region = value
            elif key == "confirm_trunk_search": self.confirm_trunk_search_region = value
        elif config_type == "limit":
            if key == "hunger": self.hunger_limit = value
            elif key == "thirst": self.thirst_limit = value
        elif config_type == "toggle":
            if key == "auto_feed": self.auto_feed_enabled = value
            elif key == "auto_store": self.auto_store_enabled = value
        elif config_type == "ref_res": self.reference_resolution = value
        elif config_type == "template_refs": self.template_reference_sizes = value or {}

    def get_client_geometry(self, hwnd=None):
        """Return the game client origin on screen and its pixel size."""
        hwnd = hwnd or self.hwnd
        if not hwnd:
            return None
        try:
            left, top, right, bottom = win32gui.GetClientRect(hwnd)
            screen_x, screen_y = win32gui.ClientToScreen(hwnd, (0, 0))
            width, height = right - left, bottom - top
            if width <= 0 or height <= 0:
                return None
            return screen_x, screen_y, width, height
        except Exception:
            return None

    def client_to_screen(self, x, y):
        try:
            return win32gui.ClientToScreen(self.hwnd, (int(x), int(y)))
        except Exception:
            geometry = self.get_client_geometry()
            if geometry:
                return geometry[0] + int(x), geometry[1] + int(y)
            return int(x), int(y)

    def get_scaled_region(self, region):
        if not region or not self.reference_resolution or not self.hwnd: return region
        try:
            geometry = self.get_client_geometry()
            if not geometry:
                return region
            cur_w, cur_h = geometry[2], geometry[3]
            ref_w, ref_h = self.reference_resolution
            if ref_w <= 0 or ref_h <= 0 or cur_w <= 0 or cur_h <= 0: return region
            if cur_w == ref_w and cur_h == ref_h: return region
            sx, sy = cur_w / ref_w, cur_h / ref_h
            return [int(region[0] * sx), int(region[1] * sy), int(region[2] * sx), int(region[3] * sy)]
        except Exception: return region

    def get_region_ranges(self, region, w_img, h_img, default_x=(0.0, 1.0), default_y=(0.0, 1.0)):
        if region:
            scaled = self.get_scaled_region(region)
            return (scaled[0]/w_img, (scaled[0]+scaled[2])/w_img), (scaled[1]/h_img, (scaled[1]+scaled[3])/h_img)
        return default_x, default_y

    def get_window_hwnd(self, keyword):
        hwnd_list = []
        def callback(hwnd, extra):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                class_name = win32gui.GetClassName(hwnd)
                if class_name == "grcWindow":
                    hwnd_list.append((hwnd, title, 10))
                    return
                if "cfx.re" in title.lower():
                    hwnd_list.append((hwnd, title, 9))
                    return
                if keyword.lower() in title.lower():
                    if any(x in title.lower() for x in ["chrome", "firefox", "edge", "visual studio", "cmd.exe", "command prompt", "remotee"]): return
                    hwnd_list.append((hwnd, title, 5))
        win32gui.EnumWindows(callback, None)
        hwnd_list.sort(key=lambda x: x[2], reverse=True)
        return hwnd_list[0][0] if hwnd_list else None

    def capture_background(self, hwnd):
        geometry = self.get_client_geometry(hwnd)
        if not geometry:
            return None
        width, height = geometry[2], geometry[3]
        hwindc = srcdc = memdc = bmp = None
        try:
            hwindc = win32gui.GetDC(hwnd)
            srcdc = win32ui.CreateDCFromHandle(hwindc)
            memdc = srcdc.CreateCompatibleDC()
            bmp = win32ui.CreateBitmap()
            bmp.CreateCompatibleBitmap(srcdc, width, height)
            memdc.SelectObject(bmp)
            result = ctypes.windll.user32.PrintWindow(hwnd, memdc.GetSafeHdc(), 3)
            if not result:
                return None
            bmpinfo = bmp.GetInfo()
            bmpstr = bmp.GetBitmapBits(True)
            img = np.frombuffer(bmpstr, dtype='uint8')
            img = img.reshape((bmpinfo['bmHeight'], bmpinfo['bmWidth'], 4))
            bgr = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            # PrintWindow can report success but return a blank GPU surface.
            if bgr.size == 0 or float(np.std(bgr)) < 1.0:
                return None
            return bgr
        except Exception:
            return None
        finally:
            try:
                if bmp is not None:
                    win32gui.DeleteObject(bmp.GetHandle())
            except Exception:
                pass
            try:
                if memdc is not None:
                    memdc.DeleteDC()
            except Exception:
                pass
            try:
                if srcdc is not None:
                    srcdc.DeleteDC()
            except Exception:
                pass
            try:
                if hwindc is not None:
                    win32gui.ReleaseDC(hwnd, hwindc)
            except Exception:
                pass

    def save_latest_gold_debug_capture(self, bg_img):
        """Expose the exact PrintWindow frame used by the matcher for debugging."""
        try:
            now = time.time()
            if now - self.last_gold_debug_capture_time < 2.0:
                return
            self.last_gold_debug_capture_time = now
            output_path = get_writable_path("debug_gold_live.png")
            temporary_path = output_path + ".tmp.png"
            if cv2.imwrite(temporary_path, bg_img):
                os.replace(temporary_path, output_path)
        except Exception:
            pass

    def bg_click(self, hwnd, x, y):
        lparam = win32api.MAKELONG(int(x), int(y))
        win32gui.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lparam)
        time.sleep(0.05)
        win32gui.PostMessage(hwnd, win32con.WM_LBUTTONUP, 0, lparam)

    def bg_right_click(self, hwnd, x, y):
        lparam = win32api.MAKELONG(int(x), int(y))
        win32gui.PostMessage(hwnd, win32con.WM_RBUTTONDOWN, win32con.MK_RBUTTON, lparam)
        time.sleep(0.05)
        win32gui.PostMessage(hwnd, win32con.WM_RBUTTONUP, 0, lparam)

    def resolve_template_path(self, template_path):
        if os.path.isabs(template_path):
            return template_path
        writable_path = get_writable_path(template_path)
        if os.path.exists(writable_path):
            return writable_path
        return get_resource_path(template_path)

    def get_template_scale(self, template_path, image_width, image_height):
        template_name = os.path.basename(template_path)
        ref_size = self.template_reference_sizes.get(template_name)
        if not ref_size:
            ref_size = self.reference_resolution
        if not ref_size or len(ref_size) != 2:
            ref_size = [1600, 900]
        try:
            ref_w, ref_h = float(ref_size[0]), float(ref_size[1])
            if ref_w <= 0 or ref_h <= 0:
                return 1.0, 1.0
            return image_width / ref_w, image_height / ref_h
        except Exception:
            return 1.0, 1.0

    def find_image(self, bg_img, template_path, threshold, x_range=None, y_range=None):
        try:
            template_path = self.resolve_template_path(template_path)
            if not os.path.exists(template_path): return None
            template = cv2.imread(template_path)
            if template is None: return None
            h, w, _ = bg_img.shape
            x_start, x_end = int(x_range[0] * w) if x_range else 0, int(x_range[1] * w) if x_range else w
            y_start, y_end = int(y_range[0] * h) if y_range else 0, int(y_range[1] * h) if y_range else h
            x_start, x_end = max(0, min(x_start, w)), max(0, min(x_end, w))
            y_start, y_end = max(0, min(y_start, h)), max(0, min(y_end, h))
            crop_img = bg_img[y_start:y_end, x_start:x_end]
            if crop_img.size == 0:
                return None

            scale_x, scale_y = self.get_template_scale(template_path, w, h)
            # Search around the expected scale. This absorbs DPI rounding,
            # window-border differences and small FiveM UI-scale changes.
            nearby_scales = (1.0, 0.95, 1.05, 0.90, 1.10, 0.85, 1.15)
            crop_gray = cv2.cvtColor(crop_img, cv2.COLOR_BGR2GRAY)
            best_val, best_loc, best_size = -1.0, None, None
            seen_sizes = set()

            for nearby in nearby_scales:
                new_w = max(2, int(round(template.shape[1] * scale_x * nearby)))
                new_h = max(2, int(round(template.shape[0] * scale_y * nearby)))
                if (new_w, new_h) in seen_sizes:
                    continue
                seen_sizes.add((new_w, new_h))
                if crop_img.shape[0] < new_h or crop_img.shape[1] < new_w:
                    continue
                interpolation = cv2.INTER_AREA if new_w < template.shape[1] or new_h < template.shape[0] else cv2.INTER_CUBIC
                scaled_template = cv2.resize(template, (new_w, new_h), interpolation=interpolation)

                color_res = cv2.matchTemplate(crop_img, scaled_template, cv2.TM_CCOEFF_NORMED)
                _, color_val, _, color_loc = cv2.minMaxLoc(color_res)
                gray_template = cv2.cvtColor(scaled_template, cv2.COLOR_BGR2GRAY)
                gray_res = cv2.matchTemplate(crop_gray, gray_template, cv2.TM_CCOEFF_NORMED)
                _, gray_val, _, gray_loc = cv2.minMaxLoc(gray_res)
                if gray_val > color_val:
                    score, location = gray_val, gray_loc
                else:
                    score, location = color_val, color_loc
                if score > best_val:
                    best_val, best_loc, best_size = score, location, (new_w, new_h)
                if score >= max(0.97, threshold):
                    break

            if best_loc is None:
                return None
            if best_val >= threshold:
                tw, th = best_size
                return (x_start + best_loc[0] + tw // 2, y_start + best_loc[1] + th // 2, best_val)
            return (None, None, max(0.0, best_val))
        except Exception:
            return None

    def find_gold_count(self, bg_img, ore_x, ore_y, threshold):
        """Require the numerator "30" directly above the detected gold ore."""
        try:
            template_path = self.resolve_template_path("templates/gold_text.png")
            template = cv2.imread(template_path)
            if template is None:
                return None

            # Remove the ore/background from the saved crop. More importantly,
            # keep only the first two glyph groups ("30"), not "/40". The
            # denominator is identical at 10/40, 20/40 and 30/40 and used to
            # produce false positives when it dominated the match score.
            upper = template[:max(3, int(template.shape[0] * 0.48)), :]
            upper_gray = cv2.cvtColor(upper, cv2.COLOR_BGR2GRAY)
            # The item-slot border is mid-gray; 120 isolates the white count
            # glyphs without pulling the whole crop into the template.
            _, bright = cv2.threshold(upper_gray, 120, 255, cv2.THRESH_BINARY)
            component_count, _, stats, _ = cv2.connectedComponentsWithStats(bright, 8)
            components = []
            for index in range(1, component_count):
                cx, cy, cw, ch, area = stats[index]
                if area >= 6 and ch >= 3:
                    components.append((int(cx), int(cy), int(cw), int(ch), int(area)))
            components.sort(key=lambda item: item[0])
            if len(components) < 2:
                return None

            first_two = components[:2]
            first_digit_x, first_digit_y, first_digit_w, first_digit_h, _ = first_two[0]
            first_digit_template = upper[
                first_digit_y:first_digit_y + first_digit_h,
                first_digit_x:first_digit_x + first_digit_w
            ]
            tx = min(item[0] for item in first_two)
            ty = min(item[1] for item in first_two)
            tx_end = max(item[0] + item[2] for item in first_two)
            ty_end = max(item[1] + item[3] for item in first_two)
            tw, th = tx_end - tx, ty_end - ty
            pad = 2
            tx0, ty0 = max(0, tx - pad), max(0, ty - pad)
            tx1, ty1 = min(upper.shape[1], tx + tw + pad), min(upper.shape[0], ty + th + pad)
            numerator_template = upper[ty0:ty1, tx0:tx1]
            if numerator_template.size == 0:
                return None

            h_img, w_img = bg_img.shape[:2]
            ore_path = self.resolve_template_path("templates/gold_ore.png")
            sx, sy = self.get_template_scale(ore_path, w_img, h_img)
            # Search only the count area of this inventory slot. The old wide
            # rectangle could accidentally use a "30" from a neighbouring item.
            x0 = max(0, ore_x - max(4, int(round(10 * sx))))
            x1 = min(w_img, ore_x + max(12, int(round(50 * sx))))
            y0 = max(0, ore_y - max(12, int(round(55 * sy))))
            y1 = min(h_img, ore_y + max(3, int(round(8 * sy))))
            search_img = bg_img[y0:y1, x0:x1]
            if search_img.size == 0:
                return None

            scale_x, scale_y = self.get_template_scale(template_path, w_img, h_img)
            # Text rasterization changes a little more than icons when scaled,
            # so include a wider band around the expected size.
            scale_offsets = (1.0, 0.90, 1.10, 0.82, 1.18, 0.76, 1.24)
            search_gray = cv2.cvtColor(search_img, cv2.COLOR_BGR2GRAY)
            best_val, best_loc, best_size = -1.0, None, None
            seen_sizes = set()
            for nearby in scale_offsets:
                new_w = max(4, int(round(numerator_template.shape[1] * scale_x * nearby)))
                new_h = max(3, int(round(numerator_template.shape[0] * scale_y * nearby)))
                if (new_w, new_h) in seen_sizes:
                    continue
                seen_sizes.add((new_w, new_h))
                if search_gray.shape[0] < new_h or search_gray.shape[1] < new_w:
                    continue
                interpolation = cv2.INTER_AREA if new_w < numerator_template.shape[1] or new_h < numerator_template.shape[0] else cv2.INTER_CUBIC
                scaled = cv2.resize(numerator_template, (new_w, new_h), interpolation=interpolation)
                scaled_gray = cv2.cvtColor(scaled, cv2.COLOR_BGR2GRAY)
                result = cv2.matchTemplate(search_gray, scaled_gray, cv2.TM_CCOEFF_NORMED)
                _, score, _, location = cv2.minMaxLoc(result)
                if score > best_val:
                    best_val, best_loc, best_size = score, location, (new_w, new_h)

            if best_loc is None:
                return (None, None, 0.0, search_img)

            # "20" can still resemble "30" when both tiny digits are matched
            # together because the trailing zero is identical. Verify the first
            # glyph independently: a 3 must match the saved 3 shape, not a 2.
            matched_scale_x = best_size[0] / float(numerator_template.shape[1])
            matched_scale_y = best_size[1] / float(numerator_template.shape[0])
            digit_w = max(2, int(round(first_digit_template.shape[1] * matched_scale_x)))
            digit_h = max(3, int(round(first_digit_template.shape[0] * matched_scale_y)))
            digit_offset_x = int(round((first_digit_x - tx0) * matched_scale_x))
            digit_offset_y = int(round((first_digit_y - ty0) * matched_scale_y))
            digit_x0 = best_loc[0] + digit_offset_x
            digit_y0 = best_loc[1] + digit_offset_y
            digit_crop = search_gray[digit_y0:digit_y0 + digit_h, digit_x0:digit_x0 + digit_w]
            first_digit_score = -1.0
            if digit_crop.shape == (digit_h, digit_w):
                digit_interpolation = cv2.INTER_AREA if digit_w < first_digit_template.shape[1] or digit_h < first_digit_template.shape[0] else cv2.INTER_CUBIC
                scaled_digit = cv2.resize(first_digit_template, (digit_w, digit_h), interpolation=digit_interpolation)
                scaled_digit_gray = cv2.cvtColor(scaled_digit, cv2.COLOR_BGR2GRAY)
                if float(np.std(scaled_digit_gray)) > 0.5:
                    digit_result = cv2.matchTemplate(digit_crop, scaled_digit_gray, cv2.TM_CCOEFF_NORMED)
                    _, first_digit_score, _, _ = cv2.minMaxLoc(digit_result)

            tw, th = best_size
            center_x = x0 + best_loc[0] + tw // 2
            center_y = y0 + best_loc[1] + th // 2
            if best_val >= threshold and first_digit_score >= 0.72:
                return (center_x, center_y, best_val, search_img)
            return (None, None, max(0.0, best_val), search_img)
        except Exception:
            return None

    def activate_game_window(self):
        try:
            if win32gui.IsIconic(self.hwnd):
                win32gui.ShowWindow(self.hwnd, win32con.SW_RESTORE)
                time.sleep(0.3)
            try: win32gui.SetForegroundWindow(self.hwnd)
            except Exception:
                keyboard.send("alt")
                time.sleep(0.1)
                win32gui.SetForegroundWindow(self.hwnd)
            time.sleep(0.3)
            geometry = self.get_client_geometry()
            if not geometry:
                return None
            cx, cy = geometry[0] + geometry[2] // 2, geometry[1] + geometry[3] // 2
            orig_x, orig_y = win32api.GetCursorPos()
            win32api.SetCursorPos((cx, cy))
            time.sleep(0.1)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            time.sleep(0.05)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            time.sleep(0.2)
            return (orig_x, orig_y)
        except Exception as e:
            self.log_signal.emit(f"[Auto-Feed Error] Focus game failed: {e}")
            return None

    def process_hud_preview(self, bg_img):
        try:
            h_img, w_img, _ = bg_img.shape
            scaled = self.get_scaled_region(self.hud_region)
            if not scaled: return
            hx, hy, hw, hh = scaled
            x_start, x_end = max(0, min(hx, w_img)), max(0, min(hx + hw, w_img))
            y_start, y_end = max(0, min(hy, h_img)), max(0, min(hy + hh, h_img))
            if (x_end - x_start) < 10 or (y_end - y_start) < 10: return
            hud_crop = bg_img[y_start:y_end, x_start:x_end]
            hsv = cv2.cvtColor(hud_crop, cv2.COLOR_BGR2HSV)
            lower_pink, upper_pink = np.array([130, 45, 70]), np.array([170, 255, 255])
            mask = cv2.inRange(hsv, lower_pink, upper_pink)
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            crop_w = mask.shape[1]
            hunger_px = int(np.sum(mask[:, :crop_w//2] > 0))
            thirst_px = int(np.sum(mask[:, crop_w//2:] > 0))
            color_mask = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
            color_mask[mask > 0] = [180, 50, 240]
            self.hud_preview_signal.emit(hud_crop, color_mask, hunger_px, thirst_px)
        except Exception: pass

    def execute_feeding_sequence(self, need_food, need_water):
        self.log_signal.emit(f"[ระบบป้อนอาหาร] เริ่มกระบวนการกิน (น้ำ: {need_water}, ข้าว: {need_food})...")
        orig_pos = self.activate_game_window()
        send_key_direct("esc")
        time.sleep(1.0)
        send_key_direct("x")
        time.sleep(1.0)
        if need_water:
            self.log_signal.emit("[ระบบป้อนอาหาร] กำลังกินน้ำ (ช่อง 6)...")
            send_key_direct("6")
            time.sleep(8.0)
        if need_food:
            self.log_signal.emit("[ระบบป้อนอาหาร] กำลังกินอาหาร (ช่อง 7)...")
            send_key_direct("7")
            time.sleep(8.0)
        self.log_signal.emit("[ระบบป้อนอาหาร] กลับไปทำอาชีพ (กด E ค้าง 1.5 วินาที)...")
        press_key_hold("e")
        time.sleep(1.5)
        release_key_hold("e")
        time.sleep(1.5)
        bg_after = self.capture_background(self.hwnd)
        if bg_after is not None:
            h_img, w_img, _ = bg_after.shape
            scaled_af = self.get_scaled_region(self.auto_farm_region)
            af_range_x = (scaled_af[0]/w_img, (scaled_af[0]+scaled_af[2])/w_img) if scaled_af else None
            af_range_y = (scaled_af[1]/h_img, (scaled_af[1]+scaled_af[3])/h_img) if scaled_af else None
            
            btn_result = self.find_image(bg_after, "templates/auto_farm.png", 0.85, x_range=af_range_x, y_range=af_range_y)
            if not btn_result or btn_result[0] is None:
                # [แก้ไข] ค้นหาปุ่มเริ่มงานทั่วหน้าจอ ป้องกันตั้งพิกัดคลาดเคลื่อน
                btn_result = self.find_image(bg_after, "templates/auto_farm.png", 0.70)
                
            if btn_result and btn_result[0] is not None:
                bx, by, bval = btn_result
                win32api.SetCursorPos(self.client_to_screen(bx, by))
                time.sleep(0.1)
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                time.sleep(0.05)
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                time.sleep(2.0)
        self.log_signal.emit("[ระบบป้อนอาหาร] กำลังเปิดกระเป๋าอีกครั้ง (ปุ่ม T)...")
        send_key_direct("t")
        time.sleep(1.0)
        if orig_pos:
            try: win32api.SetCursorPos(orig_pos)
            except: pass
        self.log_signal.emit("[ระบบป้อนอาหาร] กินเสร็จเรียบร้อย!")

    def check_and_run_auto_feed(self):
        bg_img = self.capture_background(self.hwnd)
        if bg_img is None: return
        h_img, w_img, _ = bg_img.shape
        scaled = self.get_scaled_region(self.hud_region)
        if not scaled: return
        hx, hy, hw, hh = scaled
        x_start, x_end = max(0, min(hx, w_img)), max(0, min(hx + hw, w_img))
        y_start, y_end = max(0, min(hy, h_img)), max(0, min(hy + hh, h_img))
        if x_end - x_start < 10 or y_end - y_start < 10: return
        hud_crop = bg_img[y_start:y_end, x_start:x_end]
        hsv = cv2.cvtColor(hud_crop, cv2.COLOR_BGR2HSV)
        lower_pink, upper_pink = np.array([130, 45, 70]), np.array([170, 255, 255])
        mask = cv2.inRange(hsv, lower_pink, upper_pink)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        crop_w = mask.shape[1]
        hunger_px = np.sum(mask[:, :crop_w//2] > 0)
        thirst_px = np.sum(mask[:, crop_w//2:] > 0)
        need_food, need_water = hunger_px < self.hunger_limit, thirst_px < self.thirst_limit
        if need_food or need_water: self.execute_feeding_sequence(need_food, need_water)

    def double_click_at(self, abs_x, abs_y):
        try:
            win32api.SetCursorPos((abs_x, abs_y))
            time.sleep(0.1)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            time.sleep(0.05)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            time.sleep(0.05)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            time.sleep(0.05)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        except Exception: pass

    def check_diamonds_exceed_30(self, slot_img):
        """Return True only when the displayed diamond count is at least 30.

        FiveM renders the count as tiny text such as ``31/40``.  The old
        detector treated the narrowest character as the slash, but the digit
        ``1`` is actually narrower than ``/``.  That made 31/40 fail.  Split
        the five glyphs as two numerator digits + slash + ``40`` instead, then
        distinguish a leading 3/4 from a leading 1/2 by the lower-half stroke.
        """
        try:
            h, w = slot_img.shape[:2]
            if h < 10 or w < 10:
                return False

            # Number text "X/Y" is in the top-right area of the slot.
            # The match centre can move slightly when the diamond artwork is
            # re-cropped.  Keep enough of the slot's upper half so the count is
            # not clipped to only its first four pixel rows.
            num_h = max(10, int(h * 0.40))
            num_w = max(12, int(w * 0.68))
            num_area = slot_img[:num_h, w - num_w:]
            gray = cv2.cvtColor(num_area, cv2.COLOR_BGR2GRAY)

            # A slightly lower threshold preserves all seven pixel rows of the
            # tiny anti-aliased font while the dark inventory background stays
            # black.
            _, thresh = cv2.threshold(gray, 105, 255, cv2.THRESH_BINARY)

            # Analyze column projection to find character groups.
            col_has = np.any(thresh > 0, axis=0)
            groups = []
            in_g = False
            start = 0
            for i in range(len(col_has)):
                if col_has[i] and not in_g:
                    start = i
                    in_g = True
                elif not col_has[i] and in_g:
                    if i - start >= 2:
                        groups.append((start, i))
                    in_g = False
            if in_g and len(col_has) - start >= 2:
                groups.append((start, len(col_has)))

            # NN/40 contains five groups.  Do not guess the slash from width:
            # in 31/40 the "1" is narrower than the slash.
            if len(groups) < 5:
                return False

            # Use the rightmost five groups so an unrelated bright edge on the
            # left cannot shift the count characters.
            count_groups = groups[-5:]
            first_x0, first_x1 = count_groups[0]
            first_glyph = thresh[:, first_x0:first_x1]
            row_has = np.any(first_glyph > 0, axis=1)
            active_rows = np.flatnonzero(row_has)
            if active_rows.size < 5 or first_glyph.shape[1] < 3:
                return False
            first_glyph = first_glyph[
                active_rows[0]:active_rows[-1] + 1, :
            ]

            # For this font, a leading 2 has its lower-middle stroke on the
            # left.  A leading 3 (and 4) has that stroke on the right.  This
            # rejects 10/40 and 20/40 while accepting 30/40 through 40/40.
            gh, gw = first_glyph.shape
            lower_y0 = max(0, int(round(gh * 0.52)))
            lower_y1 = max(lower_y0 + 1, int(round(gh * 0.86)))
            side_w = max(1, int(round(gw * 0.45)))
            lower_band = first_glyph[lower_y0:lower_y1, :]
            left_stroke = int(np.count_nonzero(lower_band[:, :side_w]))
            right_stroke = int(np.count_nonzero(lower_band[:, gw-side_w:]))
            return right_stroke > 0 and right_stroke >= left_stroke + 1
        except Exception:
            return False

    def execute_store_diamonds_sequence(self):
        self.log_signal.emit("[ระบบเก็บเพชร] เริ่มกระบวนการเก็บเพชรลงรถ...")
        orig_pos = self.activate_game_window()
        send_key_direct("esc")
        time.sleep(1.0)
        send_key_direct("x")
        time.sleep(1.0)
        send_key_direct("h")
        time.sleep(1.5)
        bg_img = self.capture_background(self.hwnd)
        if bg_img is not None:
            h_img, w_img, _ = bg_img.shape
            tr_x, tr_y = self.get_region_ranges(self.trunk_ready_search_region, w_img, h_img, (0.0, 1.0), (0.0, 1.0))
            btn_ready = self.find_image(bg_img, "templates/trunk_ready.png", 0.60, x_range=tr_x, y_range=tr_y)
            if btn_ready and btn_ready[0] is not None:
                bx, by, bval = btn_ready
                screen_x, screen_y = self.client_to_screen(bx, by)
                self.double_click_at(screen_x, screen_y)
                time.sleep(4.0)
        bg_trunk = self.capture_background(self.hwnd)
        if bg_trunk is not None:
            h_img, w_img, _ = bg_trunk.shape
            scaled_bag = self.get_scaled_region(self.bag_region)
            default_x = (scaled_bag[0]/w_img, (scaled_bag[0]+scaled_bag[2])/w_img) if scaled_bag else (0.33, 0.85)
            default_y = (scaled_bag[1]/h_img, (scaled_bag[1]+scaled_bag[3])/h_img) if scaled_bag else (0.0, 1.0)
            
            dia_x, dia_y = self.get_region_ranges(self.diamond_trunk_search_region, w_img, h_img, default_x, default_y)
            diamond_result = self.find_image(bg_trunk, "templates/diamond_trunk.png", 0.70, x_range=dia_x, y_range=dia_y)
            
            if diamond_result and diamond_result[0] is not None:
                dx, dy, dval = diamond_result
                screen_x, screen_y = self.client_to_screen(dx, dy)
                self.double_click_at(screen_x, screen_y)
                time.sleep(1.0)
                bg_pop = self.capture_background(self.hwnd)
                if bg_pop is not None:
                    at_x, at_y = self.get_region_ranges(self.all_trunk_search_region, w_img, h_img, (0.0, 1.0), (0.0, 1.0))
                    btn_all = self.find_image(bg_pop, "templates/all_trunk.png", 0.60, x_range=at_x, y_range=at_y)
                    if btn_all and btn_all[0] is not None:
                        ax, ay, aval = btn_all
                        win32api.SetCursorPos(self.client_to_screen(ax, ay))
                        time.sleep(0.1)
                        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                        time.sleep(0.05)
                        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                        time.sleep(0.5)
                        bg_confirm = self.capture_background(self.hwnd)
                        if bg_confirm is not None:
                            ct_x, ct_y = self.get_region_ranges(self.confirm_trunk_search_region, w_img, h_img, (0.0, 1.0), (0.0, 1.0))
                            btn_conf = self.find_image(bg_confirm, "templates/confirm_trunk.png", 0.60, x_range=ct_x, y_range=ct_y)
                            if btn_conf and btn_conf[0] is not None:
                                cx, cy, cval = btn_conf
                                win32api.SetCursorPos(self.client_to_screen(cx, cy))
                                time.sleep(0.1)
                                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                                time.sleep(0.05)
                                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                                time.sleep(1.5)
        send_key_direct("esc")
        time.sleep(1.0)
        press_key_hold("e")
        time.sleep(1.5)
        release_key_hold("e")
        time.sleep(1.5)
        bg_final = self.capture_background(self.hwnd)
        if bg_final is not None:
            # [แก้ไข] ค้นหาปุ่มเริ่มงานทั่วหน้าจอ ป้องกันตั้งพิกัดคลาดเคลื่อน
            btn_result = self.find_image(bg_final, "templates/auto_farm.png", 0.70)
            if btn_result and btn_result[0] is not None:
                bx, by, _ = btn_result
                win32api.SetCursorPos(self.client_to_screen(bx, by))
                time.sleep(0.1)
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                time.sleep(0.05)
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                time.sleep(2.0)
        send_key_direct("t")
        time.sleep(1.0)
        if orig_pos:
            try: win32api.SetCursorPos(orig_pos)
            except: pass
        self.log_signal.emit("[ระบบเก็บเพชร] เสร็จสิ้น!")

    def check_and_run_store_diamonds(self, trigger_storage=False):
        bg_img = self.capture_background(self.hwnd)
        if bg_img is None: return
        h_img, w_img, _ = bg_img.shape
        scaled_bag = self.get_scaled_region(self.bag_region)
        default_x = (scaled_bag[0]/w_img, (scaled_bag[0]+scaled_bag[2])/w_img) if scaled_bag else (0.33, 0.85)
        default_y = (scaled_bag[1]/h_img, (scaled_bag[1]+scaled_bag[3])/h_img) if scaled_bag else (0.0, 1.0)
        dia_x, dia_y = self.get_region_ranges(self.diamond_search_region, w_img, h_img, default_x, default_y)
        # A 70% match is not specific enough for the small inventory artwork:
        # orange medicine bottles can reach ~70% and previously triggered the
        # complete trunk sequence. Real diamond captures are consistently
        # around 90%, so require a high-confidence icon match.
        diamond_result = self.find_image(bg_img, "templates/diamond_icon.png", 0.86, x_range=dia_x, y_range=dia_y)
        if diamond_result and diamond_result[0] is not None:
            dx, dy, val = diamond_result
            # Load template to get actual dimensions for proper slot extraction
            tpl_w_path = get_writable_path("templates/diamond_icon.png")
            tpl_path = tpl_w_path if os.path.exists(tpl_w_path) else get_resource_path("templates/diamond_icon.png")
            tpl = cv2.imread(tpl_path)
            if tpl is not None:
                th, tw = tpl.shape[:2]
            else:
                th, tw = 55, 43
            # Extract slot area centered on match with adaptive margin
            margin = max(12, int(max(tw, th) * 0.35))
            x_start = max(0, dx - tw // 2 - margin)
            x_end = min(w_img, dx + tw // 2 + margin)
            y_start = max(0, dy - th // 2 - margin)
            y_end = min(h_img, dy + th // 2 + margin)
            slot_img = np.zeros((10, 10, 3), dtype=np.uint8)
            passed = False
            status_str = "ไม่ผ่านเกณฑ์ (< 30 เม็ด)"
            slot_w, slot_h = x_end - x_start, y_end - y_start
            if slot_w >= 20 and slot_h >= 20:
                slot_img = bg_img[y_start:y_end, x_start:x_end]
                passed = self.check_diamonds_exceed_30(slot_img)
                if passed:
                    status_str = "ผ่านเกณฑ์ >= 30 เม็ด (เตรียมเก็บของ)"
            if passed:
                self.diamond_pass_streak += 1
            else:
                self.diamond_pass_streak = 0
            confirmed = passed and self.diamond_pass_streak >= 2
            if passed and not confirmed:
                status_str = "พบเพชร >= 30 เม็ด กำลังยืนยันภาพซ้ำก่อนเก็บ"
            self.diamond_preview_signal.emit(slot_img, val, confirmed, status_str)
            if confirmed and trigger_storage:
                now = time.time()
                # Never repeat the long storage sequence continuously when the
                # inventory has not changed or a prior storage attempt failed.
                if now - self.last_diamond_storage_time >= 120.0:
                    self.last_diamond_storage_time = now
                    self.diamond_pass_streak = 0
                    self.execute_store_diamonds_sequence()
        else:
            self.diamond_pass_streak = 0
            val = diamond_result[2] if diamond_result else 0.0
            slot_img = np.zeros((10, 10, 3), dtype=np.uint8)
            self.diamond_preview_signal.emit(slot_img, val, False, "ไม่พบรูปเพชรในกระเป๋า")

    def run(self):
        while not self.is_exiting:
            try:
                if not self.hwnd:
                    self.hwnd = self.get_window_hwnd(WINDOW_NAME)
                    if self.hwnd: self.connection_signal.emit(True, win32gui.GetWindowText(self.hwnd))
                    else:
                        self.connection_signal.emit(False, "กำลังค้นหาหน้าต่างเกม FiveM...")
                        time.sleep(2)
                        continue
                if not win32gui.IsWindow(self.hwnd):
                    self.hwnd = None
                    self.connection_signal.emit(False, "การเชื่อมต่อขาดหาย...")
                    continue
                bg_img = self.capture_background(self.hwnd)
                if bg_img is None:
                    time.sleep(1.5)
                    continue
                self.save_latest_gold_debug_capture(bg_img)
                if self.hud_region: self.process_hud_preview(bg_img)
                if self.force_feed_test:
                    self.force_feed_test = False
                    self.execute_feeding_sequence(need_food=True, need_water=True)
                    continue
                if self.force_store_test:
                    self.force_store_test = False
                    self.execute_store_diamonds_sequence()
                    continue
                if not self.is_running:
                    time.sleep(0.5)
                    continue
                match_status = {}
                h_img, w_img, _ = bg_img.shape
                all_x, all_y = self.get_region_ranges(self.all_search_region, w_img, h_img, (0.35, 0.65), (0.35, 0.75))
                all_result = self.find_image(bg_img, TEMPLATES["all"], self.thresholds["all"], x_range=all_x, y_range=all_y)
                if all_result and all_result[0] is not None:
                    x_all, y_all, val_all = all_result
                    match_status["all"] = (True, val_all)
                    self.match_signal.emit(match_status)
                    self.bg_click(self.hwnd, x_all, y_all)
                    time.sleep(0.5)
                    bg_img_after = self.capture_background(self.hwnd)
                    if bg_img_after is not None:
                        conf_x, conf_y = self.get_region_ranges(self.confirm_search_region, w_img, h_img, (0.35, 0.65), (0.35, 0.75))
                        confirm_result = self.find_image(bg_img_after, TEMPLATES["confirm"], self.thresholds["confirm"], x_range=conf_x, y_range=conf_y)
                        if confirm_result and confirm_result[0] is not None:
                            x_conf, y_conf, val_conf = confirm_result
                            match_status["confirm"] = (True, val_conf)
                            self.match_signal.emit(match_status)
                            self.bg_click(self.hwnd, x_conf, y_conf)
                            time.sleep(self.delays["confirm"])
                            if self.auto_store_enabled: self.check_and_run_store_diamonds(trigger_storage=True)
                    continue
                else:
                    match_status["all"], match_status["confirm"] = (False, all_result[2] if all_result else 0.0), (False, 0.0)
                
                dest_x, dest_y = self.get_region_ranges(self.destroy_search_region, w_img, h_img, (0.25, 0.85), (0.15, 0.90))
                destroy_result = self.find_image(bg_img, TEMPLATES["destroy"], self.thresholds["destroy"], x_range=dest_x, y_range=dest_y)
                if destroy_result and destroy_result[0] is not None:
                    x, y, val = destroy_result
                    match_status["destroy"] = (True, val)
                    self.match_signal.emit(match_status)
                    self.bg_click(self.hwnd, x, y)
                    time.sleep(self.delays["destroy"])
                    continue
                else:
                    match_status["destroy"] = (False, destroy_result[2] if destroy_result else 0.0)

                gold_ore_path, gold_text_path = "templates/gold_ore.png", "templates/gold_text.png"
                preview_ore_img, preview_text_img = np.zeros((10, 10, 3), dtype=np.uint8), np.zeros((10, 10, 3), dtype=np.uint8)
                preview_ore_score, preview_text_score, preview_target_thresh = 0.0, 0.0, self.thresholds["gold"]
                
                gold_x, gold_y = self.get_region_ranges(self.gold_search_region, w_img, h_img, (0.25, 0.85), (0.15, 0.90))
                ore_result = self.find_image(bg_img, gold_ore_path, 0.72, x_range=gold_x, y_range=gold_y)
                if ore_result: preview_ore_score = ore_result[2]
                if ore_result and ore_result[0] is not None:
                    ore_x, ore_y, ore_val = ore_result
                    h_img, w_img, _ = bg_img.shape
                    abs_ore_path = self.resolve_template_path(gold_ore_path)
                    ore_tpl = cv2.imread(abs_ore_path)
                    if ore_tpl is not None:
                        ore_sx, ore_sy = self.get_template_scale(abs_ore_path, w_img, h_img)
                        ow = max(1, int(ore_tpl.shape[1] * ore_sx))
                        oh = max(1, int(ore_tpl.shape[0] * ore_sy))
                        tl_x, tl_y = max(0, min(w_img - 1, ore_x - ow // 2)), max(0, min(h_img - 1, ore_y - oh // 2))
                        preview_ore_img = bg_img[tl_y:min(h_img, tl_y+oh), tl_x:min(w_img, tl_x+ow)]

                    # Requiring a literal 95% full-crop match was brittle:
                    # anti-aliasing alone can change the score after scaling.
                    # The combined ore + count check safely allows a lower text
                    # threshold while still requiring the actual "30/40" glyphs.
                    target_thresh = max(0.76, min(float(self.thresholds["gold"]), 0.84))
                    preview_target_thresh = target_thresh
                    count_result = self.find_gold_count(bg_img, ore_x, ore_y, target_thresh)
                    if count_result:
                        count_x, count_y, count_score, count_crop = count_result
                        preview_text_score = count_score
                        preview_text_img = count_crop
                        is_matched = count_x is not None
                        match_status["gold"] = (is_matched, count_score)
                        if is_matched:
                            self.match_signal.emit(match_status)
                            self.bg_right_click(self.hwnd, ore_x, ore_y)
                            time.sleep(self.delays["gold"])
                            self.gold_preview_signal.emit(preview_ore_img, preview_text_img, preview_ore_score, preview_text_score, preview_target_thresh)
                            continue
                    else:
                        match_status["gold"] = (False, 0.0)
                else:
                    match_status["gold"] = (False, ore_result[2] if ore_result else 0.0)
                
                self.gold_preview_signal.emit(preview_ore_img, preview_text_img, preview_ore_score, preview_text_score, preview_target_thresh)
                if self.hud_region and self.auto_feed_enabled and time.time() - self.last_hud_check_time > 10.0:
                    self.last_hud_check_time = time.time()
                    self.check_and_run_auto_feed()

                if self.auto_store_enabled and time.time() - self.last_diamond_check_time > 5.0:
                    self.last_diamond_check_time = time.time()
                    # This periodic check used to update only the preview, so a
                    # valid >=30 count never started the trunk sequence unless
                    # it happened immediately after destroying gold.
                    self.check_and_run_store_diamonds(trigger_storage=True)

                self.match_signal.emit(match_status)
                time.sleep(0.3)
            except Exception as error:
                message = f"{type(error).__name__}: {error}"
                now = time.time()
                if message != self.last_runtime_error or now - self.last_runtime_error_time > 10.0:
                    self.log_signal.emit(f"[ข้อผิดพลาดในลูป] {message}")
                    self.last_runtime_error = message
                    self.last_runtime_error_time = now
                time.sleep(1.5)

    def stop(self):
        self.is_exiting = True
        self.quit()
        self.wait()

# ==========================================
# MAIN GUI WINDOW
# ==========================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config_path = get_writable_path("config.json")
        self.load_config()
        self.setWindowTitle("ระบบมาโครทิ้งทองอัตโนมัติ (Background)")
        self.resize(760, 580)
        self.setStyleSheet("""
            QMainWindow { background-color: #f8fafc; }
            QWidget { color: #334155; font-family: 'Segoe UI', sans-serif; }
            QGroupBox { border: 1px solid #cbd5e1; border-radius: 8px; margin-top: 15px; font-weight: bold; font-size: 13px; color: #475569; background-color: #ffffff; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            QFrame#Card { background-color: #f1f5f9; border: 1px solid #e2e8f0; border-radius: 8px; }
            QLabel { font-size: 12px; }
            QLabel#Title { font-size: 18px; font-weight: bold; color: #1e293b; }
            QPushButton { background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; font-weight: bold; font-size: 11px; padding: 6px 10px; }
            QPushButton:hover { background-color: #f1f5f9; border: 1px solid #94a3b8; }
            QPushButton#StartBtn { background-color: #0d9488; border: none; border-radius: 6px; color: white; font-weight: bold; font-size: 14px; padding: 12px; }
            QPushButton#StartBtn:hover { background-color: #0f766e; }
            QPushButton#StartBtn[running="true"] { background-color: #ef4444; }
            QSlider::groove:horizontal { border: 1px solid #cbd5e1; height: 5px; background: #e2e8f0; border-radius: 2px; }
            QSlider::handle:horizontal { background: #0d9488; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }
            QSlider::sub-page:horizontal { background: #0d9488; border-radius: 2px; }
            QTextEdit#Log { background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; font-family: 'Consolas', monospace; font-size: 11px; }
        """)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(12)

        header_layout = QHBoxLayout()
        title_label = QLabel("มาโครทิ้งทอง FiveM Background")
        title_label.setObjectName("Title")
        self.status_bar = QFrame()
        self.status_bar.setStyleSheet("QFrame { background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 12px; padding: 4px 12px; }")
        status_bar_layout = QHBoxLayout(self.status_bar)
        status_bar_layout.setContentsMargins(5, 2, 5, 2)
        self.status_dot = QLabel("⬤")
        self.status_dot.setStyleSheet("color: #ef4444; font-size: 10px;")
        self.status_text = QLabel("กำลังค้นหาหน้าต่างเกม FiveM...")
        status_bar_layout.addWidget(self.status_dot)
        status_bar_layout.addWidget(self.status_text)
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.status_bar)
        main_layout.addLayout(header_layout)

        content_layout = QHBoxLayout()
        content_layout.setSpacing(15)

        left_column = QVBoxLayout()
        left_column.setSpacing(10)
        
        left_tabs = QTabWidget()
        
        # Tab 1: Configuration
        tab_config = QWidget()
        config_tab_layout = QVBoxLayout(tab_config)
        config_tab_layout.setSpacing(8)
        
        setup_box = QGroupBox("ตั้งค่าขอบเขตพิกัดหน้าต่างเกม")
        setup_layout = QVBoxLayout(setup_box)
        setup_layout.setSpacing(8)
        self.hud_lbl = QLabel(self.get_region_text(self.hud_region))
        self.hud_lbl.setStyleSheet("color: #64748b; font-size: 11px;")
        hud_btn = QPushButton("เลือกพื้นที่หลอดอาหาร/น้ำ")
        hud_btn.clicked.connect(self.select_hud_region)
        self.bag_lbl = QLabel(self.get_region_text(self.bag_region))
        self.bag_lbl.setStyleSheet("color: #64748b; font-size: 11px;")
        bag_btn = QPushButton("เลือกพื้นที่กระเป๋าฝั่งขวา")
        bag_btn.clicked.connect(self.select_bag_region)
        self.af_lbl = QLabel(self.get_region_text(self.auto_farm_region))
        self.af_lbl.setStyleSheet("color: #64748b; font-size: 11px;")
        af_btn = QPushButton("ลงทะเบียนปุ่มฟาร์มอัตโนมัติ (Crop)")
        af_btn.clicked.connect(self.select_auto_farm_region)
        setup_layout.addWidget(QLabel("ขอบเขตหลอดสุขภาพ (HUD):"))
        setup_layout.addWidget(self.hud_lbl)
        setup_layout.addWidget(hud_btn)
        setup_layout.addWidget(QFrame())
        setup_layout.addWidget(QLabel("ขอบเขตกระเป๋าฝั่งขวา:"))
        setup_layout.addWidget(self.bag_lbl)
        setup_layout.addWidget(bag_btn)
        setup_layout.addWidget(QFrame())
        setup_layout.addWidget(QLabel("พิกัดปุ่มเริ่มงานอัตโนมัติ:"))
        setup_layout.addWidget(self.af_lbl)
        setup_layout.addWidget(af_btn)
        config_tab_layout.addWidget(setup_box)

        sliders_box = QGroupBox("เกณฑ์ขั้นต่ำหลอดอาหาร/น้ำ (พิกเซลสีชมพู)")
        sliders_layout = QVBoxLayout(sliders_box)
        sliders_layout.addWidget(QLabel("เกณฑ์หลอดอาหาร (หากน้อยกว่าจะกิน):"))
        self.hunger_val_lbl = QLabel(f"{self.hunger_limit}")
        hunger_slider = QSlider(Qt.Horizontal)
        hunger_slider.setRange(5, 150)
        hunger_slider.setValue(self.hunger_limit)
        hunger_slider.valueChanged.connect(self.on_hunger_limit_changed)
        sliders_layout.addWidget(self.hunger_val_lbl)
        sliders_layout.addWidget(hunger_slider)
        sliders_layout.addWidget(QLabel("เกณฑ์หลอดน้ำ (หากน้อยกว่าจะดื่ม):"))
        self.thirst_val_lbl = QLabel(f"{self.thirst_limit}")
        thirst_slider = QSlider(Qt.Horizontal)
        thirst_slider.setRange(5, 150)
        thirst_slider.setValue(self.thirst_limit)
        thirst_slider.valueChanged.connect(self.on_thirst_limit_changed)
        sliders_layout.addWidget(self.thirst_val_lbl)
        sliders_layout.addWidget(thirst_slider)
        config_tab_layout.addWidget(sliders_box)

        roi_box = QGroupBox("ระบบทดสอบการทำงาน")
        roi_layout = QVBoxLayout(roi_box)
        self.test_feed_btn = QPushButton("ทดสอบระบบกินข้าว/น้ำ")
        self.test_feed_btn.setStyleSheet("QPushButton { background-color: #0284c7; border: none; color: white; font-weight: bold; font-size: 12px; border-radius: 6px; padding: 8px; }")
        self.test_feed_btn.clicked.connect(self.test_feed_sequence)
        self.test_store_btn = QPushButton("ทดสอบระบบเก็บของลงรถ")
        self.test_store_btn.setStyleSheet("QPushButton { background-color: #0d9488; border: none; color: white; font-weight: bold; font-size: 12px; border-radius: 6px; padding: 8px; }")
        self.test_store_btn.clicked.connect(self.test_store_sequence)
        roi_layout.addWidget(self.test_feed_btn)
        roi_layout.addWidget(self.test_store_btn)
        config_tab_layout.addWidget(roi_box)

        toggle_box = QGroupBox("เปิด/ปิดฟังก์ชัน")
        toggle_layout = QVBoxLayout(toggle_box)
        self.auto_feed_cb = QCheckBox("ระบบกินข้าว/น้ำอัตโนมัติ")
        self.auto_feed_cb.setChecked(self.auto_feed_enabled)
        self.auto_feed_cb.toggled.connect(self.on_auto_feed_toggled)
        self.auto_store_cb = QCheckBox("ระบบเก็บเพชรใส่ท้ายรถอัตโนมัติ")
        self.auto_store_cb.setChecked(self.auto_store_enabled)
        self.auto_store_cb.toggled.connect(self.on_auto_store_toggled)
        toggle_layout.addWidget(self.auto_feed_cb)
        toggle_layout.addWidget(self.auto_store_cb)
        config_tab_layout.addWidget(toggle_box)

        # Tab 2: Custom Crops
        tab_crops = QWidget()
        crops_tab_layout = QVBoxLayout(tab_crops)
        crops_tab_layout.setSpacing(6)
        
        crops_scroll = QScrollArea()
        crops_scroll.setWidgetResizable(True)
        crops_scroll_content = QWidget()
        crops_scroll_layout = QVBoxLayout(crops_scroll_content)
        crops_scroll_layout.setSpacing(10)
        
        def create_crop_row(layout, label_text, template_name, region_key):
            row_layout = QHBoxLayout()
            lbl = QLabel(label_text)
            lbl.setStyleSheet("font-weight: bold; color: #475569; font-size: 11px;")
            lbl.setMinimumWidth(180)
            btn_preview = QPushButton("👁️")
            btn_preview.setFixedWidth(30)
            btn_preview.setToolTip("พรีวิวรูปที่ครอปไว้")
            btn_preview.setStyleSheet("QPushButton { font-size: 14px; padding: 2px; }")
            btn_preview.clicked.connect(lambda checked=False, tn=template_name: self.preview_template(tn))
            btn_crop = QPushButton("ครอปรูป")
            btn_crop.setStyleSheet("QPushButton { font-size: 11px; padding: 4px; }")
            btn_crop.clicked.connect(lambda checked=False, tn=template_name: self.crop_template_wizard(tn))
            btn_reg = QPushButton("พื้นที่สแกน")
            btn_reg.setStyleSheet("QPushButton { font-size: 11px; padding: 4px; background-color: #f8fafc; border: 1px solid #cbd5e1; }")
            btn_reg.clicked.connect(lambda checked=False, rk=region_key: self.select_item_search_region(rk))
            row_layout.addWidget(lbl)
            row_layout.addWidget(btn_preview)
            row_layout.addWidget(btn_crop)
            row_layout.addWidget(btn_reg)
            layout.addLayout(row_layout)
            
        g_gold = QGroupBox("🔶 หมวดฟาร์มทอง (ในกระเป๋าตัวละคร)")
        l_gold = QVBoxLayout(g_gold)
        create_crop_row(l_gold, "รูปแร่ทองคำ (ก้อนทอง):", "gold_ore.png", "gold_ore")
        create_crop_row(l_gold, "รูปตัวเลข (แร่ทอง):", "gold_text.png", "gold_text")
        create_crop_row(l_gold, "ปุ่มทำลาย:", "destroy.png", "destroy")
        create_crop_row(l_gold, "ปุ่มทั้งหมด (กระเป๋า):", "all.png", "all")
        create_crop_row(l_gold, "ปุ่มตกลง (กระเป๋า):", "confirm.png", "confirm")
        crops_scroll_layout.addWidget(g_gold)
        
        g_diamond = QGroupBox("💎 หมวดเพชร (ตรวจนับในกระเป๋า)")
        l_diamond = QVBoxLayout(g_diamond)
        create_crop_row(l_diamond, "รูปเพชร (กระเป๋าตัวละคร):", "diamond_icon.png", "diamond")
        crops_scroll_layout.addWidget(g_diamond)
        
        g_trunk = QGroupBox("🚗 หมวดเก็บลงท้ายรถ")
        l_trunk = QVBoxLayout(g_trunk)
        create_crop_row(l_trunk, "รูปเพชร (ท้ายรถ):", "diamond_trunk.png", "diamond_trunk")
        create_crop_row(l_trunk, "ปุ่มเปิดท้ายรถ:", "trunk_ready.png", "trunk_ready")
        create_crop_row(l_trunk, "ปุ่มทั้งหมด (ท้ายรถ):", "all_trunk.png", "all_trunk")
        create_crop_row(l_trunk, "ปุ่มตกลง (ท้ายรถ):", "confirm_trunk.png", "confirm_trunk")
        crops_scroll_layout.addWidget(g_trunk)
        
        g_other = QGroupBox("⚙️ หมวดอื่นๆ")
        l_other = QVBoxLayout(g_other)
        create_crop_row(l_other, "ปุ่มเริ่มงาน (Auto Farm):", "auto_farm.png", "auto_farm")
        crops_scroll_layout.addWidget(g_other)
        
        btn_reset = QPushButton("รีเซ็ตรูปภาพทั้งหมดเป็นค่าเริ่มต้น")
        btn_reset.setStyleSheet("QPushButton { background-color: #ef4444; color: white; font-weight: bold; border-radius: 4px; padding: 6px; }")
        btn_reset.clicked.connect(self.reset_all_templates)
        crops_scroll_layout.addWidget(btn_reset)
        
        crops_scroll.setWidget(crops_scroll_content)
        crops_tab_layout.addWidget(crops_scroll)
        
        left_tabs.addTab(tab_config, "ตั้งค่าพิกัด & เกณฑ์")
        left_tabs.addTab(tab_crops, "ลงทะเบียนรูปภาพ (Crop)")
        left_column.addWidget(left_tabs)

        right_panel = QVBoxLayout()
        monitors_layout = QHBoxLayout()
        self.monitor_cards = {}
        
        def create_monitor_card(name, display_name):
            card = QFrame()
            card.setObjectName("Card")
            card.setMinimumWidth(80)
            card.setMaximumHeight(85)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(6, 6, 6, 6)
            card_layout.setAlignment(Qt.AlignCenter)
            led = QLabel("⬤")
            led.setStyleSheet("color: #94a3b8; font-size: 16px;")
            lbl = QLabel(display_name)
            lbl.setFont(QFont("Segoe UI", 9, QFont.Bold))
            conf_bar = QLabel("0.0%")
            card_layout.addWidget(led)
            card_layout.addWidget(lbl)
            card_layout.addWidget(conf_bar)
            monitors_layout.addWidget(card)
            self.monitor_cards[name] = {"led": led, "conf": conf_bar, "frame": card}

        create_monitor_card("gold", "1. ทองคำ")
        create_monitor_card("destroy", "2. ทำลาย")
        create_monitor_card("all", "3. ทั้งหมด")
        create_monitor_card("confirm", "4. ดำเนินการ")
        right_panel.addLayout(monitors_layout)
        
        self.preview_tabs = QTabWidget()
        self.hud_tab = QWidget()
        hud_layout = QHBoxLayout(self.hud_tab)
        self.lbl_crop = QLabel("รอรูป...")
        self.lbl_crop.setFixedSize(90, 45)
        self.lbl_crop.setStyleSheet("border: 1px solid #cbd5e1; background-color: #f1f5f9;")
        self.lbl_mask = QLabel("รอมาร์ก...")
        self.lbl_mask.setFixedSize(90, 45)
        self.lbl_mask.setStyleSheet("border: 1px solid #cbd5e1; background-color: #f1f5f9;")
        hud_layout.addWidget(self.lbl_crop)
        hud_layout.addWidget(self.lbl_mask)
        data_layout = QVBoxLayout()
        self.lbl_hud_hunger = QLabel("หลอดอาหาร: - px")
        self.lbl_hud_thirst = QLabel("หลอดน้ำ: - px")
        self.lbl_hud_status = QLabel("สถานะ: รอดำเนินการ")
        data_layout.addWidget(self.lbl_hud_hunger)
        data_layout.addWidget(self.lbl_hud_thirst)
        data_layout.addWidget(self.lbl_hud_status)
        hud_layout.addLayout(data_layout)
        
        self.gold_tab = QWidget()
        gold_layout = QHBoxLayout(self.gold_tab)
        self.lbl_gold_ore = QLabel("รอรูปทอง...")
        self.lbl_gold_ore.setFixedSize(90, 45)
        self.lbl_gold_ore.setStyleSheet("border: 1px solid #cbd5e1; background-color: #f1f5f9;")
        self.lbl_gold_text = QLabel("รอรูปเลข...")
        self.lbl_gold_text.setFixedSize(90, 45)
        self.lbl_gold_text.setStyleSheet("border: 1px solid #cbd5e1; background-color: #f1f5f9;")
        gold_layout.addWidget(self.lbl_gold_ore)
        gold_layout.addWidget(self.lbl_gold_text)
        gold_data_layout = QVBoxLayout()
        self.lbl_gold_ore_val = QLabel("การเจอก้อนทอง: - %")
        self.lbl_gold_text_val = QLabel("ความเหมือนตัวเลข: - %")
        self.lbl_gold_thresh_val = QLabel("เกณฑ์ตัดสินใจทิ้ง: - %")
        gold_data_layout.addWidget(self.lbl_gold_ore_val)
        gold_data_layout.addWidget(self.lbl_gold_text_val)
        gold_data_layout.addWidget(self.lbl_gold_thresh_val)
        gold_layout.addLayout(gold_data_layout)
        self.diamond_tab = QWidget()
        diamond_layout = QHBoxLayout(self.diamond_tab)
        self.lbl_diamond_slot = QLabel("รอรูปเพชร...")
        self.lbl_diamond_slot.setFixedSize(90, 45)
        self.lbl_diamond_slot.setStyleSheet("border: 1px solid #cbd5e1; background-color: #f1f5f9;")
        diamond_layout.addWidget(self.lbl_diamond_slot)
        diamond_data_layout = QVBoxLayout()
        self.lbl_diamond_score = QLabel("ความเหมือนรูปเพชร: - %")
        self.lbl_diamond_status = QLabel("สถานะ: รอดำเนินการ")
        diamond_data_layout.addWidget(self.lbl_diamond_score)
        diamond_data_layout.addWidget(self.lbl_diamond_status)
        diamond_layout.addLayout(diamond_data_layout)
        self.preview_tabs.addTab(self.hud_tab, "พรีวิวหลอดอาหาร/น้ำ")
        self.preview_tabs.addTab(self.gold_tab, "พรีวิวสแกนเศษทองคำ")
        self.preview_tabs.addTab(self.diamond_tab, "พรีวิวสแกนเพชร")
        right_panel.addWidget(self.preview_tabs)

        right_panel.addWidget(QLabel("บันทึกการทำงานของบอท:"))
        self.log_console = QTextEdit()
        self.log_console.setObjectName("Log")
        self.log_console.setReadOnly(True)
        right_panel.addWidget(self.log_console)
        content_layout.addLayout(left_column, 3)
        content_layout.addLayout(right_panel, 4)
        main_layout.addLayout(content_layout)

        footer_layout = QHBoxLayout()
        self.start_btn = QPushButton("เริ่มทำงานบอท [F9]")
        self.start_btn.setObjectName("StartBtn")
        self.start_btn.setProperty("running", "false")
        self.start_btn.setMinimumHeight(45)
        self.start_btn.clicked.connect(self.toggle_macro)
        instruct_lbl = QLabel("<b>คู่มือปุ่มลัด (Hotkey):</b><br>🟢 <b>[F9]</b> - เริ่ม / หยุดบอทชั่วคราว<br>🔴 <b>[F10]</b> - ปิดโปรแกรม")
        instruct_lbl.setStyleSheet("color: #64748b; font-size: 11px;")
        footer_layout.addWidget(self.start_btn, 3)
        footer_layout.addWidget(instruct_lbl, 2)
        main_layout.addLayout(footer_layout)

        self.worker = MacroWorker()
        self.sync_worker_config()
        self.worker.log_signal.connect(self.write_log)
        self.worker.connection_signal.connect(self.update_connection_status)
        self.worker.match_signal.connect(self.update_match_monitors)
        self.worker.hud_preview_signal.connect(self.update_hud_preview)
        self.worker.gold_preview_signal.connect(self.update_gold_preview)
        self.worker.diamond_preview_signal.connect(self.update_diamond_preview)
        self.worker.start()

        keyboard.add_hotkey("F9", self.toggle_macro)
        keyboard.add_hotkey("F10", self.close)
        self.write_log("ยินดีต้อนรับสู่แผงควบคุมระบบฟาร์มทิ้งทองอัตโนมัติ (Background)")

    def sync_worker_config(self):
        for k, v in self.thresholds.items(): self.worker.set_config(k, "threshold", v)
        for k, v in self.delays.items(): self.worker.set_config(k, "delay", v)
        self.worker.set_config("hud", "region", self.hud_region)
        self.worker.set_config("auto_farm", "region", self.auto_farm_region)
        self.worker.set_config("bag", "region", self.bag_region)
        self.worker.set_config("gold_search", "region", self.gold_search_region)
        self.worker.set_config("destroy_search", "region", self.destroy_search_region)
        self.worker.set_config("all_search", "region", self.all_search_region)
        self.worker.set_config("confirm_search", "region", self.confirm_search_region)
        self.worker.set_config("diamond_search", "region", self.diamond_search_region)
        self.worker.set_config("diamond_trunk_search", "region", self.diamond_trunk_search_region)
        self.worker.set_config("trunk_ready_search", "region", self.trunk_ready_search_region)
        self.worker.set_config("all_trunk_search", "region", self.all_trunk_search_region)
        self.worker.set_config("confirm_trunk_search", "region", self.confirm_trunk_search_region)
        self.worker.set_config("hunger", "limit", self.hunger_limit)
        self.worker.set_config("thirst", "limit", self.thirst_limit)
        self.worker.set_config("auto_feed", "toggle", self.auto_feed_enabled)
        self.worker.set_config("auto_store", "toggle", self.auto_store_enabled)
        self.worker.set_config("ref_res", "ref_res", self.reference_resolution)
        self.worker.set_config("template_refs", "template_refs", self.template_reference_sizes)

    @Slot(str)
    def write_log(self, text):
        self.log_console.append(f"{time.strftime('[%H:%M:%S]')} {text}")
        sb = self.log_console.verticalScrollBar()
        sb.setValue(sb.maximum())

    @Slot(bool, str)
    def update_connection_status(self, connected, title):
        if connected:
            self.status_dot.setStyleSheet("color: #22c55e; font-size: 10px;")
            self.status_text.setText(f"เชื่อมต่อแล้ว: {title[:25]}...")
        else:
            self.status_dot.setStyleSheet("color: #eab308; font-size: 10px;")
            self.status_text.setText(title)

    @Slot(dict)
    def update_match_monitors(self, states):
        for name, data in states.items():
            if name in self.monitor_cards:
                matched, confidence = data
                self.monitor_cards[name]["conf"].setText(f"{confidence*100:.1f}%")
                if matched:
                    self.monitor_cards[name]["led"].setStyleSheet("color: #0d9488; font-size: 18px;")
                    self.monitor_cards[name]["frame"].setStyleSheet("border: 1px solid #0d9488; background-color: #f0fdf4;")
                else:
                    self.monitor_cards[name]["led"].setStyleSheet("color: #94a3b8; font-size: 16px;")
                    self.monitor_cards[name]["frame"].setStyleSheet("border: 1px solid #cbd5e1; background-color: #f1f5f9;")

    @Slot(np.ndarray, np.ndarray, int, int)
    def update_hud_preview(self, crop, mask, hunger_px, thirst_px):
        try:
            h, w, c = crop.shape
            self.lbl_crop.setPixmap(QPixmap.fromImage(QImage(crop.tobytes(), w, h, c*w, QImage.Format_BGR888)).scaled(self.lbl_crop.width(), self.lbl_crop.height(), Qt.KeepAspectRatio))
            mh, mw, mc = mask.shape
            self.lbl_mask.setPixmap(QPixmap.fromImage(QImage(mask.tobytes(), mw, mh, mc*mw, QImage.Format_BGR888)).scaled(self.lbl_mask.width(), self.lbl_mask.height(), Qt.KeepAspectRatio))
            self.lbl_hud_hunger.setText(f"หลอดอาหาร: {hunger_px} px (เกณฑ์: {self.hunger_limit})")
            self.lbl_hud_thirst.setText(f"หลอดน้ำ: {thirst_px} px (เกณฑ์: {self.thirst_limit})")
            if hunger_px < self.hunger_limit and thirst_px < self.thirst_limit: self.lbl_hud_status.setText("สถานะ: 🔴 หิว & กระหายน้ำรุนแรง!")
            elif hunger_px < self.hunger_limit: self.lbl_hud_status.setText("สถานะ: 🟡 อาหารหมดเตือนให้กิน!")
            elif thirst_px < self.thirst_limit: self.lbl_hud_status.setText("สถานะ: 🟡 น้ำหมดเตือนให้ดื่ม!")
            else: self.lbl_hud_status.setText("สถานะ: 🟢 ปกติ (กำลังฟาร์ม)")
        except Exception: pass

    @Slot(np.ndarray, np.ndarray, float, float, float)
    def update_gold_preview(self, ore_crop, text_crop, ore_score, text_score, target_thresh):
        try:
            if ore_crop.size > 100:
                h, w, c = ore_crop.shape
                self.lbl_gold_ore.setPixmap(QPixmap.fromImage(QImage(ore_crop.tobytes(), w, h, c*w, QImage.Format_BGR888)).scaled(self.lbl_gold_ore.width(), self.lbl_gold_ore.height(), Qt.KeepAspectRatio))
            if text_crop.size > 100:
                h, w, c = text_crop.shape
                self.lbl_gold_text.setPixmap(QPixmap.fromImage(QImage(text_crop.tobytes(), w, h, c*w, QImage.Format_BGR888)).scaled(self.lbl_gold_text.width(), self.lbl_gold_text.height(), Qt.KeepAspectRatio))
            self.lbl_gold_ore_val.setText(f"การเจอก้อนทอง: {ore_score*100:.1f}%")
            self.lbl_gold_text_val.setText(f"ความเหมือนตัวเลข: {text_score*100:.1f}%")
            self.lbl_gold_thresh_val.setText(f"เกณฑ์ตัดสินใจทิ้ง: {target_thresh*100:.1f}%")
        except Exception: pass

    def toggle_macro(self):
        self.worker.is_running = not self.worker.is_running
        if self.worker.is_running:
            self.start_btn.setText("หยุดทำงานบอทชั่วคราว [F9]")
            self.start_btn.setProperty("running", "true")
        else:
            self.start_btn.setText("เริ่มทำงานบอท [F9]")
            self.start_btn.setProperty("running", "false")
        self.start_btn.style().unpolish(self.start_btn)
        self.start_btn.style().polish(self.start_btn)

    def closeEvent(self, event):
        keyboard.unhook_all_hotkeys()
        self.worker.stop()
        event.accept()

    @Slot(np.ndarray, float, bool, str)
    def update_diamond_preview(self, slot_crop, match_score, passed, status_str):
        try:
            if slot_crop.size > 100:
                h, w, c = slot_crop.shape
                self.lbl_diamond_slot.setPixmap(QPixmap.fromImage(QImage(slot_crop.tobytes(), w, h, c*w, QImage.Format_BGR888)).scaled(self.lbl_diamond_slot.width(), self.lbl_diamond_slot.height(), Qt.KeepAspectRatio))
            self.lbl_diamond_score.setText(f"ความเหมือนรูปเพชร: {match_score*100:.1f}% (เกณฑ์: 86.0%)")
            self.lbl_diamond_status.setText(f"สถานะ: {status_str}")
        except Exception: pass

    def select_bag_region(self):
        if not self.worker.hwnd: return
        self.hide()
        time.sleep(0.3)
        self.selector = RegionSelector(self.bag_region_selected, self.show)
        self.selector.show()
        
    def bag_region_selected(self, x, y, w, h):
        try:
            self.bag_region, self.reference_resolution = self.selection_to_client_region(x, y, w, h)
            self.bag_lbl.setText(self.get_region_text(self.bag_region))
            self.sync_worker_config()
            self.save_config()
        finally:
            self.show()

    def load_config(self):
        self.thresholds = {"gold": 0.84, "destroy": 0.75, "all": 0.65, "confirm": 0.65}
        self.delays = {"gold": 0.8, "destroy": 0.8, "all": 0.5, "confirm": 8.0}
        self.hud_region, self.auto_farm_region, self.bag_region = None, None, None
        self.gold_search_region = None
        self.destroy_search_region = None
        self.all_search_region = None
        self.confirm_search_region = None
        self.diamond_search_region = None
        self.diamond_trunk_search_region = None
        self.trunk_ready_search_region = None
        self.all_trunk_search_region = None
        self.confirm_trunk_search_region = None
        self.hunger_limit, self.thirst_limit = 20, 20
        self.auto_feed_enabled, self.auto_store_enabled = True, True
        self.reference_resolution = None
        self.template_reference_sizes = {}
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "thresholds" in data:
                        self.thresholds.update(data["thresholds"])
                        if self.thresholds.get("gold", 0.84) > 0.90: self.thresholds["gold"] = 0.84
                    if "delays" in data: self.delays.update(data["delays"])
                    self.hud_region = data.get("hud_region", None)
                    self.auto_farm_region = data.get("auto_farm_region", None)
                    self.bag_region = data.get("bag_region", None)
                    self.gold_search_region = data.get("gold_search_region", None)
                    self.destroy_search_region = data.get("destroy_search_region", None)
                    self.all_search_region = data.get("all_search_region", None)
                    self.confirm_search_region = data.get("confirm_search_region", None)
                    self.diamond_search_region = data.get("diamond_search_region", None)
                    self.diamond_trunk_search_region = data.get("diamond_trunk_search_region", None)
                    self.trunk_ready_search_region = data.get("trunk_ready_search_region", None)
                    self.all_trunk_search_region = data.get("all_trunk_search_region", None)
                    self.confirm_trunk_search_region = data.get("confirm_trunk_search_region", None)
                    self.hunger_limit = data.get("hunger_limit", 20)
                    self.thirst_limit = data.get("thirst_limit", 20)
                    self.auto_feed_enabled = data.get("auto_feed_enabled", True)
                    self.auto_store_enabled = data.get("auto_store_enabled", True)
                    self.reference_resolution = data.get("reference_resolution", None)
                    self.template_reference_sizes = data.get("template_reference_sizes", {})
            except Exception: pass

    def save_config(self):
        try:
            data = {
                "thresholds": self.thresholds, "delays": self.delays,
                "hud_region": self.hud_region, "auto_farm_region": self.auto_farm_region,
                "bag_region": self.bag_region,
                "gold_search_region": self.gold_search_region,
                "destroy_search_region": self.destroy_search_region,
                "all_search_region": self.all_search_region,
                "confirm_search_region": self.confirm_search_region,
                "diamond_search_region": self.diamond_search_region,
                "diamond_trunk_search_region": self.diamond_trunk_search_region,
                "trunk_ready_search_region": self.trunk_ready_search_region,
                "all_trunk_search_region": self.all_trunk_search_region,
                "confirm_trunk_search_region": self.confirm_trunk_search_region,
                "hunger_limit": self.hunger_limit, "thirst_limit": self.thirst_limit,
                "auto_feed_enabled": self.auto_feed_enabled, "auto_store_enabled": self.auto_store_enabled,
                "reference_resolution": self.reference_resolution,
                "template_reference_sizes": self.template_reference_sizes
            }
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception: pass

    def get_region_text(self, region):
        if not region: return "ยังไม่ได้ตั้งค่า"
        return f"X:{region[0]}, Y:{region[1]} ({region[2]}x{region[3]})"

    def selection_to_client_region(self, x, y, w, h):
        geometry = self.worker.get_client_geometry()
        if not geometry:
            raise RuntimeError("ไม่พบพื้นที่หน้าต่างเกม")
        client_x, client_y, client_w, client_h = geometry
        x0 = max(0, min(int(x - client_x), client_w))
        y0 = max(0, min(int(y - client_y), client_h))
        x1 = max(0, min(int(x + w - client_x), client_w))
        y1 = max(0, min(int(y + h - client_y), client_h))
        if x1 - x0 < 3 or y1 - y0 < 3:
            raise RuntimeError("พื้นที่ที่เลือกไม่อยู่ในหน้าต่าง FiveM")
        return [x0, y0, x1 - x0, y1 - y0], [client_w, client_h]

    def save_template_from_game_capture(self, template_name, x, y, w, h):
        region, ref_size = self.selection_to_client_region(x, y, w, h)
        background = self.worker.capture_background(self.worker.hwnd)
        if background is None:
            raise RuntimeError("จับภาพเบื้องหลัง FiveM ไม่สำเร็จ")
        rx, ry, rw, rh = region
        crop = background[ry:ry+rh, rx:rx+rw]
        if crop.size == 0:
            raise RuntimeError("รูปที่เลือกว่างเปล่า")
        templates_dir = get_writable_path("templates")
        os.makedirs(templates_dir, exist_ok=True)
        template_path = os.path.join(templates_dir, template_name)
        if not cv2.imwrite(template_path, crop):
            raise RuntimeError("บันทึกรูปต้นแบบไม่สำเร็จ")
        self.reference_resolution = ref_size
        self.template_reference_sizes[template_name] = ref_size
        return region, ref_size

    def select_hud_region(self):
        if not self.worker.hwnd: return
        self.hide()
        time.sleep(0.3)
        self.selector = RegionSelector(self.hud_region_selected, self.show)
        self.selector.show()
        
    def hud_region_selected(self, x, y, w, h):
        try:
            self.hud_region, self.reference_resolution = self.selection_to_client_region(x, y, w, h)
            self.hud_lbl.setText(self.get_region_text(self.hud_region))
            self.sync_worker_config()
            self.save_config()
        finally:
            self.show()
        
    def select_auto_farm_region(self):
        if not self.worker.hwnd: return
        self.hide()
        time.sleep(0.3)
        self.selector = RegionSelector(self.auto_farm_region_selected, self.show)
        self.selector.show()
        
    def auto_farm_region_selected(self, x, y, w, h):
        try:
            self.auto_farm_region, self.reference_resolution = self.save_template_from_game_capture("auto_farm.png", x, y, w, h)
            self.af_lbl.setText(self.get_region_text(self.auto_farm_region))
            self.sync_worker_config()
            self.save_config()
        except Exception as e:
            self.write_log(f"[!] เกิดข้อผิดพลาดในการบันทึกรูปปุ่ม: {e}")
        finally:
            self.show()

    def preview_template(self, template_name):
        writable_p = get_writable_path(os.path.join("templates", template_name))
        bundled_p = get_resource_path(os.path.join("templates", template_name))
        img_path = None
        source = ""
        if os.path.exists(writable_p):
            img_path = writable_p
            source = "(ครอปเอง)"
        elif os.path.exists(bundled_p):
            img_path = bundled_p
            source = "(ค่าเริ่มต้น)"
        if img_path is None:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "ไม่พบรูป", f"ไม่พบรูป {template_name}\nยังไม่ได้ครอปรูปนี้")
            return
        pixmap = QPixmap(img_path)
        if pixmap.isNull():
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "โหลดรูปไม่ได้", f"ไม่สามารถโหลดรูป {template_name}")
            return
        from PySide6.QtWidgets import QDialog
        dialog = QDialog(self)
        dialog.setWindowTitle(f"พรีวิว: {template_name} {source}")
        dlg_layout = QVBoxLayout(dialog)
        info_lbl = QLabel(f"ไฟล์: {os.path.basename(img_path)}\nขนาด: {pixmap.width()}x{pixmap.height()} px\nที่มา: {source}")
        info_lbl.setStyleSheet("font-size: 11px; color: #64748b; padding: 4px;")
        dlg_layout.addWidget(info_lbl)
        img_lbl = QLabel()
        display_pixmap = pixmap.scaled(max(pixmap.width() * 3, 200), max(pixmap.height() * 3, 200), Qt.KeepAspectRatio, Qt.FastTransformation)
        img_lbl.setPixmap(display_pixmap)
        img_lbl.setAlignment(Qt.AlignCenter)
        img_lbl.setStyleSheet("border: 2px solid #cbd5e1; background-color: #1e293b; padding: 8px;")
        dlg_layout.addWidget(img_lbl)
        dialog.setMinimumSize(250, 200)
        dialog.exec()

    def crop_template_wizard(self, template_name):
        if not self.worker.hwnd: return
        self.hide()
        time.sleep(0.3)
        self.current_cropping_template = template_name
        self.selector = RegionSelector(self.template_cropped_callback, self.show)
        self.selector.show()

    def template_cropped_callback(self, x, y, w, h):
        try:
            region, _ = self.save_template_from_game_capture(self.current_cropping_template, x, y, w, h)
            self.sync_worker_config()
            self.save_config()
            self.write_log(f"บันทึกเทมเพลต {self.current_cropping_template} ขนาด {region[2]}x{region[3]} สำเร็จ!")
        except Exception as e:
            self.write_log(f"เกิดข้อผิดพลาดในการครอป: {str(e)}")
        finally:
            self.show()

    def reset_all_templates(self):
        try:
            templates_dir = get_writable_path("templates")
            # In source-code mode this folder is also the only copy of the
            # templates. Deleting it would make every detector stop working.
            if not getattr(sys, "frozen", False):
                self.write_log("โหมดนี้ไม่มีรูปค่าเริ่มต้นแยกต่างหาก จึงไม่ได้ลบรูปที่ใช้งานอยู่")
                return
            if os.path.exists(templates_dir):
                import shutil
                af_p = os.path.join(templates_dir, "auto_farm.png")
                has_af = os.path.exists(af_p)
                af_data = None
                if has_af:
                    with open(af_p, 'rb') as f:
                        af_data = f.read()
                shutil.rmtree(templates_dir)
                os.makedirs(templates_dir, exist_ok=True)
                if has_af and af_data:
                    with open(af_p, 'wb') as f:
                        f.write(af_data)
            auto_farm_ref = self.template_reference_sizes.get("auto_farm.png")
            self.template_reference_sizes = {}
            if auto_farm_ref:
                self.template_reference_sizes["auto_farm.png"] = auto_farm_ref
            self.sync_worker_config()
            self.save_config()
            self.write_log("รีเซ็ตรูปภาพไอคอนทั้งหมดกลับเป็นค่าเริ่มต้น!")
        except Exception as e:
            self.write_log(f"เกิดข้อผิดพลาด: {str(e)}")

    def select_item_search_region(self, item_name):
        if not self.worker.hwnd: return
        self.hide()
        time.sleep(0.3)
        self.current_region_item = item_name
        self.selector = RegionSelector(self.item_search_region_selected, self.show)
        self.selector.show()

    def item_search_region_selected(self, x, y, w, h):
        try:
            rel_region, ref_size = self.selection_to_client_region(x, y, w, h)
            self.reference_resolution = ref_size
            
            if self.current_region_item == "gold":
                self.gold_search_region = rel_region
            elif self.current_region_item == "destroy":
                self.destroy_search_region = rel_region
            elif self.current_region_item == "all":
                self.all_search_region = rel_region
            elif self.current_region_item == "confirm":
                self.confirm_search_region = rel_region
            elif self.current_region_item == "diamond":
                self.diamond_search_region = rel_region
            elif self.current_region_item == "trunk_ready":
                self.trunk_ready_search_region = rel_region
            elif self.current_region_item == "all_trunk":
                self.all_trunk_search_region = rel_region
            elif self.current_region_item == "confirm_trunk":
                self.confirm_trunk_search_region = rel_region
            elif self.current_region_item == "gold_ore":
                self.gold_search_region = rel_region
            elif self.current_region_item == "gold_text":
                self.gold_search_region = rel_region
            elif self.current_region_item == "diamond_trunk":
                self.diamond_trunk_search_region = rel_region
            elif self.current_region_item == "auto_farm":
                self.auto_farm_region = rel_region
                self.reference_resolution = ref_size
                
            self.sync_worker_config()
            self.save_config()
            self.write_log(f"บันทึกขอบเขตการค้นหาสำหรับ {self.current_region_item} เรียบร้อยแล้ว!")
        except Exception as e:
            self.write_log(f"เกิดข้อผิดพลาดในการบันทึกขอบเขต: {str(e)}")
        finally:
            self.show()

    def on_hunger_limit_changed(self, value):
        self.hunger_limit = value
        self.hunger_val_lbl.setText(f"{value}")
        self.worker.set_config("hunger", "limit", value)
        self.save_config()

    def on_thirst_limit_changed(self, value):
        self.thirst_limit = value
        self.thirst_val_lbl.setText(f"{value}")
        self.worker.set_config("thirst", "limit", value)
        self.save_config()

    def test_feed_sequence(self):
        if self.worker.hwnd: self.worker.force_feed_test = True

    def test_store_sequence(self):
        if self.worker.hwnd: self.worker.force_store_test = True

    def on_auto_feed_toggled(self, checked):
        self.auto_feed_enabled = checked
        self.worker.set_config("auto_feed", "toggle", checked)
        self.save_config()

    def on_auto_store_toggled(self, checked):
        self.auto_store_enabled = checked
        self.worker.set_config("auto_store", "toggle", checked)
        self.save_config()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
