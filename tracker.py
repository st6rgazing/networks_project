# tracker - keeps track of peers and files. central server

import socket
import threading
import argparse
import tkinter as tk
from utils import send_json, recv_json
import theme as T

lock = threading.Lock()
peers = {}
files = {}
chunk_owners = {}
_root = None
_logw = None


def log(msg):
    print("[TRACKER] " + str(msg))
    if _logw and _root:
        T.append_log(_logw, msg, _root)


def handle_client(conn, addr):
    log("Connection from " + str(addr[0]) + ":" + str(addr[1]))
    try:
        while True:
            msg = recv_json(conn)
            if not msg:
                break
            t = msg.get("type")
            if t == "REGISTER_PEER":
                with lock:
                    peers[msg["peer_id"]] = {"host": msg["host"], "port": msg["port"]}
                log("Peer registered " + msg["peer_id"] + " " + msg["host"] + ":" + str(msg["port"]))
                send_json(conn, {"status": "ok"})
            elif t == "UNREGISTER_PEER":
                with lock:
                    if msg["peer_id"] in peers:
                        del peers[msg["peer_id"]]
                log("Peer unregistered " + msg["peer_id"])
                send_json(conn, {"status": "ok"})
            elif t == "REGISTER_FILE":
                with lock:
                    files[msg["filename"]] = msg["metadata"]
                    if msg["filename"] not in chunk_owners:
                        chunk_owners[msg["filename"]] = {}
                log("File registered " + msg["filename"])
                send_json(conn, {"status": "ok"})
            elif t == "REGISTER_CHUNK":
                fn = msg["filename"]
                idx = str(msg["chunk_index"])
                pid = msg["peer_id"]
                with lock:
                    if fn not in chunk_owners:
                        chunk_owners[fn] = {}
                    if idx not in chunk_owners[fn]:
                        chunk_owners[fn][idx] = []
                    if pid not in chunk_owners[fn][idx]:
                        chunk_owners[fn][idx].append(pid)
                log("Chunk " + idx + " of " + fn + " -> " + pid)
                send_json(conn, {"status": "ok"})
            elif t == "LIST_FILES":
                with lock:
                    flist = list(files.keys())
                send_json(conn, {"files": flist})
            elif t == "GET_PEERS":
                fn = msg["filename"]
                with lock:
                    meta = files.get(fn)
                    owners = chunk_owners.get(fn, {})
                    pm = {}
                    for idx, pids in owners.items():
                        pl = []
                        for p in pids:
                            if p in peers:
                                pl.append({"peer_id": p, "host": peers[p]["host"], "port": peers[p]["port"]})
                        pm[idx] = pl
                if meta is None:
                    send_json(conn, {"error": "'" + fn + "' not found"})
                else:
                    send_json(conn, {"metadata": meta, "peer_map": pm})
                log("Sent peer map for " + fn)
            else:
                send_json(conn, {"error": "unknown"})
    except Exception as e:
        log("Error: " + str(e))
    finally:
        conn.close()


def run_server(host, port):
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(20)
    log("Listening on " + str(host) + ":" + str(port))
    while True:
        conn, addr = srv.accept()
        t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
        t.start()


class TrackerGUI:
    def __init__(self, root, host="0.0.0.0", port=9000):
        global _root, _logw
        self.root = root
        _root = root
        c = T.current()

        T.top_bar(root, "Tracker", "Central registry for peers and file metadata", "blue")

        scroll, _ = T.scroll_frame(root)

        cfg_wrap = tk.Frame(scroll, bg=c["bg"], padx=24)
        cfg_wrap.pack(fill="x")
        T.register(lambda f=cfg_wrap: f.configure(bg=T.current()["bg"]))

        T.section_label(cfg_wrap, "Server Configuration")
        cfg_card = T.card(cfg_wrap)
        cfg_card.pack(fill="x")

        self.host_var = tk.StringVar(value=host)
        self.port_var = tk.StringVar(value=str(port))
        T.field_row(cfg_card, "Bind address", self.host_var, accent="blue", bg_level="card")
        T.field_row(cfg_card, "Port", self.port_var, width=8, accent="blue", bg_level="card")

        T.divider(cfg_card, bg_level="card", pady=8)

        btn_row = tk.Frame(cfg_card, bg=c["card"])
        btn_row._level = "card"
        btn_row.pack(fill="x")
        T.register(lambda f=btn_row: f.configure(bg=T.current()["card"]))

        self.start_btn = T.accent_button(btn_row, "Start Server", "blue", command=self.start)
        self.start_btn.pack(side="left")

        self.status_lbl = tk.Label(btn_row, text="● Stopped", font=T.font(12, "bold"),
            fg=c["red"], bg=c["card"])
        self.status_lbl._bg_level = "card"
        self.status_lbl.pack(side="left", padx=14)
        T.register(lambda w=self.status_lbl: w.configure(bg=T.current()["card"]))

        stats_wrap = tk.Frame(scroll, bg=c["bg"], padx=24, pady=4)
        stats_wrap.pack(fill="x")
        T.register(lambda f=stats_wrap: f.configure(bg=T.current()["bg"]))

        T.section_label(stats_wrap, "Live Stats")
        sc_row = tk.Frame(stats_wrap, bg=c["bg"])
        sc_row._level = "bg"
        sc_row.pack(fill="x")
        T.register(lambda f=sc_row: f.configure(bg=T.current()["bg"]))

        self._peers_v = T.stat_card(sc_row, "Peers Online", "blue")
        self._files_v = T.stat_card(sc_row, "Files Shared", "green")
        self._chunks_v = T.stat_card(sc_row, "Chunk Records", "text3")

        log_wrap = tk.Frame(scroll, bg=c["bg"], padx=24, pady=4)
        log_wrap.pack(fill="both", expand=True)
        T.register(lambda f=log_wrap: f.configure(bg=T.current()["bg"]))

        T.section_label(log_wrap, "Event Log")
        _logw = T.log_widget(log_wrap)

        self._poll()

    def _poll(self):
        self._peers_v.config(text=str(len(peers)))
        self._files_v.config(text=str(len(files)))
        n = 0
        for fn in chunk_owners:
            for idx in chunk_owners[fn]:
                n = n + len(chunk_owners[fn][idx])
        self._chunks_v.config(text=str(n))
        self.root.after(1000, self._poll)

    def start(self):
        host = self.host_var.get().strip()
        port = int(self.port_var.get().strip())
        self.start_btn.config(state="disabled", bg=T.current()["bg3"], fg=T.current()["text"])
        t = threading.Thread(target=run_server, args=(host, port), daemon=True)
        t.start()
        self.status_lbl.config(text="● Running on :" + str(port), fg=T.current()["green"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9000)
    args = parser.parse_args()
    root = T.make_window("Tracker — P2P File Share", w=680, h=620)
    TrackerGUI(root, host=args.host, port=args.port)
    root.mainloop()


if __name__ == "__main__":
    main()
