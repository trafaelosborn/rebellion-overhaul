"""Live mission-planning companion for Star Wars Rebellion (Windows)."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import ctypes as C
from ctypes import wintypes as W
from datetime import datetime
import os
from pathlib import Path
import tkinter as tk
from tkinter import ttk

from mission_data import (MISSIONS, MISSION_BY_NAME, PlannerError, evaluate,
                          load_tables, skill_score, team_warnings)
from mission_live import LiveReader


def place_window(root):
    """Prefer a monitor that still has room when the game switches to 640x480."""
    width, height, x, y = 1160, 760, 20, 20
    if os.name == "nt":
        class MonitorInfo(C.Structure):
            _fields_ = [("size", W.DWORD), ("monitor", W.RECT), ("work", W.RECT), ("flags", W.DWORD)]
        monitors = []
        user = C.WinDLL("user32")
        callback_type = C.WINFUNCTYPE(W.BOOL, C.c_void_p, C.c_void_p, C.POINTER(W.RECT), C.c_ssize_t)
        user.GetMonitorInfoW.argtypes = [C.c_void_p, C.POINTER(MonitorInfo)]
        user.GetMonitorInfoW.restype = W.BOOL
        user.EnumDisplayMonitors.argtypes = [C.c_void_p, C.c_void_p, callback_type, C.c_ssize_t]
        user.EnumDisplayMonitors.restype = W.BOOL
        def visit(handle, _dc, _rect, _data):
            info = MonitorInfo()
            info.size = C.sizeof(info)
            if user.GetMonitorInfoW(handle, C.byref(info)):
                r = info.work
                monitors.append((r.left, r.top, r.right - r.left, r.bottom - r.top))
            return True
        user.EnumDisplayMonitors(None, None, callback_type(visit), 0)
        usable = [m for m in monitors if m[2] >= 1000 and m[3] >= 720]
        if usable:
            left, top, available_w, available_h = max(usable, key=lambda m: m[2] * m[3])
            width, height = min(width, available_w - 40), min(height, available_h - 60)
            x, y = left + (available_w - width) // 2, top + (available_h - height) // 2
    # Tk negative geometry values mean distance from the far edge, not absolute
    # screen coordinates. Set the position through SetWindowPos for left monitors.
    root.geometry(f"{width}x{height}+20+20")
    root.update_idletasks()
    if os.name == "nt":
        user.GetAncestor.argtypes = [W.HWND, W.UINT]
        user.GetAncestor.restype = W.HWND
        user.SetWindowPos.argtypes = [W.HWND, W.HWND, C.c_int, C.c_int, C.c_int, C.c_int, W.UINT]
        user.SetWindowPos.restype = W.BOOL
        hwnd = user.GetAncestor(root.winfo_id(), 2)
        user.SetWindowPos(hwnd, None, x, y, 0, 0, 0x0015)  # NOSIZE | NOZORDER | NOACTIVATE


class Planner:
    def __init__(self, root: tk.Tk, game: Path | None):
        self.root, self.game = root, game
        self.reader = None
        self.future = None
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rebellion-reader")
        self.characters, self.tables, self.roles = {}, {}, {}
        self.campaign = None
        self.closed = False
        self.mission = tk.StringVar(value="Espionage")
        self.connection = tk.StringVar(value="Start Rebellion, load your campaign, then connect.")
        self.formula = tk.StringVar()
        self.detail = tk.StringVar(value="Select a character to inspect the calculation.")
        self.summary = tk.StringVar(value="Select characters above, then add them as agents or decoys.")
        self.auto = tk.BooleanVar(value=True)
        self.topmost = tk.BooleanVar(value=False)
        self.context = {k: tk.StringVar() for k in ("support", "stormtroopers", "target_combat")}
        self.build()
        place_window(root)
        self.change_mission()
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(150, self.refresh)
        root.after(2500, self.tick)

    def build(self):
        root = self.root
        root.title("Rebellion • Mission Planner")
        root.minsize(980, 680)
        root.configure(bg="#101923")
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure(".", background="#101923", foreground="#e5edf6", font=("Segoe UI", 10))
        style.configure("TButton", padding=(12, 7), background="#263c50", borderwidth=0)
        style.map("TButton", background=[("active", "#375770"), ("disabled", "#18232e")])
        style.configure("TCombobox", fieldbackground="#203143", foreground="#f5f8fc", padding=5)
        style.map("TCombobox", fieldbackground=[("readonly", "#203143")],
                  foreground=[("readonly", "#f5f8fc")])
        style.configure("TEntry", fieldbackground="#203143", foreground="#f5f8fc", padding=5)
        style.map("TEntry", fieldbackground=[("disabled", "#15212c")], foreground=[("disabled", "#586c7e")])
        style.configure("Treeview", background="#152332", fieldbackground="#152332",
                        foreground="#e5edf6", rowheight=30, borderwidth=0)
        style.configure("Treeview.Heading", background="#22364a", foreground="#b9cedf",
                        padding=(6, 8), font=("Segoe UI", 9, "bold"))
        style.map("Treeview", background=[("selected", "#245569")], foreground=[("selected", "#ffffff")])
        frame = ttk.Frame(root, padding=20)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(5, weight=3)
        frame.rowconfigure(9, weight=1)
        header = ttk.Frame(frame)
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(header, text="MISSION PLANNER", font=("Segoe UI", 22, "bold"), foreground="#6bdcc6").pack(side="left")
        ttk.Checkbutton(header, text="Keep on top", variable=self.topmost,
                        command=lambda: root.attributes("-topmost", self.topmost.get())).pack(side="right")
        ttk.Label(frame, text="Current campaign skills • Plan here, issue orders in Rebellion",
                  foreground="#9fb2c5").grid(row=1, column=0, sticky="w", pady=(2, 14))
        connect = ttk.Frame(frame)
        connect.grid(row=2, column=0, sticky="ew", pady=(0, 14))
        self.refresh_button = ttk.Button(connect, text="Connect / refresh", command=self.refresh)
        self.refresh_button.pack(side="left")
        ttk.Checkbutton(connect, text="Auto refresh", variable=self.auto).pack(side="left", padx=12)
        ttk.Label(connect, textvariable=self.connection, foreground="#9fb2c5", wraplength=760).pack(side="left", padx=8)
        setup = ttk.Frame(frame)
        setup.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(setup, text="Mission").pack(side="left", padx=(0, 8))
        picker = ttk.Combobox(setup, textvariable=self.mission, values=[m.name for m in MISSIONS],
                              state="readonly", width=23)
        picker.pack(side="left", padx=(0, 16))
        picker.bind("<<ComboboxSelected>>", self.change_mission)
        self.context_entries = {}
        for key, label in (("support", "Our support %"), ("stormtroopers", "Stormtroopers"),
                           ("target_combat", "Target Combat")):
            ttk.Label(setup, text=label).pack(side="left", padx=(0, 5))
            entry = ttk.Entry(setup, textvariable=self.context[key], width=5)
            entry.pack(side="left", padx=(0, 12))
            self.context_entries[key] = entry
            self.context[key].trace_add("write", lambda *_: self.render())
        ttk.Label(frame, textvariable=self.formula, foreground="#9fb2c5", wraplength=1080).grid(
            row=4, column=0, sticky="w", pady=(0, 10))
        self.roster = self.tree(frame, ("name", "rating", "dip", "esp", "combat", "lead", "odds", "location", "status"),
                                ("Character", "Mission skill", "Dip", "Esp", "Combat", "Lead", "Agent roll", "Attached to", "Status"),
                                (185, 85, 45, 45, 60, 45, 80, 155, 135), 5)
        self.roster.bind("<<TreeviewSelect>>", self.describe)
        actions = ttk.Frame(frame)
        actions.grid(row=6, column=0, sticky="ew", pady=(10, 8))
        ttk.Button(actions, text="+ Agent", command=lambda: self.assign("Agent")).pack(side="left")
        ttk.Button(actions, text="+ Decoy", command=lambda: self.assign("Decoy")).pack(side="left", padx=8)
        ttk.Button(actions, text="Remove selected", command=self.remove).pack(side="left")
        ttk.Button(actions, text="Clear team", command=self.clear).pack(side="left", padx=8)
        ttk.Label(actions, text="Tip: Ctrl-click to select several characters.", foreground="#9fb2c5").pack(side="right")
        ttk.Label(frame, textvariable=self.detail, wraplength=1080, foreground="#c8d9e9").grid(
            row=7, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(frame, text="PROPOSED TEAM", font=("Segoe UI", 11, "bold"), foreground="#6bdcc6").grid(
            row=8, column=0, sticky="w", pady=(0, 8))
        self.team = self.tree(frame, ("name", "role", "rating", "odds", "note"),
                              ("Character", "Role", "Relevant skill", "Agent roll", "Readiness / calculation"),
                              (185, 80, 100, 80, 420), 9, height=4)
        ttk.Label(frame, textvariable=self.summary, wraplength=1080, foreground="#e7c28a").grid(
            row=10, column=0, sticky="ew", pady=(9, 9))
        ttk.Label(frame, text="AGENT ROLL ≠ OVERALL SUCCESS. Conditional on reaching resolution. "
                  "Detection, capture, travel, decoys, and final mission effects are not included.\n"
                  "Target fields are your inputs; leave unknown information blank. "
                  "Skills refresh from the game; team selections here do not change it.",
                  foreground="#9fb2c5", wraplength=1080, font=("Segoe UI", 9)).grid(row=11, column=0, sticky="ew")

    @staticmethod
    def tree(frame, columns, labels, widths, row, height=7):
        holder = ttk.Frame(frame)
        holder.grid(row=row, column=0, sticky="nsew")
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)
        tree = ttk.Treeview(holder, columns=columns, show="headings", height=height, selectmode="extended")
        for column, label, width in zip(columns, labels, widths):
            tree.heading(column, text=label)
            tree.column(column, width=width, minwidth=40, anchor="w" if column in ("name", "location", "status", "note") else "center")
        tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(holder, orient="vertical", command=tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=scrollbar.set)
        return tree

    def context_values(self):
        values = {}
        for key in MISSION_BY_NAME[self.mission.get()].context:
            text = self.context[key].get().strip()
            if not text:
                values[key] = None
            else:
                try:
                    value = int(text)
                except ValueError as error:
                    raise PlannerError(f"{key.replace('_', ' ')} must be a whole number, or blank") from error
                if not 0 <= value <= (100 if key == "support" else 32767):
                    raise PlannerError(f"{key.replace('_', ' ')} is outside its allowed range")
                values[key] = value
        return values

    def change_mission(self, *_):
        mission = MISSION_BY_NAME[self.mission.get()]
        for key, entry in self.context_entries.items():
            entry.configure(state="normal" if key in mission.context else "disabled")
        self.formula.set(mission.formula + ".  Ranked by current relevant skill. "
                         "Support means support for YOUR faction; Stormtroopers means regiment count.")
        self.render()

    def render(self):
        selected = self.roster.selection()
        team_selected = self.team.selection()
        roster_scroll, team_scroll = self.roster.yview()[0], self.team.yview()[0]
        mission = MISSION_BY_NAME[self.mission.get()]
        error = None
        try:
            context = self.context_values()
        except PlannerError as exc:
            context, error = {}, str(exc)
        for tree in (self.roster, self.team):
            tree.delete(*tree.get_children())
        for c in sorted(self.characters.values(), key=lambda c: (-skill_score(c, mission), c.name)):
            roll = evaluate(c, mission, self.tables, context)
            odds = f"{roll.percent}%" if roll.percent is not None and not error else "—"
            self.roster.insert("", "end", iid=str(c.id), values=(c.name, skill_score(c, mission),
                               c.diplomacy, c.espionage, c.combat, c.leadership, odds, c.location, c.status))
        for ident, role in self.roles.items():
            c = self.characters.get(ident)
            if c is None:
                continue
            roll = evaluate(c, mission, self.tables, context, role)
            odds = f"{roll.percent}%" if roll.percent is not None and not error else "—"
            note = c.status if roll.percent is not None else roll.explanation
            self.team.insert("", "end", iid=str(ident), values=(c.name, role,
                             c.espionage if role == "Decoy" else skill_score(c, mission), odds, error or note))
        self.roster.selection_set([i for i in selected if self.roster.exists(i)])
        self.team.selection_set([i for i in team_selected if self.team.exists(i)])
        self.roster.yview_moveto(roster_scroll)
        self.team.yview_moveto(team_scroll)
        members = [self.characters[i] for i in self.roles if i in self.characters]
        if error:
            self.summary.set(error)
        elif members:
            agents = sum(self.roles[c.id] == "Agent" for c in members)
            warnings = team_warnings(members)
            if not agents:
                warnings.insert(0, "A mission needs at least one agent.")
            self.summary.set(f"{agents} agent(s) · {len(members) - agents} decoy(s). " + " ".join(warnings))
        else:
            self.summary.set("Select characters above, then add them as agents or decoys.")
        self.describe()

    def describe(self, *_):
        selection = self.roster.selection()
        if not selection:
            self.detail.set("Select a character to inspect the calculation.")
            return
        c = self.characters.get(int(selection[0]))
        if c is None:
            return
        try:
            roll = evaluate(c, MISSION_BY_NAME[self.mission.get()], self.tables, self.context_values())
            self.detail.set(f"{c.name}: {roll.explanation}")
        except PlannerError as error:
            self.detail.set(str(error))

    def assign(self, role):
        for ident in self.roster.selection():
            self.roles[int(ident)] = role
        self.render()

    def remove(self):
        for ident in self.team.selection():
            self.roles.pop(int(ident), None)
        self.render()

    def clear(self):
        self.roles.clear()
        self.render()

    def refresh_job(self):
        try:
            if self.reader is None:
                self.reader = LiveReader(self.game)
            tables = load_tables(self.reader.game)
            return self.reader.snapshot(), tables
        except Exception:
            if self.reader is not None:
                self.reader.close()
                self.reader = None
            raise

    def refresh(self):
        if self.closed or self.future is not None:
            return
        self.refresh_button.configure(state="disabled")
        self.future = self.pool.submit(self.refresh_job)
        self.root.after(100, self.poll)

    def poll(self):
        if self.closed:
            return
        if not self.future.done():
            self.root.after(100, self.poll)
            return
        try:
            snapshot, self.tables = self.future.result()
            if self.campaign != snapshot.campaign:
                self.roles.clear()
                for value in self.context.values():
                    value.set("")
            self.campaign = snapshot.campaign
            self.characters = {c.id: c for c in snapshot.characters}
            self.roles = {i: r for i, r in self.roles.items() if i in self.characters}
            side = "Alliance" if snapshot.side == 1 else "Empire"
            self.connection.set(f"LIVE · {side} · {len(self.characters)} characters · {datetime.now():%H:%M:%S}")
        except Exception as error:
            self.characters, self.tables = {}, {}
            self.roles.clear()
            self.campaign = None
            self.connection.set(f"Not connected · {error}")
        finally:
            self.future = None
            self.refresh_button.configure(state="normal")
            self.render()

    def tick(self):
        if not self.closed:
            if self.auto.get():
                self.refresh()
            self.root.after(2500, self.tick)

    def close(self):
        self.closed = True
        def cleanup():
            if self.reader:
                self.reader.close()
        self.pool.submit(cleanup)
        self.pool.shutdown(wait=False)
        self.root.destroy()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path, help="Optional installation check; otherwise use the running game")
    parser.add_argument("--snapshot", action="store_true", help="Print the current player roster, then exit")
    args = parser.parse_args(argv)
    if args.snapshot:
        try:
            with LiveReader(args.game) as reader:
                snapshot = reader.snapshot()
                print("Alliance" if snapshot.side == 1 else "Empire")
                for c in snapshot.characters:
                    print(f"{c.name}: Dip {c.diplomacy}, Esp {c.espionage}, Combat {c.combat}, "
                          f"Lead {c.leadership} | {c.location} | {c.status}")
            return 0
        except (OSError, ValueError) as error:
            print(f"Cannot read campaign: {error}")
            return 1
    root = tk.Tk()
    Planner(root, args.game)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
