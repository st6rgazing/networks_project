#!/usr/bin/env python3
# external_peer.py - Run this on an external device to act as a peer.
#
# Usage:
#   python external_peer.py --peer-id ext1 --host 0.0.0.0 --port 9001
#
# Then on the main hub: add an External peer with this device's IP and port,
# and click "Connect to Peer".
#
# No GUI, no tracker - just listens for STORE_CHUNK, GET_CHUNK, and PING.

import socket
import threading
import argparse
import hashlib

from utils import send_json, recv_json, send_bytes, recv_bytes

chunk_store = {}
store_lock = threading.Lock()


def log(msg):
    print("[PEER] " + str(msg))


def handle_peer_client(conn, addr):
    log("Connection from " + str(addr[0]) + ":" + str(addr[1]))
    try:
        while True:
            msg = recv_json(conn)
            if not msg:
                break
            t = msg.get("type")
            if t == "STORE_CHUNK":
                fn = msg["filename"]
                idx = int(msg["chunk_index"])
                data = recv_bytes(conn)
                ah = hashlib.sha256(data).hexdigest()
                if ah != msg["hash"]:
                    send_json(conn, {"status": "error", "reason": "Hash mismatch"})
                    log("Hash mismatch chunk " + str(idx) + " of " + fn)
                    continue
                with store_lock:
                    if fn not in chunk_store:
                        chunk_store[fn] = {}
                    chunk_store[fn][idx] = {"data": data, "hash": ah}
                log("Stored chunk " + str(idx) + " of " + fn + " (" + str(len(data)) + " B)")
                send_json(conn, {"status": "ok"})
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
                    send_json(conn, {"status": "ok", "hash": chunk["hash"]})
                    send_bytes(conn, chunk["data"])
                    log("Served chunk " + str(idx) + " of " + fn)
            elif t == "PING":
                send_json(conn, {"status": "ok", "type": "PONG"})
            else:
                send_json(conn, {"error": "unknown"})
    except Exception as e:
        log("Error: " + str(e))
    finally:
        conn.close()


def run_peer_server(host, port, peer_id):
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(20)
    log("Peer " + peer_id + " listening on " + str(host) + ":" + str(port))
    log("Use 'Connect to Peer' from the main hub to register this peer.")
    # Print this machine's IP so user knows what to enter in the hub
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        my_ip = s.getsockname()[0]
        s.close()
        log("This device's IP: " + my_ip + " (use this in the hub's Host field)")
    except Exception:
        log("Could not detect IP - use this device's network address in the hub")
    try:
        while True:
            conn, addr = srv.accept()
            t = threading.Thread(target=handle_peer_client, args=(conn, addr), daemon=True)
            t.start()
    except KeyboardInterrupt:
        log("Shutting down...")
    finally:
        srv.close()


def main():
    parser = argparse.ArgumentParser(
        description="Run as a peer on an external device. "
        "Use 'Connect to Peer' from the main hub to register.")
    parser.add_argument("--peer-id", default="external", help="Peer identifier")
    parser.add_argument("--host", default="0.0.0.0",
        help="Host to bind (0.0.0.0 = all interfaces)")
    parser.add_argument("--port", type=int, default=9001, help="Port to listen on")
    args = parser.parse_args()

    run_peer_server(args.host, args.port, args.peer_id)


if __name__ == "__main__":
    main()
