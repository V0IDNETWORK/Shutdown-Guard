import os
import sys
import platform
import datetime
import socket
import getpass
import subprocess
import threading
import time
from pathlib import Path

os.environ.setdefault("KIVY_NO_ENV_CONFIG", "1")

from kivy.config import Config
Config.set("graphics", "width", "960")
Config.set("graphics", "height", "680")
Config.set("graphics", "minimum_width", "720")
Config.set("graphics", "minimum_height", "520")
Config.set("input", "mouse", "mouse,disable_multitouch")

from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.animation import Animation
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.uix.popup import Popup
from kivy.graphics import Color, RoundedRectangle, Rectangle, Line
from kivy.core.window import Window
from kivy.properties import (
    StringProperty, BooleanProperty, NumericProperty,
    ColorProperty, ListProperty, ObjectProperty
)
from kivy.lang import Builder
from kivy.utils import get_color_from_hex

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    import requests as req_lib
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    import pyttsx3
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False

DARK_BG = get_color_from_hex("#121212")
DARK_SURFACE = get_color_from_hex("#1E1E1E")
DARK_CARD = get_color_from_hex("#252525")
DARK_TEXT = get_color_from_hex("#E0E0E0")
DARK_SUBTEXT = get_color_from_hex("#9E9E9E")
DARK_ACCENT = get_color_from_hex("#4FC3F7")
DARK_ACCENT2 = get_color_from_hex("#81C784")
DARK_WARNING = get_color_from_hex("#FFB74D")
DARK_ERROR = get_color_from_hex("#EF9A9A")
DARK_BORDER = get_color_from_hex("#333333")

LIGHT_BG = get_color_from_hex("#F5F5F5")
LIGHT_SURFACE = get_color_from_hex("#FFFFFF")
LIGHT_CARD = get_color_from_hex("#F9F9F9")
LIGHT_TEXT = get_color_from_hex("#212121")
LIGHT_SUBTEXT = get_color_from_hex("#757575")
LIGHT_ACCENT = get_color_from_hex("#0288D1")
LIGHT_ACCENT2 = get_color_from_hex("#388E3C")
LIGHT_WARNING = get_color_from_hex("#F57C00")
LIGHT_ERROR = get_color_from_hex("#C62828")
LIGHT_BORDER = get_color_from_hex("#DCDCDC")

SETTINGS_FILE = Path("shutdown_time.txt")
EMAIL_FILE = Path("email_settings.txt")


class ThemeManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.dark_mode = True
            cls._instance._callbacks = []
        return cls._instance

    @property
    def bg(self):
        return DARK_BG if self.dark_mode else LIGHT_BG

    @property
    def surface(self):
        return DARK_SURFACE if self.dark_mode else LIGHT_SURFACE

    @property
    def card(self):
        return DARK_CARD if self.dark_mode else LIGHT_CARD

    @property
    def text(self):
        return DARK_TEXT if self.dark_mode else LIGHT_TEXT

    @property
    def subtext(self):
        return DARK_SUBTEXT if self.dark_mode else LIGHT_SUBTEXT

    @property
    def accent(self):
        return DARK_ACCENT if self.dark_mode else LIGHT_ACCENT

    @property
    def accent2(self):
        return DARK_ACCENT2 if self.dark_mode else LIGHT_ACCENT2

    @property
    def warning(self):
        return DARK_WARNING if self.dark_mode else LIGHT_WARNING

    @property
    def error(self):
        return DARK_ERROR if self.dark_mode else LIGHT_ERROR

    @property
    def border(self):
        return DARK_BORDER if self.dark_mode else LIGHT_BORDER

    def toggle(self):
        self.dark_mode = not self.dark_mode
        for cb in self._callbacks:
            cb()

    def register(self, callback):
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def unregister(self, callback):
        if callback in self._callbacks:
            self._callbacks.remove(callback)


theme = ThemeManager()


def safe_tts(text):
    if not TTS_AVAILABLE:
        return
    def _speak():
        try:
            engine = pyttsx3.init()
            engine.say(text)
            engine.runAndWait()
        except Exception:
            pass
    threading.Thread(target=_speak, daemon=True).start()


class StyledCard(FloatLayout):
    radius = NumericProperty(dp(12))

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(pos=self._redraw, size=self._redraw)
        theme.register(self._redraw)

    def _redraw(self, *args):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*theme.card)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[self.radius])
            Color(*theme.border)
            Line(rounded_rectangle=[self.x, self.y, self.width, self.height, self.radius], width=1)

    def on_kv_post(self, base_widget):
        self._redraw()


class ThemedLabel(Label):
    def __init__(self, is_subtext=False, is_accent=False, **kwargs):
        self.is_subtext = is_subtext
        self.is_accent = is_accent
        super().__init__(**kwargs)
        self._update_color()
        theme.register(self._update_color)

    def _update_color(self, *args):
        if self.is_accent:
            self.color = theme.accent
        elif self.is_subtext:
            self.color = theme.subtext
        else:
            self.color = theme.text


class AnimatedButton(Button):
    def __init__(self, accent=False, danger=False, **kwargs):
        self.accent = accent
        self.danger = danger
        super().__init__(**kwargs)
        self.background_normal = ""
        self.background_down = ""
        self.background_color = [0, 0, 0, 0]
        self.bind(pos=self._redraw, size=self._redraw)
        theme.register(self._redraw)

    def _get_base_color(self):
        if self.danger:
            return theme.error
        if self.accent:
            return theme.accent
        return theme.surface

    def _redraw(self, *args):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*self._get_base_color())
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(8)])

    def on_press(self):
        anim = Animation(size=(self.width * 0.96, self.height * 0.94), t="out_quad", duration=0.08)
        anim.start(self)

    def on_release(self):
        anim = Animation(size=(self.width / 0.96, self.height / 0.94), t="out_elastic", duration=0.2)
        anim.start(self)


class ThemedTextInput(TextInput):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.multiline = False
        self.cursor_color = theme.accent
        self.padding = [dp(12), dp(10), dp(12), dp(10)]
        self.font_size = sp(14)
        self._apply_theme()
        theme.register(self._apply_theme)

    def _apply_theme(self, *args):
        self.background_color = theme.surface
        self.foreground_color = theme.text
        self.hint_text_color = theme.subtext
        self.cursor_color = theme.accent


class SidebarItem(BoxLayout):
    def __init__(self, label, icon_text, on_select, **kwargs):
        super().__init__(orientation="horizontal", size_hint_y=None, height=dp(52), **kwargs)
        self.label = label
        self._on_select = on_select
        self._selected = False
        self.padding = [dp(16), dp(8), dp(16), dp(8)]
        self.spacing = dp(12)

        self.icon_lbl = Label(
            text=icon_text,
            font_size=sp(18),
            size_hint_x=None,
            width=dp(28),
            halign="center",
            valign="middle"
        )
        self.icon_lbl.bind(size=self.icon_lbl.setter("text_size"))

        self.text_lbl = Label(
            text=label,
            font_size=sp(14),
            halign="left",
            valign="middle"
        )
        self.text_lbl.bind(size=self.text_lbl.setter("text_size"))

        self.add_widget(self.icon_lbl)
        self.add_widget(self.text_lbl)

        self.bind(on_touch_down=self._on_touch)
        self.bind(pos=self._redraw, size=self._redraw)
        theme.register(self._redraw)

    def _redraw(self, *args):
        self.canvas.before.clear()
        with self.canvas.before:
            if self._selected:
                Color(*[c * 0.15 for c in theme.accent[:3]] + [1])
            else:
                Color(0, 0, 0, 0)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(8)])
        self.icon_lbl.color = theme.accent if self._selected else theme.subtext
        self.text_lbl.color = theme.text if self._selected else theme.subtext

    def set_selected(self, selected):
        self._selected = selected
        self._redraw()

    def _on_touch(self, instance, touch):
        if self.collide_point(*touch.pos):
            self._on_select(self.label)
            return True


class NotificationPopup(Popup):
    def __init__(self, message, title="Notification", error=False, **kwargs):
        super().__init__(title=title, size_hint=(0.45, 0.28), **kwargs)
        self.separator_color = theme.error if error else theme.accent
        self.title_color = theme.text
        self.background_color = theme.surface

        layout = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(12))
        msg_lbl = ThemedLabel(
            text=message,
            is_subtext=False,
            font_size=sp(14),
            halign="center",
            valign="middle",
            text_size=(self.width - dp(32), None)
        )
        msg_lbl.bind(size=msg_lbl.setter("text_size"))

        close_btn = AnimatedButton(
            text="OK",
            accent=True,
            size_hint=(0.4, None),
            height=dp(44),
            pos_hint={"center_x": 0.5},
            font_size=sp(14),
            color=theme.text
        )
        close_btn.bind(on_release=self.dismiss)

        layout.add_widget(msg_lbl)
        layout.add_widget(close_btn)
        self.content = layout

    def open(self, *args):
        super().open(*args)
        anim = Animation(opacity=1, duration=0.2, t="out_quad")
        self.opacity = 0
        anim.start(self)


def show_notification(message, title="Notification", error=False):
    def _open(dt):
        p = NotificationPopup(message=message, title=title, error=error)
        p.open()
    Clock.schedule_once(_open, 0)


class SystemInfoPanel(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", padding=dp(20), spacing=dp(16), **kwargs)
        self._build_ui()
        theme.register(self._apply_theme)
        Clock.schedule_interval(self._refresh, 2)
        Clock.schedule_once(lambda dt: self._refresh(), 0)

    def _build_ui(self):
        header = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(12))
        title = ThemedLabel(
            text="System Monitor",
            font_size=sp(22),
            bold=True,
            halign="left",
            valign="middle",
            size_hint_x=1
        )
        title.bind(size=title.setter("text_size"))
        header.add_widget(title)

        self.clock_label = ThemedLabel(
            text="",
            is_accent=True,
            font_size=sp(15),
            halign="right",
            valign="middle",
            size_hint_x=None,
            width=dp(200)
        )
        self.clock_label.bind(size=self.clock_label.setter("text_size"))
        header.add_widget(self.clock_label)
        self.add_widget(header)

        self.scroll = ScrollView(do_scroll_x=False)
        self.info_content = BoxLayout(
            orientation="vertical",
            spacing=dp(12),
            size_hint_y=None,
            padding=[0, dp(4), 0, dp(4)]
        )
        self.info_content.bind(minimum_height=self.info_content.setter("height"))
        self.scroll.add_widget(self.info_content)
        self.add_widget(self.scroll)

        Clock.schedule_interval(self._tick_clock, 1)

    def _tick_clock(self, dt):
        now = datetime.datetime.now()
        self.clock_label.text = now.strftime("%H:%M:%S  %Y-%m-%d")

    def _make_section(self, title_text, items):
        card = StyledCard(size_hint_y=None)
        inner = BoxLayout(
            orientation="vertical",
            padding=dp(16),
            spacing=dp(8),
            size_hint_y=None
        )
        sec_title = ThemedLabel(
            text=title_text,
            is_accent=True,
            font_size=sp(13),
            bold=True,
            size_hint_y=None,
            height=dp(28),
            halign="left",
            valign="middle"
        )
        sec_title.bind(size=sec_title.setter("text_size"))
        inner.add_widget(sec_title)

        for key, val in items:
            row = BoxLayout(size_hint_y=None, height=dp(26), spacing=dp(8))
            key_lbl = ThemedLabel(
                text=key,
                is_subtext=True,
                font_size=sp(12),
                halign="left",
                valign="middle",
                size_hint_x=0.38
            )
            key_lbl.bind(size=key_lbl.setter("text_size"))
            val_lbl = ThemedLabel(
                text=str(val),
                font_size=sp(12),
                halign="left",
                valign="middle",
                size_hint_x=0.62
            )
            val_lbl.bind(size=val_lbl.setter("text_size"))
            row.add_widget(key_lbl)
            row.add_widget(val_lbl)
            inner.add_widget(row)

        total_h = dp(28) + dp(8) + len(items) * (dp(26) + dp(8)) + dp(32)
        inner.height = total_h
        card.height = total_h + dp(4)
        card.add_widget(inner)
        return card

    def _gather_info(self):
        sections = []

        try:
            uname = platform.uname()
            hostname = socket.gethostname()
            user = getpass.getuser()
            sys_items = [
                ("OS", f"{uname.system} {uname.release}"),
                ("Version", uname.version[:60] + "..." if len(uname.version) > 60 else uname.version),
                ("Architecture", platform.machine()),
                ("Hostname", hostname),
                ("User", user),
            ]
            sections.append(("System", sys_items))
        except Exception:
            pass

        if PSUTIL_AVAILABLE:
            try:
                boot_time = datetime.datetime.fromtimestamp(psutil.boot_time())
                uptime = datetime.datetime.now() - boot_time
                uptime_str = str(uptime).split(".")[0]
                cpu_freq = psutil.cpu_freq()
                cpu_pct = psutil.cpu_percent(interval=None)
                phys = psutil.cpu_count(logical=False)
                logical = psutil.cpu_count()
                cpu_items = [
                    ("Physical Cores", phys),
                    ("Logical Cores", logical),
                    ("Frequency", f"{cpu_freq.current:.0f} / {cpu_freq.max:.0f} MHz" if cpu_freq else "N/A"),
                    ("Usage", f"{cpu_pct}%"),
                    ("Boot Time", boot_time.strftime("%Y-%m-%d %H:%M")),
                    ("Uptime", uptime_str),
                ]
                sections.append(("CPU", cpu_items))
            except Exception:
                pass

            try:
                mem = psutil.virtual_memory()
                mem_items = [
                    ("Total", f"{mem.total // (1024**2):,} MB"),
                    ("Used", f"{mem.used // (1024**2):,} MB"),
                    ("Available", f"{mem.available // (1024**2):,} MB"),
                    ("Usage", f"{mem.percent}%"),
                ]
                sections.append(("Memory", mem_items))
            except Exception:
                pass

            try:
                parts = psutil.disk_partitions()
                disk_items = []
                for p in parts[:4]:
                    try:
                        usage = psutil.disk_usage(p.mountpoint)
                        disk_items.append((
                            p.device[:20],
                            f"{usage.used // (1024**3)} / {usage.total // (1024**3)} GB ({usage.percent}%)"
                        ))
                    except PermissionError:
                        disk_items.append((p.device[:20], "Permission Denied"))
                if disk_items:
                    sections.append(("Disk", disk_items))
            except Exception:
                pass

            try:
                net_addrs = psutil.net_if_addrs()
                net_items = []
                for iface, addrs in list(net_addrs.items())[:6]:
                    ips = [a.address for a in addrs if a.family == socket.AF_INET]
                    if ips:
                        net_items.append((iface[:20], ips[0]))
                net_io = psutil.net_io_counters()
                net_items.append(("Sent", f"{net_io.bytes_sent // (1024**2)} MB"))
                net_items.append(("Received", f"{net_io.bytes_recv // (1024**2)} MB"))
                if net_items:
                    sections.append(("Network", net_items))
            except Exception:
                pass

            try:
                battery = psutil.sensors_battery()
                if battery:
                    status = "Plugged In" if battery.power_plugged else "On Battery"
                    bat_items = [
                        ("Level", f"{battery.percent:.1f}%"),
                        ("Status", status),
                    ]
                    if not battery.power_plugged and battery.secsleft and battery.secsleft > 0:
                        mins = battery.secsleft // 60
                        bat_items.append(("Remaining", f"{mins // 60}h {mins % 60}m"))
                    sections.append(("Battery", bat_items))
            except Exception:
                pass

        if REQUESTS_AVAILABLE:
            try:
                resp = req_lib.get("https://api.myip.com", timeout=3)
                data = resp.json()
                ip_items = [
                    ("Public IP", data.get("ip", "N/A")),
                    ("Country", data.get("country", "N/A")),
                ]
                sections.append(("Public IP", ip_items))
            except Exception:
                pass

        return sections

    def _refresh(self, dt=None):
        def _worker():
            try:
                sections = self._gather_info()
                Clock.schedule_once(lambda dt2: self._update_ui(sections), 0)
            except Exception:
                pass
        threading.Thread(target=_worker, daemon=True).start()

    def _update_ui(self, sections):
        self.info_content.clear_widgets()
        for title, items in sections:
            card = self._make_section(title, items)
            self.info_content.add_widget(card)

    def _apply_theme(self, *args):
        pass


class TimePicker(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(64), **kwargs)
        self._hour = 0
        self._minute = 0
        self._build()

    def _build(self):
        for attr, label in [("_hour_box", "Hour"), ("_min_box", "Minute")]:
            col = BoxLayout(orientation="vertical", spacing=dp(4))
            lbl = ThemedLabel(
                text=label,
                is_subtext=True,
                font_size=sp(11),
                size_hint_y=None,
                height=dp(18),
                halign="center"
            )
            lbl.bind(size=lbl.setter("text_size"))
            inp = ThemedTextInput(
                text="00",
                font_size=sp(26),
                halign="center",
                size_hint_y=None,
                height=dp(52),
                input_filter="int"
            )
            col.add_widget(lbl)
            col.add_widget(inp)
            setattr(self, attr, inp)
            self.add_widget(col)

        sep = ThemedLabel(
            text=":",
            font_size=sp(28),
            bold=True,
            size_hint_x=None,
            width=dp(24),
            halign="center",
            valign="middle"
        )
        self.insert(1, sep)

    def get_time(self):
        try:
            h = max(0, min(23, int(self._hour_box.text or 0)))
            m = max(0, min(59, int(self._min_box.text or 0)))
            return h, m
        except ValueError:
            return None, None

    def set_time(self, h, m):
        self._hour_box.text = f"{h:02d}"
        self._min_box.text = f"{m:02d}"

    def insert(self, index, widget):
        self.remove_widget(widget) if widget in self.children else None
        children = list(reversed(self.children))
        children.insert(index, widget)
        self.clear_widgets()
        for w in children:
            self.add_widget(w)


class ShutdownPanel(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", padding=dp(24), spacing=dp(20), **kwargs)
        self._build_ui()
        self._load_saved_time()
        theme.register(self._apply_theme)

    def _build_ui(self):
        title = ThemedLabel(
            text="Schedule Shutdown",
            font_size=sp(22),
            bold=True,
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(40)
        )
        title.bind(size=title.setter("text_size"))
        self.add_widget(title)

        desc = ThemedLabel(
            text="Set the time at which your computer will automatically shut down. A warning will be issued 5 minutes before.",
            is_subtext=True,
            font_size=sp(13),
            halign="left",
            valign="top",
            size_hint_y=None,
            height=dp(44)
        )
        desc.bind(size=desc.setter("text_size"))
        self.add_widget(desc)

        card = StyledCard(size_hint_y=None, height=dp(220))
        inner = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(16))

        time_lbl = ThemedLabel(
            text="Shutdown Time (24-hour format)",
            is_subtext=True,
            font_size=sp(12),
            size_hint_y=None,
            height=dp(24),
            halign="left"
        )
        time_lbl.bind(size=time_lbl.setter("text_size"))
        inner.add_widget(time_lbl)

        self.time_picker = TimePicker()
        inner.add_widget(self.time_picker)

        save_btn = AnimatedButton(
            text="Save & Start Scheduler",
            accent=True,
            size_hint=(1, None),
            height=dp(48),
            font_size=sp(15),
            bold=True,
            color=get_color_from_hex("#FFFFFF")
        )
        save_btn.bind(on_release=self._save_time)
        inner.add_widget(save_btn)

        card.add_widget(inner)
        self.add_widget(card)

        self.status_card = StyledCard(size_hint_y=None, height=dp(80))
        self.status_inner = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(4))

        self.status_title = ThemedLabel(
            text="No scheduler running",
            is_subtext=True,
            font_size=sp(13),
            size_hint_y=None,
            height=dp(26),
            halign="left"
        )
        self.status_title.bind(size=self.status_title.setter("text_size"))
        self.status_inner.add_widget(self.status_title)

        self.status_detail = ThemedLabel(
            text="Save a time to start the shutdown scheduler.",
            is_subtext=True,
            font_size=sp(11),
            size_hint_y=None,
            height=dp(22),
            halign="left"
        )
        self.status_detail.bind(size=self.status_detail.setter("text_size"))
        self.status_inner.add_widget(self.status_detail)

        self.status_card.add_widget(self.status_inner)
        self.add_widget(self.status_card)
        self.add_widget(Widget())

    def _save_time(self, *args):
        h, m = self.time_picker.get_time()
        if h is None:
            show_notification("Please enter valid hour and minute values.", title="Invalid Time", error=True)
            return
        time_str = f"{h:02d}:{m:02d}"
        try:
            SETTINGS_FILE.write_text(time_str, encoding="utf-8")
        except OSError as e:
            show_notification(f"Failed to write time file:\n{e}", title="Error", error=True)
            return

        self.status_title.text = f"Scheduler active — shutting down at {time_str}"
        self.status_detail.text = "offing process started in background."

        python_exec = sys.executable
        offing_path = Path("offing.py")
        if offing_path.exists():
            try:
                kwargs = {
                    "stdout": subprocess.DEVNULL,
                    "stderr": subprocess.DEVNULL,
                }
                if platform.system() == "Windows":
                    kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
                subprocess.Popen([python_exec, str(offing_path)], **kwargs)
            except Exception as e:
                show_notification(f"Could not launch scheduler:\n{e}", title="Warning", error=True)
                return
        else:
            try:
                offing_bin = Path("offing")
                if not offing_bin.exists():
                    offing_bin = Path("offing.exe")
                if offing_bin.exists():
                    subprocess.Popen([str(offing_bin)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:
                show_notification(f"Scheduler binary not found:\n{e}", title="Warning", error=True)

        safe_tts(f"Shutdown scheduled at {h:02d} {m:02d}")
        show_notification(f"Shutdown scheduled for {time_str}.", title="Saved")

    def _load_saved_time(self):
        try:
            if SETTINGS_FILE.exists():
                content = SETTINGS_FILE.read_text(encoding="utf-8").strip()
                if ":" in content:
                    parts = content.split(":")
                    h, m = int(parts[0]), int(parts[1])
                    self.time_picker.set_time(h, m)
                    self.status_title.text = f"Last scheduled time: {h:02d}:{m:02d}"
        except Exception:
            pass

    def _apply_theme(self, *args):
        pass


class EmailPanel(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", padding=dp(24), spacing=dp(20), **kwargs)
        self._build_ui()
        self._load_settings()
        theme.register(self._apply_theme)

    def _build_ui(self):
        title = ThemedLabel(
            text="Email Alert Settings",
            font_size=sp(22),
            bold=True,
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(40)
        )
        title.bind(size=title.setter("text_size"))
        self.add_widget(title)

        desc = ThemedLabel(
            text="Configure Gmail SMTP to receive shutdown warnings. Use an App Password, not your main password.",
            is_subtext=True,
            font_size=sp(13),
            halign="left",
            valign="top",
            size_hint_y=None,
            height=dp(44)
        )
        desc.bind(size=desc.setter("text_size"))
        self.add_widget(desc)

        card = StyledCard(size_hint_y=None, height=dp(290))
        inner = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(14))

        fields = [
            ("Sender Gmail Address", False, "sender_input"),
            ("Gmail App Password", True, "password_input"),
            ("Recipient Email Address", False, "receiver_input"),
        ]
        for label_text, is_password, attr in fields:
            row = BoxLayout(orientation="vertical", spacing=dp(4), size_hint_y=None, height=dp(68))
            lbl = ThemedLabel(
                text=label_text,
                is_subtext=True,
                font_size=sp(11),
                size_hint_y=None,
                height=dp(20),
                halign="left"
            )
            lbl.bind(size=lbl.setter("text_size"))
            inp = ThemedTextInput(
                hint_text=label_text,
                password=is_password,
                size_hint_y=None,
                height=dp(44)
            )
            row.add_widget(lbl)
            row.add_widget(inp)
            setattr(self, attr, inp)
            inner.add_widget(row)

        save_btn = AnimatedButton(
            text="Save Email Settings",
            accent=False,
            size_hint=(1, None),
            height=dp(48),
            font_size=sp(15),
            color=theme.accent
        )
        save_btn.bind(on_release=self._save_settings)
        inner.add_widget(save_btn)

        card.add_widget(inner)
        self.add_widget(card)
        self.add_widget(Widget())

    def _save_settings(self, *args):
        sender = self.sender_input.text.strip()
        password = self.password_input.text.strip()
        receiver = self.receiver_input.text.strip()

        if not sender or not password or not receiver:
            show_notification("All fields are required.", title="Incomplete", error=True)
            return
        if "@" not in sender or "@" not in receiver:
            show_notification("Please enter valid email addresses.", title="Invalid Email", error=True)
            return

        try:
            EMAIL_FILE.write_text(
                f"{sender}\n{password}\n{receiver}",
                encoding="utf-8"
            )
            show_notification("Email settings saved successfully.", title="Saved")
        except OSError as e:
            show_notification(f"Failed to save:\n{e}", title="Error", error=True)

    def _load_settings(self):
        try:
            if EMAIL_FILE.exists():
                lines = EMAIL_FILE.read_text(encoding="utf-8").splitlines()
                if len(lines) >= 1:
                    self.sender_input.text = lines[0]
                if len(lines) >= 2:
                    self.password_input.text = lines[1]
                if len(lines) >= 3:
                    self.receiver_input.text = lines[2]
        except Exception:
            pass

    def _apply_theme(self, *args):
        pass


class AboutPanel(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", padding=dp(24), spacing=dp(20), **kwargs)
        self._build_ui()
        theme.register(self._apply_theme)

    def _build_ui(self):
        title = ThemedLabel(
            text="About Shutdown Guard",
            font_size=sp(22),
            bold=True,
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(40)
        )
        title.bind(size=title.setter("text_size"))
        self.add_widget(title)

        card = StyledCard(size_hint_y=None, height=dp(340))
        inner = BoxLayout(orientation="vertical", padding=dp(24), spacing=dp(16))

        items = [
            ("Application", "Shutdown Guard"),
            ("Version", "2.0.0"),
            ("Author", "Niproot"),
            ("Website", "niproot.freehost.io"),
            ("GitHub", "github.com/niproot"),
            ("License", "MIT"),
            ("Description", "Cross-platform PC shutdown scheduler with voice alerts and email notifications."),
        ]
        for key, val in items:
            row = BoxLayout(size_hint_y=None, height=dp(30), spacing=dp(12))
            k = ThemedLabel(
                text=key,
                is_subtext=True,
                font_size=sp(13),
                halign="left",
                valign="middle",
                size_hint_x=0.32
            )
            k.bind(size=k.setter("text_size"))
            v = ThemedLabel(
                text=val,
                font_size=sp(13),
                halign="left",
                valign="middle",
                size_hint_x=0.68
            )
            v.bind(size=v.setter("text_size"))
            row.add_widget(k)
            row.add_widget(v)
            inner.add_widget(row)

        card.add_widget(inner)
        self.add_widget(card)
        self.add_widget(Widget())

    def _apply_theme(self, *args):
        pass


class Sidebar(BoxLayout):
    def __init__(self, on_navigate, **kwargs):
        super().__init__(orientation="vertical", size_hint_x=None, width=dp(220), **kwargs)
        self._on_navigate = on_navigate
        self._items = {}
        self._build()
        theme.register(self._apply_theme)

    def _build(self):
        self.padding = [dp(12), dp(20), dp(12), dp(20)]
        self.spacing = dp(4)

        with self.canvas.before:
            self._bg_color = Color(*theme.surface)
            self._bg_rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_bg, size=self._update_bg)

        app_title = ThemedLabel(
            text="Shutdown Guard",
            font_size=sp(16),
            bold=True,
            size_hint_y=None,
            height=dp(48),
            halign="left",
            valign="middle"
        )
        app_title.bind(size=app_title.setter("text_size"))
        self.add_widget(app_title)

        sep = Widget(size_hint_y=None, height=dp(1))
        with sep.canvas:
            Color(*theme.border)
            Rectangle(pos=sep.pos, size=sep.size)
        self.add_widget(sep)
        self.add_widget(Widget(size_hint_y=None, height=dp(8)))

        nav_items = [
            ("System Info", "📊"),
            ("Shutdown Time", "⏰"),
            ("Email Settings", "✉"),
            ("About", "ℹ"),
        ]
        for label, icon in nav_items:
            item = SidebarItem(label=label, icon_text=icon, on_select=self._select)
            self._items[label] = item
            self.add_widget(item)

        self.add_widget(Widget())

        self.theme_btn = AnimatedButton(
            text="☀ Light Mode" if theme.dark_mode else "☾ Dark Mode",
            size_hint=(1, None),
            height=dp(44),
            font_size=sp(13),
            color=theme.subtext
        )
        self.theme_btn.bind(on_release=self._toggle_theme)
        self.add_widget(self.theme_btn)

        if self._items:
            first = list(self._items.keys())[0]
            self._items[first].set_selected(True)

    def _update_bg(self, *args):
        self._bg_rect.pos = self.pos
        self._bg_rect.size = self.size

    def _select(self, label):
        for k, item in self._items.items():
            item.set_selected(k == label)
        self._on_navigate(label)

    def _toggle_theme(self, *args):
        theme.toggle()
        self.theme_btn.text = "☀ Light Mode" if theme.dark_mode else "☾ Dark Mode"

    def _apply_theme(self, *args):
        self._bg_color.rgba = theme.surface
        self.theme_btn.color = theme.subtext


class ContentArea(FloatLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._panels = {}
        self._current = None

        panels_def = {
            "System Info": SystemInfoPanel,
            "Shutdown Time": ShutdownPanel,
            "Email Settings": EmailPanel,
            "About": AboutPanel,
        }
        for name, cls in panels_def.items():
            panel = cls(size_hint=(1, 1), pos_hint={"x": 0, "y": 0})
            panel.opacity = 0
            self._panels[name] = panel
            self.add_widget(panel)

        self.bind(pos=self._update_bg, size=self._update_bg)
        with self.canvas.before:
            self._bg_color = Color(*theme.bg)
            self._bg_rect = Rectangle(pos=self.pos, size=self.size)
        theme.register(self._apply_theme)

    def _update_bg(self, *args):
        self._bg_rect.pos = self.pos
        self._bg_rect.size = self.size

    def navigate(self, name):
        if self._current:
            old = self._panels.get(self._current)
            if old:
                Animation(opacity=0, duration=0.12, t="out_quad").start(old)
        self._current = name
        new = self._panels.get(name)
        if new:
            Clock.schedule_once(lambda dt: Animation(opacity=1, duration=0.18, t="out_quad").start(new), 0.1)

    def show_initial(self, name):
        self._current = name
        panel = self._panels.get(name)
        if panel:
            panel.opacity = 1

    def _apply_theme(self, *args):
        self._bg_color.rgba = theme.bg


class RootLayout(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="horizontal", **kwargs)
        self._content_area = ContentArea()
        self._sidebar = Sidebar(on_navigate=self._content_area.navigate)
        self.add_widget(self._sidebar)

        divider = Widget(size_hint_x=None, width=dp(1))
        with divider.canvas:
            Color(*theme.border)
            Rectangle(pos=divider.pos, size=divider.size)
        theme.register(lambda *a: divider.canvas.clear() or divider.canvas.__enter__())
        self.add_widget(divider)

        self.add_widget(self._content_area)
        self._content_area.show_initial("System Info")

        with self.canvas.before:
            self._bg = Color(*theme.bg)
            self._bg_rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._upd, size=self._upd)
        theme.register(lambda *a: setattr(self._bg, "rgba", theme.bg))

    def _upd(self, *args):
        self._bg_rect.pos = self.pos
        self._bg_rect.size = self.size


class ShutdownGuardApp(App):
    def build(self):
        self.title = "Shutdown Guard"
        Window.clearcolor = theme.bg
        theme.register(lambda: setattr(Window, "clearcolor", theme.bg))
        safe_tts("Welcome to Shutdown Guard")
        return RootLayout()

    def on_stop(self):
        pass


if __name__ == "__main__":
    ShutdownGuardApp().run()
