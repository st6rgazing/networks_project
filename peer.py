# peer - run this on other computers/phones whatever
# each machine that stores chunks runs this, then you add it in the hub with Contact Peer

import socket
import threading
import argparse
import hashlib

from utils import send_json, recv_json, send_bytes, recv_bytes

chunk_store = {}
store_lock = threading.Lock()


def handle_client(conn, addr):
    print("[PEER] Connection from " + str(addr[0]) + ":" + str(addr[1]))
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
                    continue
                with store_lock:
                    if fn not in chunk_store:
                        chunk_store[fn] = {}
                    chunk_store[fn][idx] = {"data": data, "hash": ah}
                print("[PEER] Stored chunk " + str(idx) + " of " + fn)
                send_json(conn, {"status": "ok"})
            elif t == "GET_CHUNK":
                fn = msg["filename"]
                idx = int(msg["chunk_index"])
                with store_lock:
                    chunk = chunk_store.get(fn, {}).get(idx)
                if chunk is None:
                    send_json(conn, {"status": "error", "reason": "Chunk " + str(idx) + " not found"})
                else:
                    send_json(conn, {"status": "ok", "hash": chunk["hash"]})
                    send_bytes(conn, chunk["data"])
                    print("[PEER] Served chunk " + str(idx) + " of " + fn)
            else:
                send_json(conn, {"error": "unknown"})
    except Exception as e:
        print("[PEER] Error: " + str(e))
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="standalone peer for p2p")
    parser.add_argument("--host", default="0.0.0.0", help="bind address, 0.0.0.0 for external connections")
    parser.add_argument("--port", type=int, default=9001)
    parser.add_argument("--id", default="peer1", help="peer id for tracker")
    parser.add_argument("--tracker-host", default="127.0.0.1")
    parser.add_argument("--tracker-port", type=int, default=9000)
    parser.add_argument("--no-register", action="store_true",
        help="dont auto-register, just add it manually in hub with Contact Peer")
    parser.add_argument("--advertise-host", default=None,
        help="host to tell tracker (needed when you bind to 0.0.0.0)")
    args = parser.parse_args()

    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((args.host, args.port))
    srv.listen(20)
    print("[PEER] " + args.id + " listening on " + str(args.host) + ":" + str(args.port))

    advertise_host = args.advertise_host or ("127.0.0.1" if args.host in ("127.0.0.1", "localhost") else args.host)
    # try to register w/ tracker unless --no-register
    if not args.no_register:
        try:
            s = socket.socket()
            s.connect((args.tracker_host, args.tracker_port))
            send_json(s, {"type": "REGISTER_PEER", "peer_id": args.id, "host": advertise_host, "port": args.port})
            recv_json(s)
            s.close()
            print("[PEER] Registered with tracker")
        except Exception as e:
            print("[PEER] Tracker registration failed: " + str(e) + " (use Contact Peer in hub)")

    try:
        while True:
            conn, addr = srv.accept()
            t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            t.start()
    finally:
        srv.close()


if __name__ == "__main__":
    main()
