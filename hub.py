# hub - tracker + peers + sender all in one window
# this is the main app that combines everything so you dont need 3 separate windows

import socket
import threading
import argparse
import os
import hashlib

import tkinter as tk
from tkinter import filedialog, messagebox

from utils import chunk_file, make_metadata, send_json, recv_json, send_bytes, recv_bytes
import theme as T

# we need the tracker module to run the tracker server and get its stats
import tracker as tracker_mod

# where we store chunks that peers receive (filename -> chunk_index -> data)
chunk_store = {}
# lock so multiple threads dont mess up the chunk_store at same time
store_lock = threading.Lock()
# refs to root window and log widget - needed for appending to log from threads
_root = None
_logw = None
# which peer ports are currently running
_running_peers = {}
_running_lock = threading.Lock()
# port -> socket, so we can close it to stop a peer
_peer_sockets = {}


def log(msg):
    # print to console and also add to the gui log if we have one
    print("[HUB] " + str(msg))
    if _logw and _root:
        T.append_log(_logw, msg, _root)


# handles when someone connects to a peer - either sender storing a chunk or receiver getting one
def handle_peer_client(conn, addr):
    log("Connection from " + str(addr[0]) + ":" + str(addr[1]))
    try:
        # keep reading messages until connection closes
        while True:
            msg = recv_json(conn)
            if not msg:
                break
            t = msg.get("type")
            # sender is pushing a chunk to us
            if t == "STORE_CHUNK":
                fn = msg["filename"]
                idx = int(msg["chunk_index"])
                data = recv_bytes(conn)
                # verify the hash matches so we know data isnt corrupted
                ah = hashlib.sha256(data).hexdigest()
                if ah != msg["hash"]:
                    send_json(conn, {"status": "error", "reason": "Hash mismatch"})
                    log("Hash mismatch chunk " + str(idx) + " of " + fn)
                    continue
                # add to our storage
                with store_lock:
                    if fn not in chunk_store:
                        chunk_store[fn] = {}
                    chunk_store[fn][idx] = {"data": data, "hash": ah}
                log("Stored chunk " + str(idx) + " of " + fn + " (" + str(len(data)) + " B)")
                send_json(conn, {"status": "ok"})
            # receiver is asking for a chunk
            elif t == "GET_CHUNK":
                fn = msg["filename"]
                idx = int(msg["chunk_index"])
                with store_lock:
                    chunk = None
                    if fn in chunk_store and idx in chunk_store[fn]:
                        chunk = chunk_store[fn][idx]
                if chunk is None:
                    send_json(conn, {"status": "error", "reason": "Chunk " + str(idx) + " not found"})
                else:
                    # send the chunk data back
                    send_json(conn, {"status": "ok", "hash": chunk["hash"]})
                    send_bytes(conn, chunk["data"])
                    log("Served chunk " + str(idx) + " of " + fn)
            else:
                # unknown message type
                send_json(conn, {"error": "unknown"})
    except Exception as e:
        log("Error: " + str(e))
    finally:
        conn.close()


# starts a peer server that listens for connections - runs in its own thread
def run_peer_server(host, port, peer_id):
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(20)
    with _running_lock:
        _running_peers[port] = True
        _peer_sockets[port] = srv
    log("Peer " + peer_id + " listening on " + str(host) + ":" + str(port))
    try:
        while True:
            conn, addr = srv.accept()
            t = threading.Thread(target=handle_peer_client, args=(conn, addr), daemon=True)
            t.start()
    finally:
        with _running_lock:
            if port in _running_peers:
                del _running_peers[port]
            if port in _peer_sockets:
                del _peer_sockets[port]


# close a peer's socket so its server thread exits
def stop_peer(port):
    with _running_lock:
        srv = _peer_sockets.get(port)
    if srv:
        try:
            srv.close()
        except Exception:
            pass


# tell the tracker we exist so it can tell receivers where to get chunks from
# th=tracker host, tp=tracker port, pid=peer id, ph=peer host, pp=peer port
def register_with_tracker(th, tp, pid, ph, pp):
    try:
        s = socket.socket()
        s.connect((th, tp))
        send_json(s, {"type": "REGISTER_PEER", "peer_id": pid, "host": ph, "port": pp})
        r = recv_json(s)
        s.close()
        return r.get("status") == "ok"
    except Exception as e:
        log("Tracker registration failed: " + str(e))
        return False


def unregister_with_tracker(th, tp, pid):
    try:
        s = socket.socket()
        s.connect((th, tp))
        send_json(s, {"type": "UNREGISTER_PEER", "peer_id": pid})
        recv_json(s)
        s.close()
    except Exception:
        pass


# quick check if a peer is actually running and accepting connections
def verify_peer(host, port):
    try:
        s = socket.socket()
        s.settimeout(2)
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        return False


# register a file with the tracker before we start sending chunks
def _register_file(th, tp, fn, meta):
    s = socket.socket()
    s.connect((th, tp))
    send_json(s, {"type": "REGISTER_FILE", "filename": fn, "metadata": meta, "peer_id": "sender"})
    r = recv_json(s)
    s.close()
    return r.get("status") == "ok"


# send one chunk to a peer
def _push_chunk(ph, pp, fn, chunk):
    s = socket.socket()
    s.connect((ph, pp))
    send_json(s, {"type": "STORE_CHUNK", "filename": fn,
        "chunk_index": chunk["index"], "hash": chunk["hash"], "size": chunk["size"]})
    send_bytes(s, chunk["data"])
    r = recv_json(s)
    s.close()
    return r.get("status") == "ok"


# tell tracker which peer has which chunk (so receiver knows where to fetch from)
def _reg_chunk(th, tp, fn, idx, pid):
    s = socket.socket()
    s.connect((th, tp))
    send_json(s, {"type": "REGISTER_CHUNK", "filename": fn, "chunk_index": idx, "peer_id": pid})
    r = recv_json(s)
    s.close()
    return r.get("status") == "ok"


# the main gui class - builds all the sections and handles user actions
class HubGUI:
    def __init__(self, root, tracker_host="127.0.0.1", tracker_port=9000):
        global _root, _logw
        self.root = root
        _root = root
        self._filepath = None  # path of file user picked to send
        self._peer_rows = []   # list of (pid_var, host_var, port_var, status_label, start_btn, stop_btn)
        c = T.current()

        # so tracker can write to our log widget
        tracker_mod._root = root

        # top bar with title and dark/light mode toggle
        bar = tk.Frame(root, bg=c["bg2"], pady=0)
        bar._level = "bg2"
        bar.pack(fill="x")

        text_frame = tk.Frame(bar, bg=c["bg2"], padx=28, pady=20)
        text_frame._level = "bg2"
        text_frame.pack(side="left", fill="both", expand=True)

        t = tk.Label(text_frame, text="P2P File Share", font=T.font(20, "bold"),
            fg=c["text"], bg=c["bg2"], anchor="w")
        t._bg_level = "bg2"
        t._fg_level = "text"
        t.pack(anchor="w")
        s = tk.Label(text_frame, text="Tracker · Peers · Send", font=T.font(12),
            fg=c["text3"], bg=c["bg2"], anchor="w")
        s._bg_level = "bg2"
        s._fg_level = "text3"
        s.pack(anchor="w")
        T.register(lambda: (
            bar.configure(bg=T.current()["bg2"]),
            text_frame.configure(bg=T.current()["bg2"]),
            t.configure(bg=T.current()["bg2"], fg=T.current()["text"]),
            s.configure(bg=T.current()["bg2"], fg=T.current()["text3"])))

        right = tk.Frame(bar, bg=c["bg2"], padx=24)
        right._level = "bg2"
        right.pack(side="right", fill="y")
        T.register(lambda f=right: f.configure(bg=T.current()["bg2"]))
        moon = tk.Label(right, text="🌙", bg=c["bg2"], font=T.font(13))
        moon._bg_level = "bg2"
        moon.pack(side="left", padx=(0, 6))
        T.ToggleSwitch(right).pack(side="left", pady=16)
        sun = tk.Label(right, text="☀️", bg=c["bg2"], font=T.font(13))
        sun._bg_level = "bg2"
        sun.pack(side="left", padx=(6, 0))
        T.register(lambda w=moon: w.configure(bg=T.current()["bg2"]))
        T.register(lambda w=sun: w.configure(bg=T.current()["bg2"]))

        # thin line under the header
        sep = tk.Frame(root, bg=c["sep"], height=1)
        sep._level = "sep"
        sep.pack(fill="x")
        T.register(lambda w=sep: w.configure(bg=T.current()["sep"]))

        # scrollable area for all the content
        scroll, self._scroll_canvas = T.scroll_frame(root)

        # tracker host/port - shared between peers section and send section
        self.th_v = tk.StringVar(value=tracker_host)
        self.tp_v = tk.StringVar(value=str(tracker_port))

        # build the 3 main sections
        self._build_tracker_section(scroll, c)
        self._build_peers_section(scroll, c)
        self._build_send_section(scroll, c)

        # activity log at the bottom
        log_wrap = tk.Frame(scroll, bg=c["bg"], padx=28, pady=20)
        log_wrap.pack(fill="both", expand=True)
        T.register(lambda f=log_wrap: f.configure(bg=T.current()["bg"]))
        T.section_label(log_wrap, "Activity")
        _logw = T.log_widget(log_wrap)
        tracker_mod._logw = _logw

        # start the polling loops that update stats and chunk table
        self._poll_stats()
        self._poll_chunks()

    # section 1: start the tracker server and show live stats
    def _build_tracker_section(self, scroll, c):
        wrap = tk.Frame(scroll, bg=c["bg"], padx=28, pady=24)
        wrap.pack(fill="x")
        T.register(lambda f=wrap: f.configure(bg=T.current()["bg"]))

        T.section_label(wrap, "Tracker")
        card = T.card(wrap, padx=20, pady=16)
        card.pack(fill="x")

        # 0.0.0.0 means listen on all interfaces
        self.tracker_host_v = tk.StringVar(value="0.0.0.0")
        self.tracker_port_v = tk.StringVar(value="9000")
        T.field_row(card, "Bind address", self.tracker_host_v, accent="blue", bg_level="card")
        T.field_row(card, "Port", self.tracker_port_v, width=8, accent="blue", bg_level="card")

        T.divider(card, bg_level="card", pady=12)

        # start button and status indicator
        btn_row = tk.Frame(card, bg=c["card"])
        btn_row._level = "card"
        btn_row.pack(fill="x")
        T.register(lambda f=btn_row: f.configure(bg=T.current()["card"]))

        self.tracker_start_btn = T.accent_button(btn_row, "Start Tracker", "grey",
            command=self._start_tracker, padx=20, pady=8)
        self.tracker_start_btn.pack(side="left")

        self.tracker_status = tk.Label(btn_row, text="● Stopped", font=T.font(12, "bold"),
            fg=c["red"], bg=c["card"])
        self.tracker_status._bg_level = "card"
        self.tracker_status.pack(side="left", padx=16)
        T.register(lambda w=self.tracker_status: w.configure(bg=T.current()["card"]))

        # the 3 stat cards that show peers count, files count, chunks count
        stats_row = tk.Frame(card, bg=c["card"])
        stats_row._level = "card"
        stats_row.pack(fill="x", pady=(12, 0))
        T.register(lambda f=stats_row: f.configure(bg=T.current()["card"]))

        self._peers_stat = T.stat_card(stats_row, "Peers", "blue")
        self._files_stat = T.stat_card(stats_row, "Files", "green")
        self._chunks_stat = T.stat_card(stats_row, "Chunks", "text3")

    # section 2: add peers, start them, see stored chunks
    def _build_peers_section(self, scroll, c):
        wrap = tk.Frame(scroll, bg=c["bg"], padx=16, pady=28)
        wrap.pack(fill="x")
        T.register(lambda f=wrap: f.configure(bg=T.current()["bg"]))

        T.section_label(wrap, "Peers")
        card = T.card(wrap, padx=12, pady=16)
        card.pack(fill="x")

        tc = tk.Frame(card, bg=c["card"])
        tc._level = "card"
        tc.pack(fill="x", pady=(0, 12))
        T.register(lambda f=tc: f.configure(bg=T.current()["card"]))
        # where to find the tracker (peers need this to register)
        T.field_row(tc, "Tracker host", self.th_v, accent="teal", bg_level="card")
        T.field_row(tc, "Tracker port", self.tp_v, width=8, accent="teal", bg_level="card")

        T.divider(card, bg_level="card", pady=8)

        # card holds the peer rows - new peers get inserted before _add_peer_row
        self._peers_card = card
        self._add_peer_row = tk.Frame(card, bg=c["card"])
        self._add_peer_row._level = "card"
        self._add_peer_row.pack(fill="x", pady=(8, 0))
        T.register(lambda f=self._add_peer_row: f.configure(bg=T.current()["card"]))

        btn_row = tk.Frame(self._add_peer_row, bg=c["card"])
        btn_row._level = "card"
        btn_row.pack(fill="x")
        T.register(lambda f=btn_row: f.configure(bg=T.current()["card"]))
        T.ghost_button(btn_row, "Add Peer", command=self._on_add_peer).pack(side="left", padx=(0, 10))
        T.accent_button(btn_row, "Start All", "grey", command=self._start_all_peers, padx=24, pady=10).pack(side="left")

        # add 2 default peers to start with
        self._add_peer("peer1", "127.0.0.1", "9001")
        self._add_peer("peer2", "127.0.0.1", "9002")

        T.section_label(wrap, "Stored Chunks")
        # table showing what chunks we have stored (updated by _poll_chunks)
        self.chunk_tree = T.make_tree(wrap, ["filename", "chunk", "size", "hash"],
            [220, 60, 90, 280], height=4)

    # section 3: pick file, verify peers, choose strategy, send
    def _build_send_section(self, scroll, c):
        wrap = tk.Frame(scroll, bg=c["bg"], padx=28, pady=28)
        wrap.pack(fill="x")
        T.register(lambda f=wrap: f.configure(bg=T.current()["bg"]))

        T.section_label(wrap, "Send File")
        card = T.card(wrap, padx=20, pady=16)
        card.pack(fill="x")

        file_row = tk.Frame(card, bg=c["card"])
        file_row._level = "card"
        file_row.pack(fill="x")
        T.register(lambda f=file_row: f.configure(bg=T.current()["card"]))
        # shows selected filename or "No file selected"
        self.file_lbl = tk.Label(file_row, text="No file selected", font=T.font(13),
            fg=c["text3"], bg=c["card"], anchor="w")
        self.file_lbl._bg_level = "card"
        self.file_lbl._fg_level = "text3"
        self.file_lbl.pack(side="left", fill="x", expand=True)
        T.register(lambda w=self.file_lbl: w.configure(
            bg=T.current()["card"], fg=T.current()[w._fg_level]))
        T.ghost_button(file_row, "Choose File…", command=self.browse).pack(side="right")

        T.divider(card, bg_level="card", pady=12)

        # verify button checks if peers are reachable before sending
        verify_row = tk.Frame(card, bg=c["card"])
        verify_row._level = "card"
        verify_row.pack(fill="x")
        T.register(lambda f=verify_row: f.configure(bg=T.current()["card"]))
        T.ghost_button(verify_row, "Verify Peers", command=self._verify_peers).pack(side="left")
        self.verify_lbl = tk.Label(verify_row, text="", font=T.font(12),
            fg=c["text3"], bg=c["card"], anchor="w")
        self.verify_lbl._bg_level = "card"
        self.verify_lbl._fg_level = "text3"
        self.verify_lbl.pack(side="left", padx=12)
        T.register(lambda w=self.verify_lbl: w.configure(bg=T.current()["card"], fg=T.current()["text3"]))

        # shows list of peers with ● or ○ for online/offline
        self.peer_status_frame = tk.Frame(card, bg=c["card"])
        self.peer_status_frame._level = "card"
        self.peer_status_frame.pack(fill="x", pady=(4, 0))
        T.register(lambda f=self.peer_status_frame: f.configure(bg=T.current()["card"]))

        T.divider(card, bg_level="card", pady=12)

        # round-robin = spread chunks across peers, replicate = every peer gets full copy
        strat_row = tk.Frame(card, bg=c["card"])
        strat_row._level = "card"
        strat_row.pack(fill="x")
        T.register(lambda f=strat_row: f.configure(bg=T.current()["card"]))
        self.strategy_var = tk.StringVar(value="round-robin")
        rb1 = tk.Radiobutton(strat_row, text="Round-robin", variable=self.strategy_var, value="round-robin",
            bg=c["card"], fg=c["text"], selectcolor=c["card"],
            activebackground=c["card"], cursor="hand2", bd=0, font=T.font(12))
        rb1.pack(side="left", padx=(0, 20))
        T.register(lambda w=rb1: w.configure(bg=T.current()["card"], fg=T.current()["text"],
            selectcolor=T.current()["card"], activebackground=T.current()["card"]))
        rb2 = tk.Radiobutton(strat_row, text="Replicate all", variable=self.strategy_var, value="replicate-all",
            bg=c["card"], fg=c["text"], selectcolor=c["card"],
            activebackground=c["card"], cursor="hand2", bd=0, font=T.font(12))
        rb2.pack(side="left", padx=(0, 20))
        T.register(lambda w=rb2: w.configure(bg=T.current()["card"], fg=T.current()["text"],
            selectcolor=T.current()["card"], activebackground=T.current()["card"]))

        T.divider(card, bg_level="card", pady=12)

        self.prog = T.ProgressBar(card, accent="teal")
        send_row = tk.Frame(card, bg=c["card"])
        send_row._level = "card"
        send_row.pack(fill="x", pady=(12, 0))
        T.register(lambda f=send_row: f.configure(bg=T.current()["card"]))
        self.send_btn = T.accent_button(send_row, "Send File", "teal_btn",
            command=self.send, padx=24, pady=10)
        self.send_btn.pack(side="left")

    # user clicked Start Tracker - run the tracker server in a background thread
    def _start_tracker(self):
        host = self.tracker_host_v.get().strip()
        port = int(self.tracker_port_v.get().strip())
        self.tracker_start_btn.config(state="disabled", bg=T.current()["bg3"], fg=T.current()["text"])
        t = threading.Thread(target=tracker_mod.run_server, args=(host, port), daemon=True)
        t.start()
        self.tracker_status.config(text="● Running on :" + str(port), fg=T.current()["green"])
        # update the tracker fields in peers/send sections so they point to our tracker
        self.th_v.set("127.0.0.1")
        self.tp_v.set(str(port))
        log("Tracker started")

    # every second update the peer/files/chunks counts from tracker module
    def _poll_stats(self):
        self._peers_stat.config(text=str(len(tracker_mod.peers)))
        self._files_stat.config(text=str(len(tracker_mod.files)))
        n = 0
        for fn in tracker_mod.chunk_owners:
            for idx in tracker_mod.chunk_owners[fn]:
                n = n + len(tracker_mod.chunk_owners[fn][idx])
        self._chunks_stat.config(text=str(n))
        self.root.after(1000, self._poll_stats)

    # add one peer row to the list (ID, host, port, status, start button)
    def _add_peer(self, pid="", ph="127.0.0.1", pp="9003"):
        c = T.current()
        row = tk.Frame(self._peers_card, bg=c["card"], pady=6)
        row._level = "card"
        row.pack(fill="x", before=self._add_peer_row)
        T.register(lambda f=row: f.configure(bg=T.current()["card"]))

        # string vars for the entry fields
        pid_v = tk.StringVar(value=pid)
        ph_v = tk.StringVar(value=ph)
        pp_v = tk.StringVar(value=pp)

        def _lbl(t, w=4):
            l = tk.Label(row, text=t, font=T.font(12), fg=c["text3"], bg=c["card"], width=w, anchor="e")
            l._bg_level = "card"
            l._fg_level = "text3"
            l.pack(side="left", padx=4)
            T.register(lambda w=l: w.configure(bg=T.current()["card"], fg=T.current()["text3"]))

        _lbl("ID", 4)
        T.styled_entry(row, pid_v, width=8, accent="teal").pack(side="left", ipady=5, padx=4)
        _lbl("Host", 4)
        T.styled_entry(row, ph_v, width=12, accent="teal").pack(side="left", ipady=5, padx=4)
        _lbl("Port", 4)
        T.styled_entry(row, pp_v, width=5, accent="teal").pack(side="left", ipady=5, padx=4)

        status_lbl = tk.Label(row, text="● Offline", font=T.font(11), fg=c["red"], bg=c["card"])
        status_lbl._bg_level = "card"
        status_lbl.pack(side="left", padx=6)
        T.register(lambda w=status_lbl: w.configure(bg=T.current()["card"]))

        start_btn = T.accent_button(row, "Start Peer", "grey",
            command=lambda: self._start_one(pid_v, ph_v, pp_v, status_lbl, start_btn, stop_btn),
            padx=24, pady=10)
        start_btn.config(width=12)
        start_btn.pack(side="right", padx=8)

        stop_btn = T.accent_button(row, "Stop Peer", "grey",
            command=lambda: self._stop_one(pid_v, ph_v, pp_v, status_lbl, start_btn, stop_btn),
            padx=24, pady=10)
        stop_btn.config(width=12)
        stop_btn.config(state="disabled", bg=c["bg3"], fg=c["text"])
        stop_btn.pack(side="right", padx=8)

        self._peer_rows.append((pid_v, ph_v, pp_v, status_lbl, start_btn, stop_btn))

    # user clicked Add Peer - add another row with next peer number
    def _on_add_peer(self):
        n = len(self._peer_rows) + 1
        self._add_peer("peer" + str(n), "127.0.0.1", str(9000 + n))
        self.root.update_idletasks()
        self._scroll_canvas.configure(scrollregion=self._scroll_canvas.bbox("all"))
        log("Added peer" + str(n))

    # start a single peer - run server thread and register with tracker
    def _start_one(self, pid_v, ph_v, pp_v, status_lbl, start_btn, stop_btn):
        pid = pid_v.get().strip()
        host = ph_v.get().strip()
        try:
            port = int(pp_v.get().strip())
        except ValueError:
            log("Invalid port")
            return
        th = self.th_v.get().strip()
        tp = int(self.tp_v.get().strip())

        def worker():
            t = threading.Thread(target=run_peer_server, args=(host, port, pid), daemon=True)
            t.start()
            ok = register_with_tracker(th, tp, pid, host, port)

            def update_gui():
                c = T.current()
                if ok:
                    status_lbl.config(text="● Online", fg=c["green"])
                    log("Started " + pid)
                else:
                    status_lbl.config(text="● No tracker", fg=c["yellow"])
                    log(pid + " started but tracker unreachable")
                start_btn.config(state="disabled", bg=c["bg3"], fg=c["text"])
                stop_btn.config(state="normal", bg=c["grey"], fg="#ffffff" if T.is_dark() else "#000000")

            self.root.after(0, update_gui)

        threading.Thread(target=worker, daemon=True).start()

    # stop a single peer - close its socket so the server thread exits
    def _stop_one(self, pid_v, ph_v, pp_v, status_lbl, start_btn, stop_btn):
        pid = pid_v.get().strip()
        try:
            port = int(pp_v.get().strip())
        except ValueError:
            return
        th = self.th_v.get().strip()
        tp = int(self.tp_v.get().strip())
        stop_peer(port)
        unregister_with_tracker(th, tp, pid)
        c = T.current()
        status_lbl.config(text="● Offline", fg=c["red"])
        start_btn.config(state="normal", bg=c["grey"], fg="#ffffff" if T.is_dark() else "#000000")
        stop_btn.config(state="disabled", bg=c["bg3"], fg=c["text"])
        log("Stopped " + pid)

    # start any peer that hasnt been started yet
    def _start_all_peers(self):
        for pid_v, ph_v, pp_v, status_lbl, start_btn, stop_btn in self._peer_rows:
            if start_btn["state"] == "normal":
                self._start_one(pid_v, ph_v, pp_v, status_lbl, start_btn, stop_btn)

    # check which peers are actually online and update the status labels
    def _verify_peers(self):
        peers = []
        for p, h, pp, _, _, _ in self._peer_rows:
            pid = p.get().strip()
            host = h.get().strip()
            port_s = pp.get().strip()
            if pid and host and port_s:
                peers.append((pid, host, port_s))
        if not peers:
            self.verify_lbl.config(text="No peers configured")
            return
        # try to connect to each one
        active = []
        inactive = []
        for pid, host, port_s in peers:
            try:
                port = int(port_s)
                if verify_peer(host, port):
                    active.append(pid)
                else:
                    inactive.append(pid)
            except ValueError:
                inactive.append(pid)
        c = T.current()
        if inactive:
            self.verify_lbl.config(text=str(len(active)) + " active, " + str(len(inactive)) + " offline", fg=c["yellow"])
        else:
            self.verify_lbl.config(text="All " + str(len(active)) + " peers active", fg=c["green"])

        # clear old status labels and add new ones showing each peer
        for widget in self.peer_status_frame.winfo_children():
            widget.destroy()
        for pid, host, port_s in peers:
            try:
                port = int(port_s)
                ok = verify_peer(host, port)
            except ValueError:
                ok = False
            status_char = "●" if ok else "○"
            fg_color = c["green"] if ok else c["text3"]
            lbl = tk.Label(self.peer_status_frame,
                text="  " + pid + " (" + host + ":" + port_s + "): " + status_char,
                font=T.font(11), fg=fg_color, bg=c["card"])
            lbl.pack(anchor="w")
            T.register(lambda w=lbl: w.configure(bg=T.current()["card"]))

    # file picker - user selects which file to send
    def browse(self):
        path = filedialog.askopenfilename(title="Select file to share")
        if path:
            self._filepath = path
            name = os.path.basename(path)
            size = os.path.getsize(path)
            self.file_lbl.config(text=name + "  (" + f"{size:,}" + " bytes)", fg=T.current()["teal"])
            self.file_lbl._fg_level = "teal"
            log("Selected: " + path)

    # user clicked Send - validate then run the send in a background thread
    def send(self):
        if not self._filepath:
            messagebox.showwarning("No file", "Please select a file first.")
            return
        peers = []
        for p, h, pp, _, _, _ in self._peer_rows:
            pid = p.get().strip()
            host = h.get().strip()
            port_s = pp.get().strip()
            if pid and host and port_s:
                peers.append((pid, host, port_s))
        if len(peers) < 2:
            messagebox.showwarning("Too few peers", "At least 2 peers required.")
            return
        # only use peers that are actually online
        active = []
        for pid, h, pp in peers:
            if verify_peer(h, int(pp)):
                active.append((pid, h, int(pp)))
        if len(active) < 2:
            messagebox.showwarning("Peers offline",
                "Only " + str(len(active)) + " peer(s) reachable. Start peers and verify first.")
            return

        self.send_btn.config(state="disabled", bg=T.current()["bg3"], fg=T.current()["text"])
        t = threading.Thread(target=self._worker, args=(active,), daemon=True)
        t.start()

    # does the actual work: chunk file, register with tracker, push each chunk to peers
    def _worker(self, peers_info):
        filepath = self._filepath
        fn = os.path.basename(filepath)
        th = self.th_v.get().strip()
        tp = int(self.tp_v.get().strip())
        strategy = self.strategy_var.get()
        try:
            # step 1: split file into chunks
            self.prog.set(5, "Chunking file…", self.root)
            chunks = chunk_file(filepath)
            log("Created " + str(len(chunks)) + " chunk(s)")

            # step 2: tell tracker about the file
            self.prog.set(15, "Registering with tracker…", self.root)
            meta = make_metadata(fn, chunks)
            if not _register_file(th, tp, fn, meta):
                raise RuntimeError("Tracker rejected file registration")
            log("File registered")

            # step 3: figure out which chunk goes to which peer
            if strategy == "round-robin":
                asgn = []
                for i in range(len(chunks)):
                    c = chunks[i]
                    p = peers_info[i % len(peers_info)]
                    asgn.append((c, p))
            else:
                asgn = []
                for c in chunks:
                    for p in peers_info:
                        asgn.append((c, p))

            # step 4: push each chunk to its assigned peer and register with tracker
            total = len(asgn)
            for i in range(len(asgn)):
                chunk, (pid, ph, pp) = asgn[i]
                self.prog.set(20 + 75 * i / total, "Chunk " + str(chunk["index"]) + " -> " + pid + "…", self.root)
                log("Pushing chunk " + str(chunk["index"]) + " to " + pid)
                if not _push_chunk(ph, pp, fn, chunk):
                    log("ERROR: " + pid + " rejected chunk " + str(chunk["index"]))
                    continue
                _reg_chunk(th, tp, fn, chunk["index"], pid)

            self.prog.set(100, "Done — " + str(len(chunks)) + " chunks", self.root)
            log("File shared successfully")
            self.root.after(0, lambda: messagebox.showinfo("File Sent", "'" + fn + "' shared successfully."))

        except Exception as e:
            # something went wrong - show error and re-enable the button
            err_msg = str(e)
            log("ERROR: " + str(e))
            self.prog.set(0, "Error: " + str(e), self.root)
            self.root.after(0, lambda m=err_msg: messagebox.showerror("Send Failed", m))
        finally:
            # always re-enable the send button when we're done (success or fail)
            def _restore():
                cc = T.current()
                if T.is_dark():
                    fg = "#ffffff"
                else:
                    fg = "#000000"
                self.send_btn.config(state="normal", bg=cc["teal_btn"], fg=fg)
            self.root.after(0, _restore)

    # every 2 seconds refresh the chunk table with what we have stored
    def _poll_chunks(self):
        self.chunk_tree.delete(*self.chunk_tree.get_children())
        with store_lock:
            for fn in chunk_store:
                for idx, info in sorted(chunk_store[fn].items()):
                    size_str = str(len(info["data"])) + " B"
                    hash_short = info["hash"][:36] + "…"
                    self.chunk_tree.insert("", "end", values=(fn, idx, size_str, hash_short))
        self.root.after(2000, self._poll_chunks)


# entry point when you run python hub.py
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tracker-host", default="127.0.0.1")
    parser.add_argument("--tracker-port", type=int, default=9000)
    args = parser.parse_args()

    # create window and run the gui
    root = T.make_window("P2P File Share", w=680, h=880)
    HubGUI(root, tracker_host=args.tracker_host, tracker_port=args.tracker_port)
    root.mainloop()


if __name__ == "__main__":
    main()
