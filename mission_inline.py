"""Embed a live skills panel in Rebellion's native Create Mission window."""
from __future__ import annotations

import argparse
import ctypes as C
from ctypes import wintypes as W
import os

from mission_data import MISSION_BY_NAME, PlannerError, evaluate, load_tables
from mission_live import LiveReader
from mission_setup import SetupReader

CLASS_NAME = "RebellionOverhaulMissionSkills_v1"
STOP_MESSAGE = 0x8001


def member_lines(setup, roster, tables, index):
    """Keep unsupported and conditional readings distinct in the tiny native UI."""
    key, role = setup.members[index % len(setup.members)]
    c = roster.get(key & 0xFFFFFF)
    if not c or c.family != key >> 24:
        return (f"Special force ({role.lower()})" if key >> 24 == 0x3C else "Character unavailable",
                "Skills not available", "Roll: unknown", "")
    name = f"{c.name} ({role.lower()})"
    if role == "Decoy":
        return name, f"ESP {c.espionage}", "Decoy: no mission-success roll", "Defender odds unknown"
    mission = MISSION_BY_NAME.get(setup.mission)
    if mission is None:
        return name, "Skills not supported for this mission", "Roll: unknown", ""
    roll = evaluate(c, mission, tables, setup.context, role)
    if mission.skill == "combined":
        skills = f"ESP {c.espionage}  COM {c.combat}"
    else:
        labels = {"diplomacy": "DIP", "espionage": "ESP", "combat": "COM",
                  "leadership": "LEAD", "ship_design": "SHIP", "troop_training": "TROOP",
                  "facility_design": "FACILITY"}
        skills = f"{labels[mission.skill]} {getattr(c, mission.skill)}"
    if roll.percent is not None:
        odds = f"Agent roll: {roll.percent}%  (score {roll.score})"
        detail = "Per-agent roll; excludes interception"
    elif mission.table is None:
        odds, detail = "Research odds not implemented", "Current capability shown above"
    elif any(setup.context.get(field) is None for field in mission.context):
        odds, detail = "Roll: unknown target information", "Missing inputs are not treated as zero"
    else:
        odds, detail = "Roll unavailable", "Check mission eligibility in the game"
    return name, skills, odds, detail


def rgb(r, g, b):
    return r | (g << 8) | (b << 16)


class NativePanel:
    def __init__(self):
        if os.name != "nt":
            raise PlannerError("The embedded panel requires Windows")
        self.user = C.WinDLL("user32", use_last_error=True)
        self.gdi = C.WinDLL("gdi32", use_last_error=True)
        self.kernel = C.WinDLL("kernel32", use_last_error=True)
        self.live = None
        self.panel = self.controller = None
        self.setup = None
        self.roster = {}
        self.index = 0
        self.mouse_down = False
        self.saved_lists = {}
        self.failure = None
        self.bind()
        self.font = self.brush = None
        try:
            self.initialize()
        except Exception:
            self.close()
            raise

    def initialize(self):
        self.live = LiveReader()
        self.reader = SetupReader(self.live, lambda hwnd: self.game_window(hwnd, "CoolGameWindow", 12)
                                  and self.user.IsWindowVisible(hwnd))
        self.tables = load_tables(self.live.game)
        self.font = self.gdi.CreateFontW(-11, 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 0, 0, "Tahoma")
        self.brush = self.gdi.CreateSolidBrush(rgb(5, 18, 13))
        if not self.font or not self.brush:
            raise C.WinError(C.get_last_error())
        self.proc = self.proc_type(self.wndproc)
        self.instance = self.kernel.GetModuleHandleW(None)
        wc = self.class_type()
        wc.cbSize, wc.lpfnWndProc, wc.hInstance = C.sizeof(wc), self.proc, self.instance
        wc.lpszClassName = CLASS_NAME
        wc.hCursor = self.user.LoadCursorW(None, C.c_void_p(32512))
        if not self.user.RegisterClassExW(C.byref(wc)):
            raise C.WinError(C.get_last_error())
        self.controller = self.user.CreateWindowExW(0, CLASS_NAME, CLASS_NAME, 0, 0, 0, 0, 0,
                                                     C.c_void_p(-3), None, self.instance, None)
        if not self.controller:
            raise C.WinError(C.get_last_error())
        if not self.user.SetTimer(self.controller, 1, 800, None):
            raise C.WinError(C.get_last_error())
        # Fullscreen Rebellion can capture mouse input and bypass a foreign
        # child HWND. Observe left-button edges only over our visible panel.
        self.mouse_down = bool(self.user.GetAsyncKeyState(1) & 0x8000)
        if not self.user.SetTimer(self.controller, 2, 20, None):
            raise C.WinError(C.get_last_error())

    def bind(self):
        self.proc_type = C.WINFUNCTYPE(C.c_ssize_t, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
        proc_type = self.proc_type
        class WindowClass(C.Structure):
            _fields_ = [("cbSize", W.UINT), ("style", W.UINT), ("lpfnWndProc", proc_type),
                        ("cbClsExtra", C.c_int), ("cbWndExtra", C.c_int), ("hInstance", W.HINSTANCE),
                        ("hIcon", W.HICON), ("hCursor", W.HANDLE), ("hbrBackground", W.HBRUSH),
                        ("lpszMenuName", W.LPCWSTR), ("lpszClassName", W.LPCWSTR), ("hIconSm", W.HICON)]
        class PaintStruct(C.Structure):
            _fields_ = [("hdc", W.HDC), ("erase", W.BOOL), ("rect", W.RECT),
                        ("restore", W.BOOL), ("inc_update", W.BOOL), ("reserved", W.BYTE * 32)]
        self.class_type, self.paint_type = WindowClass, PaintStruct
        signatures = {
            "RegisterClassExW": ([C.POINTER(WindowClass)], W.WORD),
            "CreateWindowExW": ([W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD, C.c_int, C.c_int,
                                  C.c_int, C.c_int, W.HWND, W.HMENU, W.HINSTANCE, C.c_void_p], W.HWND),
            "DefWindowProcW": ([W.HWND, W.UINT, W.WPARAM, W.LPARAM], C.c_ssize_t),
            "DestroyWindow": ([W.HWND], W.BOOL),
            "IsWindow": ([W.HWND], W.BOOL),
            "IsWindowVisible": ([W.HWND], W.BOOL),
            "ShowWindow": ([W.HWND, C.c_int], W.BOOL),
            "GetClassNameW": ([W.HWND, W.LPWSTR, C.c_int], C.c_int),
            "GetDlgCtrlID": ([W.HWND], C.c_int),
            "GetParent": ([W.HWND], W.HWND),
            "GetForegroundWindow": ([], W.HWND),
            "GetAncestor": ([W.HWND, W.UINT], W.HWND),
            "GetAsyncKeyState": ([C.c_int], C.c_short),
            "GetCursorPos": ([C.POINTER(W.POINT)], W.BOOL),
            "ScreenToClient": ([W.HWND, C.POINTER(W.POINT)], W.BOOL),
            "WindowFromPoint": ([W.POINT], W.HWND),
            "GetWindowThreadProcessId": ([W.HWND, C.POINTER(W.DWORD)], W.DWORD),
            "GetClientRect": ([W.HWND, C.POINTER(W.RECT)], W.BOOL),
            "GetWindowRect": ([W.HWND, C.POINTER(W.RECT)], W.BOOL),
            "MapWindowPoints": ([W.HWND, W.HWND, C.c_void_p, W.UINT], C.c_int),
            "SetWindowPos": ([W.HWND, W.HWND, C.c_int, C.c_int, C.c_int, C.c_int, W.UINT], W.BOOL),
            "InvalidateRect": ([W.HWND, C.POINTER(W.RECT), W.BOOL], W.BOOL),
            "BeginPaint": ([W.HWND, C.POINTER(PaintStruct)], W.HDC),
            "EndPaint": ([W.HWND, C.POINTER(PaintStruct)], W.BOOL),
            "FillRect": ([W.HDC, C.POINTER(W.RECT), W.HBRUSH], C.c_int),
            "DrawTextW": ([W.HDC, W.LPCWSTR, C.c_int, C.POINTER(W.RECT), W.UINT], C.c_int),
            "LoadCursorW": ([W.HINSTANCE, C.c_void_p], W.HANDLE),
            "SetTimer": ([W.HWND, C.c_size_t, W.UINT, C.c_void_p], C.c_size_t),
            "KillTimer": ([W.HWND, C.c_size_t], W.BOOL),
            "GetMessageW": ([C.POINTER(W.MSG), W.HWND, W.UINT, W.UINT], W.BOOL),
            "TranslateMessage": ([C.POINTER(W.MSG)], W.BOOL),
            "DispatchMessageW": ([C.POINTER(W.MSG)], C.c_ssize_t),
            "PostQuitMessage": ([C.c_int], None),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.user, name)
            function.argtypes, function.restype = args, result
        self.kernel.GetModuleHandleW.argtypes = [W.LPCWSTR]
        self.kernel.GetModuleHandleW.restype = W.HMODULE
        for name, args, result in (
            ("CreateFontW", [C.c_int] * 5 + [W.DWORD] * 8 + [W.LPCWSTR], W.HFONT),
            ("CreateSolidBrush", [W.DWORD], W.HBRUSH),
            ("DeleteObject", [W.HGDIOBJ], W.BOOL),
            ("SelectObject", [W.HDC, W.HGDIOBJ], W.HGDIOBJ),
            ("SetTextColor", [W.HDC, W.DWORD], W.DWORD),
            ("SetBkMode", [W.HDC, C.c_int], C.c_int),
        ):
            function = getattr(self.gdi, name)
            function.argtypes, function.restype = args, result

    def game_window(self, hwnd, class_name=None, control_id=None, parent=None):
        if not hwnd or not self.user.IsWindow(hwnd):
            return False
        pid = W.DWORD()
        self.user.GetWindowThreadProcessId(hwnd, C.byref(pid))
        if pid.value != self.live.pid:
            return False
        name = C.create_unicode_buffer(128)
        self.user.GetClassNameW(hwnd, name, len(name))
        return ((class_name is None or name.value == class_name)
                and (control_id is None or self.user.GetDlgCtrlID(hwnd) == control_id)
                and (parent is None or self.user.GetParent(hwnd) == parent))

    def restore_lists(self):
        for hwnd, (parent, control_id, rect) in self.saved_lists.items():
            if self.game_window(hwnd, "CoolDragList", control_id, parent):
                self.user.SetWindowPos(hwnd, None, *rect, 0x4014)
        self.saved_lists.clear()

    def detach(self):
        self.restore_lists()
        if self.panel and self.user.IsWindow(self.panel):
            self.user.DestroyWindow(self.panel)
        self.panel = None
        self.setup = None
        self.roster = {}

    def update(self):
        try:
            campaign = self.live.session()
            setup = self.reader.find()
            if (setup is None or not self.game_window(setup.hwnd, "CoolGameWindow", 12)
                    or not self.user.IsWindowVisible(setup.hwnd)):
                self.detach()
                return
            if self.setup is None or self.setup.hwnd != setup.hwnd:
                self.detach()
                self.index = 0
                self.panel = self.user.CreateWindowExW(0, CLASS_NAME, "Mission skills", 0x40000000,
                                                       35, 83, 200, 89, setup.hwnd, 0x7B01,
                                                       self.instance, None)
                if not self.panel:
                    raise C.WinError(C.get_last_error())
            if self.setup is None or self.setup.members != setup.members:
                self.index = 0
            self.setup = setup
            self.failure = None
            snapshot = self.live.snapshot()
            if snapshot.campaign != campaign or self.reader.find() != setup:
                raise PlannerError("Mission setup changed during refresh")
            self.roster = {c.id: c for c in snapshot.characters}
            if setup.page in (0, 151):
                self.restore_lists()
                rect = (35, 83, 200, 89)
            elif setup.page == 152:
                # The game's custom scrolling assumes the original list height.
                # Compact lists need no scrollbar; larger teams keep the original
                # layout and can inspect every member on the Mission tab instead.
                if any(sum(role == r for _, role in setup.members) > 2 for r in ("Agent", "Decoy")):
                    self.restore_lists()
                    self.user.ShowWindow(self.panel, 0)
                    return
                for hwnd, control_id in ((setup.agent_hwnd, 200), (setup.decoy_hwnd, 201)):
                    if not self.game_window(hwnd, "CoolDragList", control_id, setup.hwnd):
                        raise PlannerError("Mission list window changed")
                    if hwnd not in self.saved_lists:
                        original = W.RECT()
                        self.user.GetWindowRect(hwnd, C.byref(original))
                        self.user.MapWindowPoints(None, setup.hwnd, C.byref(original), 2)
                        self.saved_lists[hwnd] = (setup.hwnd, control_id,
                                                 (original.left, original.top,
                                                  original.right-original.left, original.bottom-original.top))
                        x, y, w, _ = self.saved_lists[hwnd][2]
                        if not self.user.SetWindowPos(hwnd, None, x, y, w, 140, 0x4014):
                            raise C.WinError(C.get_last_error())
                rect = (8, 240, 236, 75)
            else:
                raise PlannerError("Unsupported mission page")
            if not self.user.SetWindowPos(self.panel, None, *rect, 0x0050):  # show, no activation
                raise C.WinError(C.get_last_error())
            self.user.InvalidateRect(self.panel, None, False)
        except (OSError, ValueError) as error:
            self.failure = str(error)
            self.detach()
            code = W.DWORD()
            if not self.live.k.GetExitCodeProcess(self.live.handle, C.byref(code)) or code.value != 259:
                self.user.PostQuitMessage(0)

    def text(self, dc, value, x, y, width, color=0xE2EFE2, height=14):
        self.gdi.SetTextColor(dc, color)
        rect = W.RECT(x, y, x + width, y + height)
        self.user.DrawTextW(dc, value, -1, C.byref(rect), 0x8820)  # single line, no prefix, ellipsis

    def paint(self, hwnd):
        ps, rect = self.paint_type(), W.RECT()
        dc = self.user.BeginPaint(hwnd, C.byref(ps))
        old_font = None
        try:
            self.user.GetClientRect(hwnd, C.byref(rect))
            width, height = rect.right, rect.bottom
            self.user.FillRect(dc, C.byref(rect), self.brush)
            old_font = self.gdi.SelectObject(dc, self.font)
            self.gdi.SetBkMode(dc, 1)
            setup = self.setup
            if not setup:
                return
            self.index %= len(setup.members)
            self.text(dc, "LIVE SKILLS", 5, 2, 85, rgb(110, 255, 145))
            self.text(dc, f"< {self.index+1}/{len(setup.members)} >", width-81, 2, 65)
            self.text(dc, "x", width-12, 2, 10)
            name, skills, odds, detail = member_lines(setup, self.roster, self.tables, self.index)
            self.text(dc, name, 5, 17, width-10)
            self.text(dc, skills, 5, 32, width-10)
            self.text(dc, odds, 5, 45, width-10, rgb(245, 220, 145))
            if height >= 75:
                self.text(dc, detail, 5, 60, width-10, rgb(150, 185, 160))
        finally:
            if old_font:
                self.gdi.SelectObject(dc, old_font)
            self.user.EndPaint(hwnd, C.byref(ps))

    def pointer(self):
        """Consume no input: act only on a fresh press over our foreground child."""
        state = self.user.GetAsyncKeyState(1)
        down = bool(state & 0x8000)
        pressed = bool(state & 0x8001) and not self.mouse_down
        self.mouse_down = down
        if not pressed or not self.panel or not self.user.IsWindowVisible(self.panel):
            return
        if self.user.GetForegroundWindow() != self.user.GetAncestor(self.panel, 2):
            return
        point, rect = W.POINT(), W.RECT()
        if not self.user.GetCursorPos(C.byref(point)) or self.user.WindowFromPoint(point) != self.panel:
            return
        if not self.user.ScreenToClient(self.panel, C.byref(point)):
            return
        self.user.GetClientRect(self.panel, C.byref(rect))
        if 0 <= point.y < 17 and rect.right-23 <= point.x < rect.right:
            self.user.PostQuitMessage(0)
        elif 0 <= point.y < 17 and rect.right-90 <= point.x < rect.right-23:
            self.index += -1 if point.x < rect.right-55 else 1
            self.user.InvalidateRect(self.panel, None, False)

    def wndproc(self, hwnd, message, wparam, lparam):
        try:
            if message == STOP_MESSAGE:
                self.user.PostQuitMessage(0)
                return 0
            if message == 0x113 and hwnd == self.controller:
                if wparam == 1:
                    self.update()
                elif wparam == 2:
                    self.pointer()
                return 0
            if message == 0x0F and hwnd == self.panel:
                self.paint(hwnd)
                return 0
            if message == 0x14:  # erase background
                return 1
            if message == 0x21:  # prevent this informational child stealing focus
                return 3
            if message in (0x201, 0x202) and hwnd == self.panel:
                self.pointer()
                return 0
            if message == 0x20A and hwnd == self.panel:
                self.index += -1 if C.c_short(wparam >> 16).value > 0 else 1
                self.user.InvalidateRect(hwnd, None, False)
                return 0
        except Exception as error:
            self.failure = str(error)
            self.user.PostQuitMessage(1)
        return self.user.DefWindowProcW(hwnd, message, wparam, lparam)

    def run(self):
        try:
            message = W.MSG()
            while (result := self.user.GetMessageW(C.byref(message), None, 0, 0)) > 0:
                self.user.TranslateMessage(C.byref(message))
                self.user.DispatchMessageW(C.byref(message))
            if result < 0:
                raise C.WinError(C.get_last_error())
            if message.wParam and self.failure:
                raise PlannerError(self.failure)
            return int(message.wParam)
        finally:
            self.close()

    def close(self):
        self.detach()
        if self.controller:
            self.user.KillTimer(self.controller, 1)
            self.user.KillTimer(self.controller, 2)
            self.user.DestroyWindow(self.controller)
            self.controller = None
        if self.font:
            self.gdi.DeleteObject(self.font)
            self.font = None
        if self.brush:
            self.gdi.DeleteObject(self.brush)
            self.brush = None
        if self.live:
            self.live.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stop", action="store_true", help="Stop the embedded panel and restore list sizes")
    args = parser.parse_args(argv)
    if os.name != "nt":
        parser.error("Windows is required")
    user = C.WinDLL("user32", use_last_error=True)
    user.FindWindowExW.argtypes = [W.HWND, W.HWND, W.LPCWSTR, W.LPCWSTR]
    user.FindWindowExW.restype = W.HWND
    user.PostMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
    user.PostMessageW.restype = W.BOOL
    existing = user.FindWindowExW(C.c_void_p(-3), None, CLASS_NAME, CLASS_NAME)
    if existing:
        if args.stop:
            user.PostMessageW(existing, STOP_MESSAGE, 0, 0)
        return 0
    if args.stop:
        return 0
    try:
        app = NativePanel()
        return app.run()
    except (OSError, ValueError) as error:
        user.MessageBoxW.argtypes = [W.HWND, W.LPCWSTR, W.LPCWSTR, W.UINT]
        user.MessageBoxW(None, str(error), "Rebellion mission panel", 0x10)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
