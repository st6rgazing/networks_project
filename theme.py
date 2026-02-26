# theme - colors and widgets for the gui. has dark and light mode

import tkinter as tk
from tkinter import ttk
import sys

# pick fonts based on os
if sys.platform == "darwin":
    _UI = "SF Pro Display"
    _MONO = "SF Mono"
elif sys.platform == "win32":
    _UI = "Segoe UI"
    _MONO = "Cascadia Code"
else:
    _UI = "DejaVu Sans"
    _MONO = "DejaVu Sans Mono"

# color palettes
_PALETTES = {
    "dark": {
        "bg": "#1c1c1e",
        "bg2": "#2c2c2e",
        "bg3": "#3a3a3c",
        "card": "#2c2c2e",
        "card_border": "#3a3a3c",
        "input_bg": "#3a3a3c",
        "text": "#ffffff",
        "text2": "#d8d8e0",
        "text3": "#b8b8c0",
        "text4": "#90909c",
        "sep": "#38383a",
        "blue": "#0a84ff",
        "blue_hover": "#409cff",
        "blue_sel": "#2a5a9e",
        "blue_sel2": "#3a6aae",
        "green": "#30d158",
        "red": "#ff453a",
        "yellow": "#ffd60a",
        "teal": "#5ac8fa",
        "teal_sel": "#2a7a9e",
        "teal_btn": "#2a7a9e",
        "teal_btn_hover": "#3a8aae",
        "violet": "#bf5af2",
        "orange": "#ff9f0a",
        "orange_sel": "#8b6b2a",
        "shadow": "#373737",
        "tag": "#1a5bb3",
        "grey": "#1e1e21",
        "grey_hover": "#2a2a2e",
    },
    "light": {
        "bg": "#f2f2f7",
        "bg2": "#ffffff",
        "bg3": "#f2f2f7",
        "card": "#ffffff",
        "card_border": "#e5e5ea",
        "input_bg": "#f2f2f7",
        "text": "#1c1c1e",
        "text2": "#5c5c64",
        "text3": "#787882",
        "text4": "#94949e",
        "sep": "#c6c6c8",
        "blue": "#007aff",
        "blue_hover": "#0066d6",
        "blue_sel": "#99c8ff",
        "blue_sel2": "#b3d4ff",
        "green": "#34c759",
        "red": "#ff3b30",
        "yellow": "#ff9500",
        "teal": "#32ade6",
        "teal_sel": "#5ab8e6",
        "teal_btn": "#32ade6",
        "teal_btn_hover": "#5ab8e6",
        "violet": "#af52de",
        "orange": "#ff9500",
        "orange_sel": "#c48440",
        "shadow": "#e8e8ec",
        "tag": "#0055c4",
        "grey": "#a8a8ac",
        "grey_hover": "#909096",
    },
}

_mode = "dark"
_listeners = []
_ttk_style = None


def current():
    return _PALETTES[_mode]


def is_dark():
    return _mode == "dark"


def register(callback):
    _listeners.append(callback)


def unregister(callback):
    if callback in _listeners:
        _listeners.remove(callback)


def toggle():
    global _mode
    if _mode == "light":
        _mode = "dark"
    else:
        _mode = "light"
    _apply_ttk()
    for cb in _listeners[:]:
        try:
            cb()
        except Exception:
            pass


def _apply_ttk():
    if _ttk_style is None:
        return
    c = current()
    _ttk_style.configure(".", background=c["bg"], foreground=c["text"],
        troughcolor=c["bg3"], selectbackground=c["blue"],
        selectforeground="#ffffff", relief="flat")
    _ttk_style.configure("Treeview", background=c["card"], foreground=c["text"],
        fieldbackground=c["card"], borderwidth=0, rowheight=28, font=(_UI, 10))
    _ttk_style.configure("Treeview.Heading", background=c["bg3"], foreground=c["text2"],
        font=(_UI, 9), relief="flat", padding=(8, 5))
    _ttk_style.map("Treeview", background=[("selected", c["blue_sel"])],
        foreground=[("selected", c["blue"])])
    _ttk_style.configure("TScrollbar", background=c["bg3"], troughcolor=c["bg"],
        arrowcolor=c["text3"], gripcount=0, relief="flat", borderwidth=0, width=10)
    _ttk_style.map("TScrollbar", background=[("active", c["text4"])])


def init_style(root):
    global _ttk_style
    s = ttk.Style(root)
    s.theme_use("clam")
    _ttk_style = s
    _apply_ttk()


def font(size=13, weight="normal", family=None):
    if family is None:
        family = _UI
    return (family, size, weight)


def mono(size=11):
    return (_MONO, size)


def make_window(title, w=760, h=720):
    root = tk.Tk()
    root.title(title)
    c = current()
    root.configure(bg=c["bg"])
    root.geometry(str(w) + "x" + str(h))
    root.minsize(600, 500)
    init_style(root)
    return root


def section_label(parent, text, bg_level="bg"):
    c = current()
    lbl = tk.Label(parent, text=text, font=font(11, "bold"),
        fg=c["text3"], bg=c[bg_level], anchor="w")
    lbl._bg_level = bg_level
    lbl._fg_level = "text3"
    lbl.pack(anchor="w", pady=(18, 6))
    register(lambda w=lbl: w.configure(bg=current()[w._bg_level], fg=current()[w._fg_level]))
    return lbl


def card(parent, padx=16, pady=12, bg_level="card"):
    c = current()
    outer = tk.Frame(parent, bg=c["card_border"], bd=0)
    outer._level = "card_border"
    inner = tk.Frame(outer, bg=c[bg_level], padx=padx, pady=pady)
    inner._level = bg_level
    inner.pack(fill="both", expand=True, padx=1, pady=1)
    outer.pack(fill="x")
    register(lambda o=outer, i=inner: (
        o.configure(bg=current()["card_border"]),
        i.configure(bg=current()[bg_level])))
    return inner


class _MacButtonWrapper:
    # wraps Frame+Label so it quacks like a Button (state, config)
    def __init__(self, frame, label, accent, hover_key, command):
        self._frame = frame
        self._label = label
        self._accent = accent
        self._hover_key = hover_key
        self._command = command
        self._state = "normal"
        self._disabled_bg = None
        self._disabled_fg = None

    def __getitem__(self, key):
        if key == "state":
            return self._state
        return self._frame[key]

    def config(self, **kwargs):
        if "state" in kwargs:
            self._state = kwargs.pop("state")
            if self._state == "disabled":
                c = current()
                self._disabled_bg = c["bg3"]
                self._disabled_fg = c["text"]
                self._frame.configure(bg=self._disabled_bg)
                self._label.configure(bg=self._disabled_bg, fg=self._disabled_fg, cursor="")
                self._frame.unbind("<Button-1>")
                self._label.unbind("<Button-1>")
                self._frame.unbind("<Enter>")
                self._label.unbind("<Enter>")
                self._frame.unbind("<Leave>")
                self._label.unbind("<Leave>")
            else:
                self._apply_accent_colors()
                self._rebind()
        if "bg" in kwargs:
            self._disabled_bg = kwargs.pop("bg")
            if self._state == "disabled":
                self._frame.configure(bg=self._disabled_bg)
                self._label.configure(bg=self._disabled_bg)
        if "fg" in kwargs:
            self._disabled_fg = kwargs.pop("fg")
            if self._state == "disabled":
                self._label.configure(fg=self._disabled_fg)
        if "width" in kwargs:
            w = kwargs.pop("width")
            self._label.configure(width=w)
        if kwargs:
            self._frame.configure(**kwargs)

    def _apply_accent_colors(self):
        cc = current()
        nc = cc[self._accent]
        fg = "#ffffff" if is_dark() else "#000000"
        self._frame.configure(bg=nc)
        self._label.configure(bg=nc, fg=fg, cursor="hand2")

    def _rebind(self):
        def _click(e):
            if self._command and self._state == "normal":
                self._command()

        def _enter(e):
            if self._state == "normal":
                cc = current()
                h = cc.get(self._hover_key, cc[self._accent])
                self._frame.configure(bg=h)
                self._label.configure(bg=h)

        def _leave(e):
            cc = current()
            nc = cc[self._accent]
            self._frame.configure(bg=nc)
            self._label.configure(bg=nc)

        for w in (self._frame, self._label):
            w.bind("<Button-1>", _click)
            w.bind("<Enter>", _enter)
            w.bind("<Leave>", _leave)

    def pack(self, **kwargs):
        return self._frame.pack(**kwargs)

    def place(self, **kwargs):
        return self._frame.place(**kwargs)

    def grid(self, **kwargs):
        return self._frame.grid(**kwargs)


def _mac_accent_btn(parent, text, accent, command, padx, pady):
    # on macOS tk.Button ignores bg; use Frame+Label instead (Labels respect bg)
    c = current()
    hover = accent + "_hover"
    if is_dark():
        fg = "#ffffff"
    else:
        fg = "#000000"
    bg_color = c[accent]
    f = tk.Frame(parent, bg=bg_color)
    lbl = tk.Label(f, text=text, bg=bg_color, fg=fg, font=font(13, "bold"),
        cursor="hand2", padx=padx, pady=pady)
    lbl.pack()

    wrapper = _MacButtonWrapper(f, lbl, accent, hover, command)

    def _click(e):
        if command and wrapper._state == "normal":
            command()

    def _enter(e):
        if wrapper._state == "normal":
            cc = current()
            h = cc.get(hover, cc[accent])
            f.configure(bg=h)
            lbl.configure(bg=h)

    def _leave(e):
        if wrapper._state == "normal":
            cc = current()
            nc = cc[accent]
            f.configure(bg=nc)
            lbl.configure(bg=nc)

    for w in (f, lbl):
        w.bind("<Button-1>", _click)
        w.bind("<Enter>", _enter)
        w.bind("<Leave>", _leave)

    def _repaint():
        if wrapper._state == "disabled":
            cc = current()
            f.configure(bg=cc["bg3"])
            lbl.configure(bg=cc["bg3"], fg=cc["text"])
        else:
            cc = current()
            nc = cc[accent]
            fg_color = "#ffffff" if is_dark() else "#000000"
            f.configure(bg=nc)
            lbl.configure(bg=nc, fg=fg_color)

    register(_repaint)
    return wrapper


def _mac_ghost_btn(parent, text, command, padx, pady):
    c = current()
    bg_color = c["bg3"]
    f = tk.Frame(parent, bg=bg_color)
    lbl = tk.Label(f, text=text, bg=bg_color, fg=c["text"], font=font(12),
        cursor="hand2", padx=padx, pady=pady)
    lbl.pack()

    def _click(e):
        if command:
            command()

    def _enter(e):
        cc = current()
        f.configure(bg=cc["sep"])
        lbl.configure(bg=cc["sep"])

    def _leave(e):
        cc = current()
        nc = cc["bg3"]
        f.configure(bg=nc)
        lbl.configure(bg=nc)

    for w in (f, lbl):
        w.bind("<Button-1>", _click)
        w.bind("<Enter>", _enter)
        w.bind("<Leave>", _leave)

    register(lambda: (f.configure(bg=current()["bg3"]), lbl.configure(bg=current()["bg3"], fg=current()["text"])))
    return f


def accent_button(parent, text, accent="blue", command=None, padx=20, pady=8):
    if sys.platform == "darwin":
        return _mac_accent_btn(parent, text, accent, command, padx, pady)
    c = current()
    hover = accent + "_hover"
    if is_dark():
        fg = "#ffffff"
    else:
        fg = "#000000"
    active_fg = fg
    hover_color = c.get(hover, c[accent])
    btn = tk.Button(parent, text=text, font=font(13, "bold"),
        bg=c[accent], fg=fg, activebackground=hover_color, activeforeground=active_fg,
        relief="flat", cursor="hand2", bd=0, padx=padx, pady=pady, command=command,
        highlightthickness=0, highlightbackground=c[accent])
    btn._is_accent = True
    btn._accent_key = accent
    def _repaint(b=btn):
        cc = current()
        if is_dark():
            fg_color = "#ffffff"
        else:
            fg_color = "#000000"
        accent_color = cc[b._accent_key]
        b.configure(bg=accent_color, fg=fg_color,
            activebackground=cc.get(b._accent_key + "_hover", accent_color),
            activeforeground=fg_color, highlightbackground=accent_color)
    register(_repaint)
    return btn


def ghost_button(parent, text, command=None, padx=14, pady=6):
    if sys.platform == "darwin":
        return _mac_ghost_btn(parent, text, command, padx, pady)
    c = current()
    btn = tk.Button(parent, text=text, font=font(12),
        bg=c["bg3"], fg=c["text"], activebackground=c["sep"], activeforeground=c["text"],
        relief="flat", cursor="hand2", bd=0, padx=padx, pady=pady, command=command,
        highlightthickness=0, highlightbackground=c["bg3"])
    btn._is_ghost = True
    register(lambda b=btn: b.configure(bg=current()["bg3"], fg=current()["text"],
        activebackground=current()["sep"], activeforeground=current()["text"],
        highlightbackground=current()["bg3"]))
    return btn


def icon_btn(parent, text, command=None):
    c = current()
    btn = tk.Button(parent, text=text, font=font(12),
        bg=c["bg"], fg=c["text2"], activebackground=c["bg3"], activeforeground=c["text"],
        relief="flat", cursor="hand2", bd=0, padx=8, pady=4, command=command)
    btn._is_icon_btn = True
    register(lambda b=btn: b.configure(bg=current()["bg"], fg=current()["text2"],
        activebackground=current()["bg3"], activeforeground=current()["text"]))
    return btn


def styled_entry(parent, var, width=20, accent="blue"):
    c = current()
    e = tk.Entry(parent, textvariable=var, width=width,
        bg=c["input_bg"], fg=c["text"], insertbackground=c[accent],
        relief="flat", font=font(12), highlightthickness=1,
        highlightbackground=c["sep"], highlightcolor=c[accent])
    register(lambda w=e: w.configure(bg=current()["input_bg"], fg=current()["text"],
        insertbackground=current()[accent], highlightbackground=current()["sep"],
        highlightcolor=current()[accent]))
    return e


def segmented_control(parent, labels, on_select, accent="blue"):
    c = current()
    outer = tk.Frame(parent, bg=c["bg3"], bd=0)
    outer._level = "bg3"
    inner = tk.Frame(outer, bg=c["bg3"], padx=2, pady=2)
    inner._level = "bg3"
    inner.pack()
    btns = []
    for i in range(len(labels)):
        lbl = labels[i]
        def make_click(idx):
            def _click():
                for b in btns:
                    b.configure(bg=c["bg3"], fg=c["text"])
                btns[idx].configure(bg=c["card"], fg=c["text"])
                on_select(idx)
            return _click
        btn = tk.Button(inner, text=lbl, font=font(12),
            bg=c["bg3"], fg=c["text"], activebackground=c["sep"], activeforeground=c["text"],
            relief="flat", cursor="hand2", bd=0, padx=16, pady=8)
        btn.configure(command=make_click(i))
        btn.pack(side="left", padx=1)
        btns.append(btn)
    btns[0].configure(bg=c["card"], fg=c["text"])
    register(lambda: [b.configure(bg=current()["bg3"], fg=current()["text"]) for b in btns])
    return outer, btns


def divider(parent, bg_level="bg", pady=10):
    c = current()
    sep = tk.Frame(parent, bg=c["sep"], height=1)
    sep._level = "sep"
    sep.pack(fill="x", pady=pady)
    register(lambda w=sep: w.configure(bg=current()["sep"]))
    return sep


def log_widget(parent):
    c = current()
    outer = tk.Frame(parent, bg=c["sep"], bd=0)
    outer._level = "sep"
    outer.pack(fill="both", expand=True, pady=(0, 0))
    inner = tk.Frame(outer, bg=c["card"])
    inner._level = "card"
    inner.pack(fill="both", expand=True, padx=1, pady=1)
    txt = tk.Text(inner, bg=c["card"], fg=c["text2"], font=mono(11),
        relief="flat", bd=0, state="disabled",
        selectbackground=c["blue_sel2"], insertbackground=c["blue"],
        spacing1=1, spacing3=1, padx=14, pady=10, wrap="word")
    sb = ttk.Scrollbar(inner, orient="vertical", command=txt.yview)
    txt.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y")
    txt.pack(side="left", fill="both", expand=True)
    txt.tag_configure("ts", foreground=c["text4"])
    txt.tag_configure("ok", foreground=c["green"])
    txt.tag_configure("err", foreground=c["red"])
    txt.tag_configure("info", foreground=c["text3"])
    txt.tag_configure("hi", foreground=c["blue"])
    def _repaint_log():
        cc = current()
        txt.configure(bg=cc["card"], fg=cc["text2"],
            selectbackground=cc["blue_sel2"], insertbackground=cc["blue"])
        txt.tag_configure("ts", foreground=cc["text4"])
        txt.tag_configure("ok", foreground=cc["green"])
        txt.tag_configure("err", foreground=cc["red"])
        txt.tag_configure("info", foreground=cc["text3"])
        txt.tag_configure("hi", foreground=cc["blue"])
        outer.configure(bg=cc["sep"])
        inner.configure(bg=cc["card"])
    register(_repaint_log)
    return txt


def append_log(widget, line, root=None):
    import datetime
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    lo = line.lower()
    tag = "info"
    if "error" in lo or "fail" in lo or "mismatch" in lo:
        tag = "err"
    elif "✓" in line or "✅" in line or "success" in lo:
        tag = "ok"
    elif "→" in line or "chunk" in lo or "register" in lo or "fetch" in lo or "push" in lo:
        tag = "hi"
    def _do():
        widget.config(state="normal")
        widget.insert("end", ts + "  ", "ts")
        widget.insert("end", line + "\n", tag)
        widget.see("end")
        widget.config(state="disabled")
    if root:
        root.after(0, _do)
    else:
        _do()


def make_tree(parent, columns, widths, height=6):
    c = current()
    outer = tk.Frame(parent, bg=c["sep"], bd=0)
    outer._level = "sep"
    outer.pack(fill="x", pady=(0, 2))
    tree = ttk.Treeview(outer, columns=columns, show="headings",
        height=height, style="Treeview", selectmode="browse")
    sb = ttk.Scrollbar(outer, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    for i in range(len(columns)):
        col = columns[i]
        w = widths[i]
        tree.heading(col, text=col.replace("_", " ").title())
        tree.column(col, width=w, anchor="w", minwidth=30)
    sb.pack(side="right", fill="y", padx=(0, 1), pady=1)
    tree.pack(side="left", fill="both", expand=True, padx=(1, 0), pady=1)
    register(lambda: _apply_ttk())
    register(lambda w=outer: w.configure(bg=current()["sep"]))
    return tree


class ProgressBar:
    def __init__(self, parent, accent="blue", height=4):
        c = current()
        self._accent = accent
        self._pct = 0.0
        self._track = tk.Frame(parent, bg=c["bg3"], height=height)
        self._track.pack(fill="x")
        self._track._level = "bg3"
        self._track.pack_propagate(False)
        self._fill = tk.Frame(self._track, bg=c[accent], height=height)
        self._fill.place(x=0, y=0, relheight=1, relwidth=0)
        self._lbl = tk.Label(parent, text="Ready", font=font(11), fg=c["text3"], bg=c["bg"], anchor="w")
        self._lbl.pack(fill="x", pady=(3, 0))
        self._lbl._bg_level = "bg"
        self._lbl._fg_level = "text3"
        register(self._repaint)

    def _repaint(self):
        c = current()
        self._track.configure(bg=c["bg3"])
        self._fill.configure(bg=c[self._accent])
        self._lbl.configure(bg=c["bg"], fg=c["text3"])

    def set(self, pct, msg="", root=None):
        def _do():
            self._pct = pct
            w = min(pct / 100, 1.0)
            self._fill.place(relwidth=w)
            c = current()
            if pct >= 100:
                fg = c["green"]
            elif "error" in msg.lower():
                fg = c["red"]
            else:
                fg = c["text3"]
            self._lbl.configure(text=msg or "Ready", fg=fg)
        if root:
            root.after(0, _do)
        else:
            _do()


class ToggleSwitch(tk.Canvas):
    W = 44
    H = 26

    def __init__(self, parent, on_toggle=None, **kw):
        c = current()
        super().__init__(parent, width=self.W, height=self.H,
            bg=c["bg"], highlightthickness=0, cursor="hand2", **kw)
        self._bg_level = "bg"
        self._on_toggle = on_toggle
        self._state = is_dark()
        self._draw()
        self.bind("<Button-1>", self._click)
        register(self._on_theme_change)

    def _draw(self):
        c = current()
        self.delete("all")
        if not self._state:
            col = c["blue"]
        else:
            col = c["bg3"]
        r = self.H // 2
        self.create_oval(0, 0, self.H, self.H, fill=col, outline="")
        self.create_oval(self.W - self.H, 0, self.W, self.H, fill=col, outline="")
        self.create_rectangle(r, 0, self.W - r, self.H, fill=col, outline="")
        pad = 3
        if not self._state:
            x = self.W - self.H + pad
        else:
            x = pad
        self.create_oval(x, pad, x + self.H - 2 * pad, self.H - pad, fill="white", outline="")
        self.configure(bg=c["bg"])

    def _click(self, _):
        self._state = not self._state
        toggle()
        if self._on_toggle:
            self._on_toggle(self._state)
        self._draw()

    def _on_theme_change(self):
        self._state = is_dark()
        self._draw()


def top_bar(root, title, subtitle, accent="blue"):
    c = current()
    bar = tk.Frame(root, bg=c["bg2"], pady=0)
    bar._level = "bg2"
    bar.pack(fill="x")
    dot_frame = tk.Frame(bar, bg=c["bg2"], width=4)
    dot_frame._level = "bg2"
    dot_frame.pack(side="left", fill="y")
    dot = tk.Frame(dot_frame, bg=c[accent], width=4)
    dot.pack(fill="y")
    register(lambda d=dot, f=dot_frame: (
        d.configure(bg=current()[accent]),
        f.configure(bg=current()["bg2"])))
    text_frame = tk.Frame(bar, bg=c["bg2"], padx=20, pady=16)
    text_frame._level = "bg2"
    text_frame.pack(side="left", fill="both", expand=True)
    t = tk.Label(text_frame, text=title, font=font(18, "bold"),
        fg=c["text"], bg=c["bg2"], anchor="w")
    t._bg_level = "bg2"
    t._fg_level = "text"
    t.pack(anchor="w")
    s = tk.Label(text_frame, text=subtitle, font=font(12),
        fg=c["text3"], bg=c["bg2"], anchor="w")
    s._bg_level = "bg2"
    s._fg_level = "text3"
    s.pack(anchor="w")
    register(lambda: (
        bar.configure(bg=current()["bg2"]),
        text_frame.configure(bg=current()["bg2"]),
        t.configure(bg=current()["bg2"], fg=current()["text"]),
        s.configure(bg=current()["bg2"], fg=current()["text3"])))
    right = tk.Frame(bar, bg=c["bg2"], padx=20)
    right._level = "bg2"
    right.pack(side="right", fill="y")
    register(lambda f=right: f.configure(bg=current()["bg2"]))
    moon = tk.Label(right, text="🌙", bg=c["bg2"], font=font(13))
    moon._bg_level = "bg2"
    moon._fg_level = "text3"
    moon.pack(side="left", padx=(0, 6))
    register(lambda w=moon: w.configure(bg=current()["bg2"]))
    ToggleSwitch(right).pack(side="left", pady=16)
    sun = tk.Label(right, text="☀️", bg=c["bg2"], font=font(13))
    sun._bg_level = "bg2"
    sun._fg_level = "text3"
    sun.pack(side="left", padx=(6, 0))
    register(lambda w=sun: w.configure(bg=current()["bg2"]))
    bdr = tk.Frame(root, bg=c["sep"], height=1)
    bdr._level = "sep"
    bdr.pack(fill="x")
    register(lambda w=bdr: w.configure(bg=current()["sep"]))
    return bar


def scroll_frame(parent):
    c = current()
    canvas = tk.Canvas(parent, bg=c["bg"], highlightthickness=0, bd=0, yscrollincrement=1)
    canvas._bg_level = "bg"
    sb = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    inner = tk.Frame(canvas, bg=c["bg"])
    inner._level = "bg"
    win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

    def _on_configure(e):
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _on_canvas_resize(e):
        canvas.itemconfig(win_id, width=e.width)

    inner.bind("<Configure>", _on_configure)
    canvas.bind("<Configure>", _on_canvas_resize)

    def _scroll_mouse(e):
        if sys.platform == "darwin":
            amt = int(-1 * e.delta)
            if amt == 0:
                amt = -1 if e.delta > 0 else 1
            amt = max(-15, min(15, amt))
        else:
            amt = int(-1 * (e.delta / 120)) * 12
        canvas.yview_scroll(amt, "units")

    def _scroll_linux_up(e):
        canvas.yview_scroll(-12, "units")
    def _scroll_linux_down(e):
        canvas.yview_scroll(12, "units")

    def _scroll_bind(e):
        canvas.bind_all("<MouseWheel>", _scroll_mouse)
        if sys.platform.startswith("linux"):
            canvas.bind_all("<Button-4>", _scroll_linux_up)
            canvas.bind_all("<Button-5>", _scroll_linux_down)
    def _scroll_unbind(e):
        canvas.unbind_all("<MouseWheel>")
        if sys.platform.startswith("linux"):
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")
    canvas.bind("<Enter>", _scroll_bind)
    canvas.bind("<Leave>", _scroll_unbind)
    inner.bind("<Enter>", _scroll_bind)
    inner.bind("<Leave>", _scroll_unbind)

    register(lambda: (
        canvas.configure(bg=current()["bg"]),
        inner.configure(bg=current()["bg"])))
    return inner, canvas


def stat_card(parent, label, color_key="blue"):
    c = current()
    frm = tk.Frame(parent, bg=c["card"], padx=20, pady=14)
    frm._level = "card"
    frm.pack(side="left", padx=(0, 10))
    register(lambda f=frm: f.configure(bg=current()["card"]))
    val = tk.Label(frm, text="0", font=font(28, "bold"), fg=c[color_key], bg=c["card"])
    val._bg_level = "card"
    val.pack()
    register(lambda v=val: v.configure(bg=current()["card"], fg=current()[color_key]))
    lbl = tk.Label(frm, text=label, font=font(10), fg=c["text3"], bg=c["card"])
    lbl._bg_level = "card"
    lbl._fg_level = "text3"
    lbl.pack()
    register(lambda l=lbl: l.configure(bg=current()["card"], fg=current()["text3"]))
    return val


def badge(parent, text, color_key="blue"):
    c = current()
    lbl = tk.Label(parent, text="  " + text + "  ", font=font(10, "bold"),
        fg=c[color_key], bg=c["tag"], padx=4, pady=2)
    lbl._color_key = color_key
    register(lambda w=lbl: w.configure(fg=current()[w._color_key], bg=current()["tag"]))
    return lbl


def field_row(parent, label, var, width=18, accent="blue", bg_level="bg"):
    c = current()
    row = tk.Frame(parent, bg=c[bg_level])
    row._level = bg_level
    row.pack(fill="x", pady=3)
    register(lambda f=row: f.configure(bg=current()[f._level]))
    lbl = tk.Label(row, text=label, font=font(12),
        fg=c["text3"], bg=c[bg_level], width=16, anchor="w")
    lbl._bg_level = bg_level
    lbl._fg_level = "text3"
    lbl.pack(side="left", padx=(0, 8))
    register(lambda w=lbl: w.configure(bg=current()[w._bg_level], fg=current()[w._fg_level]))
    e = styled_entry(row, var, width=width, accent=accent)
    e.pack(side="left", ipady=5)
    return e


# this is used by _repaint_widget to update colors when theme changes
def _repaint_widget(w):
    c = current()
    cls = w.__class__.__name__
    try:
        if cls in ("Frame", "ThemeFrame"):
            lvl = getattr(w, "_level", "bg")
            w.configure(bg=c[lvl])
        elif cls == "Label":
            lvl = getattr(w, "_bg_level", "bg")
            fg_lvl = getattr(w, "_fg_level", "text")
            w.configure(bg=c[lvl], fg=c[fg_lvl])
        elif cls == "Button":
            if getattr(w, "_is_accent", False):
                accent = getattr(w, "_accent_key", "blue")
                if is_dark():
                    fg_accent = "#ffffff"
                else:
                    fg_accent = "#000000"
                hover_key = accent + "_hover"
                if hover_key in c:
                    hover_color = c[hover_key]
                else:
                    hover_color = c[accent]
                w.configure(bg=c[accent], fg=fg_accent,
                    activebackground=hover_color, activeforeground=fg_accent)
            elif getattr(w, "_is_ghost", False):
                w.configure(bg=c["bg3"], fg=c["text"],
                    activebackground=c["sep"], activeforeground=c["text"])
            elif getattr(w, "_is_icon_btn", False):
                w.configure(bg=c["bg"], fg=c["text2"],
                    activebackground=c["bg3"], activeforeground=c["text"])
            else:
                lvl = getattr(w, "_bg_level", "bg")
                w.configure(bg=c[lvl], fg=c["text"])
        elif cls == "Entry":
            w.configure(bg=c["input_bg"], fg=c["text"],
                insertbackground=c["blue"], highlightbackground=c["sep"],
                highlightcolor=c["blue"])
        elif cls in ("Text", "ScrolledText"):
            w.configure(bg=c["card"], fg=c["text2"], insertbackground=c["blue"])
        elif cls == "Listbox":
            w.configure(bg=c["card"], fg=c["text"],
                selectbackground=c["blue_sel"], selectforeground=c["blue"])
        elif cls == "Canvas":
            lvl = getattr(w, "_bg_level", "card")
            w.configure(bg=c[lvl])
    except Exception:
        pass
    for child in w.winfo_children():
        _repaint_widget(child)
