# utils - stuff for chunking files and sending over network

import os
import hashlib
import json

# how big each chunk is (512 kb)
CHUNK_SIZE = 512 * 1024


def chunk_file(filepath):
    # split file into chunks
    chunks = []
    f = open(filepath, "rb")
    index = 0
    while True:
        data = f.read(CHUNK_SIZE)
        if not data:
            break
        # hash it so we can check its not corrupted later
        chunk_hash = hashlib.sha256(data).hexdigest()
        chunks.append({
            "index": index,
            "data": data,
            "hash": chunk_hash,
            "size": len(data),
        })
        index = index + 1
    f.close()
    return chunks


def reassemble_file(chunks, output_path):
    # put chunks back together
    sorted_chunks = sorted(chunks, key=lambda c: c["index"])
    dirname = os.path.dirname(output_path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    else:
        os.makedirs(".", exist_ok=True)
    f = open(output_path, "wb")
    for chunk in sorted_chunks:
        # make sure hash matches
        computed = hashlib.sha256(chunk["data"]).hexdigest()
        if computed != chunk["hash"]:
            f.close()
            return False
        f.write(chunk["data"])
    f.close()
    return True


def make_metadata(filename, chunks):
    # info about the file for the tracker
    chunk_list = []
    for c in chunks:
        chunk_list.append({"index": c["index"], "hash": c["hash"], "size": c["size"]})
    return {
        "filename": filename,
        "total_chunks": len(chunks),
        "chunks": chunk_list,
    }


def send_json(conn, obj):
    # send json over socket, first 8 bytes says how long it is
    payload = json.dumps(obj).encode()
    length = len(payload).to_bytes(8, "big")
    conn.sendall(length + payload)


def recv_json(conn):
    # get json from socket
    raw_len = _recv_exact(conn, 8)
    if not raw_len:
        return {}
    length = int.from_bytes(raw_len, "big")
    raw = _recv_exact(conn, length)
    return json.loads(raw.decode())


def send_bytes(conn, data):
    length = len(data).to_bytes(8, "big")
    conn.sendall(length + data)


def recv_bytes(conn):
    raw_len = _recv_exact(conn, 8)
    if not raw_len:
        return b""
    length = int.from_bytes(raw_len, "big")
    return _recv_exact(conn, length)


def _recv_exact(conn, n):
    # keep reading until we get n bytes
    buf = b""
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            return b""
        buf = buf + chunk
    return buf
