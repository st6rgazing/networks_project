# receiver - gets file list from tracker then downloads chunks from peers

import socket
import threading
import argparse
import os

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox
    _HAS_TK = True
except ImportError:
    _HAS_TK = False

from utils import send_json, recv_json, send_bytes, recv_bytes, reassemble_file

if _HAS_TK:
    import theme as T

_root = None
_logw = None


def log(msg):
    print("[RECEIVER] " + str(msg))
    if _HAS_TK and _logw and _root:
        T.append_log(_logw, msg, _root)


def _list_files(th, tp):
    s = socket.socket()
    s.connect((th, tp))
    send_json(s, {"type": "LIST_FILES"})
    r = recv_json(s)
    s.close()
    return r.get("files", [])


def _get_peer_map(th, tp, fn):
    s = socket.socket()
    s.connect((th, tp))
    send_json(s, {"type": "GET_PEERS", "filename": fn})
    r = recv_json(s)
    s.close()
    if "error" in r:
        raise RuntimeError(r["error"])
    return r["metadata"], r["peer_map"]


def _fetch_chunk(ph, pp, fn, idx):
    s = socket.socket()
    s.connect((ph, pp))
    send_json(s, {"type": "GET_CHUNK", "filename": fn, "chunk_index": idx})
    r = recv_json(s)
    if r.get("status") != "ok":
        s.close()
        raise RuntimeError(r.get("reason", "unknown"))
    data = recv_bytes(s)
    s.close()
    return data, r["hash"]


class ReceiverGUI:
    def __init__(self, root, tracker_host="127.0.0.1", tracker_port=9000):
        global _root, _logw
        self.root = root
        _root = root
        self._selected = None
        c = T.current()

        T.top_bar(root, "Receiver",
            "Query tracker · fetch chunks · reconstruct file", "orange")

        scroll, _ = T.scroll_frame(root)

        w1 = tk.Frame(scroll, bg=c["bg"], padx=24)
        w1.pack(fill="x")
        T.register(lambda f=w1: f.configure(bg=T.current()["bg"]))
        T.section_label(w1, "Tracker")
        tc = T.card(w1)
        tc.pack(fill="x")

        self.th_v = tk.StringVar(value=tracker_host)
        self.tp_v = tk.StringVar(value=str(tracker_port))
        T.field_row(tc, "Tracker host", self.th_v, accent="orange", bg_level="card")
        T.field_row(tc, "Tracker port", self.tp_v, width=8, accent="orange", bg_level="card")

        T.divider(tc, bg_level="card", pady=8)

        tr = tk.Frame(tc, bg=c["card"])
        tr._level = "card"
        tr.pack(fill="x")
        T.register(lambda f=tr: f.configure(bg=T.current()["card"]))
        T.ghost_button(tr, "⟳  Refresh file list", command=self.refresh).pack(side="left")

        w2 = tk.Frame(scroll, bg=c["bg"], padx=24)
        w2.pack(fill="x")
        T.register(lambda f=w2: f.configure(bg=T.current()["bg"]))
        T.section_label(w2, "Available Files")

        lb_outer = tk.Frame(w2, bg=c["sep"])
        lb_outer._level = "sep"
        lb_outer.pack(fill="x")
        T.register(lambda f=lb_outer: f.configure(bg=T.current()["sep"]))

        lb_inner = tk.Frame(lb_outer, bg=c["card"])
        lb_inner._level = "card"
        lb_inner.pack(fill="x", padx=1, pady=1)
        T.register(lambda f=lb_inner: f.configure(bg=T.current()["card"]))

        self.lb = tk.Listbox(lb_inner, bg=c["card"], fg=c["text"],
            font=T.font(13), selectbackground=c["orange_sel"],
            selectforeground=c["orange"], relief="flat", bd=0, height=4,
            activestyle="none", highlightthickness=0)
        self.lb.pack(fill="x", padx=14, pady=8)
        self.lb.bind("<<ListboxSelect>>", self._on_select)
        T.register(lambda w=self.lb: w.configure(
            bg=T.current()["card"], fg=T.current()["text"],
            selectbackground=T.current()["orange_sel"],
            selectforeground=T.current()["orange"]))

        w3 = tk.Frame(scroll, bg=c["bg"], padx=24)
        w3.pack(fill="x")
        T.register(lambda f=w3: f.configure(bg=T.current()["bg"]))
        T.section_label(w3, "Save Location")
        dc = T.card(w3)
        dc.pack(fill="x")

        drow = tk.Frame(dc, bg=c["card"])
        drow._level = "card"
        drow.pack(fill="x")
        T.register(lambda f=drow: f.configure(bg=T.current()["card"]))

        self.outdir_v = tk.StringVar(value=os.path.expanduser("~/Downloads"))
        self.dir_lbl = tk.Label(drow, textvariable=self.outdir_v,
            font=T.font(12), fg=c["text3"], bg=c["card"], anchor="w")
        self.dir_lbl._bg_level = "card"
        self.dir_lbl._fg_level = "text3"
        self.dir_lbl.pack(side="left", fill="x", expand=True)
        T.register(lambda w=self.dir_lbl: w.configure(
            bg=T.current()["card"], fg=T.current()["text3"]))
        T.ghost_button(drow, "Change…", command=self.browse_dir).pack(side="right")

        w4 = tk.Frame(scroll, bg=c["bg"], padx=24, pady=4)
        w4.pack(fill="x")
        T.register(lambda f=w4: f.configure(bg=T.current()["bg"]))
        T.section_label(w4, "Chunk Retrieval Map")
        self.tree = T.make_tree(w4, ["chunk", "peer", "size", "status"],
            [60, 240, 90, 130], height=5)

        w5 = tk.Frame(scroll, bg=c["bg"], padx=24, pady=8)
        w5.pack(fill="x")
        T.register(lambda f=w5: f.configure(bg=T.current()["bg"]))
        self.prog = T.ProgressBar(w5, accent="orange")

        br = tk.Frame(w5, bg=c["bg"])
        br._level = "bg"
        br.pack(fill="x", pady=(8, 0))
        T.register(lambda f=br: f.configure(bg=T.current()["bg"]))

        self.dl_btn = T.accent_button(br, "⬇  Download File", "orange",
            command=self.download, padx=24, pady=10)
        self.dl_btn.pack(side="left")
        self.sel_lbl = tk.Label(br, text="(no file selected)", font=T.font(12),
            fg=c["text3"], bg=c["bg"])
        self.sel_lbl._bg_level = "bg"
        self.sel_lbl._fg_level = "text3"
        self.sel_lbl.pack(side="left", padx=14)
        T.register(lambda w=self.sel_lbl: w.configure(
            bg=T.current()["bg"], fg=T.current()["text3"]))

        wlog = tk.Frame(scroll, bg=c["bg"], padx=24, pady=4)
        wlog.pack(fill="both", expand=True)
        T.register(lambda f=wlog: f.configure(bg=T.current()["bg"]))
        T.section_label(wlog, "Event Log")
        _logw = T.log_widget(wlog)

    def refresh(self):
        try:
            files_list = _list_files(self.th_v.get().strip(), int(self.tp_v.get().strip()))
            self.lb.delete(0, "end")
            for f in files_list:
                self.lb.insert("end", "  " + f)
            log("Tracker: " + str(len(files_list)) + " file(s) available")
        except Exception as e:
            log("ERROR: " + str(e))
            messagebox.showerror("Tracker Error", str(e))

    def _on_select(self, _):
        sel = self.lb.curselection()
        if sel:
            self._selected = self.lb.get(sel[0]).strip()
            self.sel_lbl.config(text=self._selected, fg=T.current()["orange"])
            self.sel_lbl._fg_level = "orange"

    def browse_dir(self):
        d = filedialog.askdirectory(title="Select download folder")
        if d:
            self.outdir_v.set(d)

    def download(self):
        if not self._selected:
            messagebox.showwarning("No file", "Select a file from the list first.")
            return
        self.dl_btn.config(state="disabled", bg=T.current()["bg3"], fg=T.current()["text2"])
        t = threading.Thread(target=self._worker, daemon=True)
        t.start()

    def _worker(self):
        fn = self._selected
        th = self.th_v.get().strip()
        tp = int(self.tp_v.get().strip())
        outdir = self.outdir_v.get().strip()
        try:
            self.prog.set(5, "Contacting tracker…", self.root)
            log("Requesting peer map for " + fn + "…")
            meta, peer_map = _get_peer_map(th, tp, fn)
            total = meta["total_chunks"]
            # build hash lookup
            hashes = {}
            for c in meta["chunks"]:
                hashes[c["index"]] = c["hash"]
            log("Tracker: " + str(total) + " chunk(s)")

            def _tbl():
                self.tree.delete(*self.tree.get_children())
                for idx_s in peer_map:
                    pl = peer_map[idx_s]
                    for p in pl:
                        peer_str = p["peer_id"] + "  (" + p["host"] + ":" + str(p["port"]) + ")"
                        self.tree.insert("", "end", values=(idx_s, peer_str, "—", "pending"))
            self.root.after(0, _tbl)

            retrieved = {}
            for i in range(total):
                idx_s = str(i)
                pl = peer_map.get(idx_s, [])
                if not pl:
                    raise RuntimeError("No peer has chunk " + str(i))
                ok = False
                for p in pl:
                    try:
                        self.prog.set(10 + 80 * i / total,
                            "Chunk " + str(i) + "/" + str(total) + "  <-  " + p["peer_id"] + "…",
                            self.root)
                        log("Fetching chunk " + str(i) + " from " + p["peer_id"] + "…")
                        data, rh = _fetch_chunk(p["host"], p["port"], fn, i)
                        expected_hash = hashes.get(i)
                        if rh != expected_hash:
                            log("Hash mismatch chunk " + str(i) + ", trying next")
                            continue
                        retrieved[i] = {"index": i, "data": data, "hash": rh}
                        log("Chunk " + str(i) + " ok")
                        ok = True
                        break
                    except Exception as e:
                        log("Failed chunk " + str(i) + " from " + p["peer_id"] + ": " + str(e))
                if not ok:
                    raise RuntimeError("Could not retrieve chunk " + str(i))

            self.prog.set(85, "Saving chunks…", self.root)
            # Save individual chunks to a subfolder
            chunks_dir = os.path.join(outdir, fn + "_chunks")
            os.makedirs(chunks_dir, exist_ok=True)
            for i in range(total):
                chunk_path = os.path.join(chunks_dir, "chunk_" + str(i))
                with open(chunk_path, "wb") as f:
                    f.write(retrieved[i]["data"])
            log("Saved " + str(total) + " chunks to " + chunks_dir)

            self.prog.set(95, "Reassembling file…", self.root)
            outpath = os.path.join(outdir, fn)
            chunk_list = list(retrieved.values())
            if not reassemble_file(chunk_list, outpath):
                raise RuntimeError("Reassembly failed — hash mismatch")

            self.prog.set(100, "Saved to " + outpath, self.root)
            log("File reconstructed -> " + outpath)
            self.root.after(0, lambda: messagebox.showinfo(
                "Download Complete",
                "'" + fn + "' saved to:\n" + outpath + "\n\nChunks saved to:\n" + chunks_dir))

        except Exception as e:
            err_msg = str(e)
            log("ERROR: " + str(e))
            self.prog.set(0, "Error: " + str(e), self.root)
            self.root.after(0, lambda m=err_msg: messagebox.showerror("Download Failed", m))
        finally:
            def _restore():
                c = T.current()
                if T.is_dark():
                    fg = "#ffffff"
                else:
                    fg = "#000000"
                self.dl_btn.config(state="normal", bg=c["orange"], fg=fg)
            self.root.after(0, _restore)


def run_cli(tracker_host, tracker_port):
    print("Receiver — P2P File Share (CLI mode, no GUI)")
    print("Tracker: " + tracker_host + ":" + str(tracker_port) + "\n")
    try:
        files_list = _list_files(tracker_host, tracker_port)
    except Exception as e:
        print("ERROR: Could not contact tracker: " + str(e))
        return
    if not files_list:
        print("No files available on tracker.")
        return
    print("Available files:")
    for i in range(len(files_list)):
        print("  " + str(i + 1) + ". " + files_list[i])
    try:
        idx = int(input("\nEnter file number to download (or 0 to exit): "))
    except (ValueError, EOFError):
        return
    if idx < 1 or idx > len(files_list):
        print("Exiting.")
        return
    fn = files_list[idx - 1]
    outdir = input("Save to directory [default: ~/Downloads]: ").strip()
    if not outdir:
        outdir = os.path.expanduser("~/Downloads")
    try:
        log("Requesting peer map for " + fn + "…")
        meta, peer_map = _get_peer_map(tracker_host, tracker_port, fn)
        total = meta["total_chunks"]
        hashes = {}
        for c in meta["chunks"]:
            hashes[c["index"]] = c["hash"]
        log("Tracker: " + str(total) + " chunk(s)")
        retrieved = {}
        for i in range(total):
            idx_s = str(i)
            pl = peer_map.get(idx_s, [])
            if not pl:
                raise RuntimeError("No peer has chunk " + str(i))
            ok = False
            for p in pl:
                try:
                    log("Fetching chunk " + str(i) + " from " + p["peer_id"] + "…")
                    data, rh = _fetch_chunk(p["host"], p["port"], fn, i)
                    if rh != hashes.get(i):
                        log("Hash mismatch chunk " + str(i) + ", trying next")
                        continue
                    retrieved[i] = {"index": i, "data": data, "hash": rh}
                    log("Chunk " + str(i) + " ok")
                    ok = True
                    break
                except Exception as e:
                    log("Failed chunk " + str(i) + " from " + p["peer_id"] + ": " + str(e))
            if not ok:
                raise RuntimeError("Could not retrieve chunk " + str(i))
        # Save individual chunks
        chunks_dir = os.path.join(outdir, fn + "_chunks")
        os.makedirs(chunks_dir, exist_ok=True)
        for i in range(total):
            chunk_path = os.path.join(chunks_dir, "chunk_" + str(i))
            with open(chunk_path, "wb") as f:
                f.write(retrieved[i]["data"])
        log("Saved " + str(total) + " chunks to " + chunks_dir)
        # Reassemble full file
        outpath = os.path.join(outdir, fn)
        if not reassemble_file(list(retrieved.values()), outpath):
            raise RuntimeError("Reassembly failed — hash mismatch")
        log("File reconstructed -> " + outpath)
        print("\nSaved to: " + outpath)
        print("Chunks saved to: " + chunks_dir)
    except Exception as e:
        log("ERROR: " + str(e))
        print("\nDownload failed: " + str(e))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tracker-host", default="127.0.0.1")
    parser.add_argument("--tracker-port", type=int, default=9000)
    args = parser.parse_args()
    if not _HAS_TK:
        run_cli(args.tracker_host, args.tracker_port)
        return
    root = T.make_window("Receiver — P2P File Share", w=740, h=800)
    ReceiverGUI(root, tracker_host=args.tracker_host, tracker_port=args.tracker_port)
    root.mainloop()


if __name__ == "__main__":
    main()
