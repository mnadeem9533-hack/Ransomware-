#!/usr/bin/env python3
"""
RansomSim Key Generator
Generates RSA-4096 keypair for the ransomware simulation.
- Public key: embedded in the ransomware agent for encrypting AES keys
- Private key: held by the C2 server to decrypt exfiltrated AES keys
"""
import os
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

KEY_DIR = "keys"

def main():
    os.makedirs(KEY_DIR, exist_ok=True)

    print("[*] Generating RSA-4096 keypair...")
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=4096,
    )

    # Export private key (PEM, PKCS8, no encryption for lab use)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    with open(os.path.join(KEY_DIR, "private.pem"), "wb") as f:
        f.write(private_pem)
    print(f"[+] Private key saved to {KEY_DIR}/private.pem")

    # Export public key (PEM, SubjectPublicKeyInfo)
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    with open(os.path.join(KEY_DIR, "public.pem"), "wb") as f:
        f.write(public_pem)
    print(f"[+] Public key saved to {KEY_DIR}/public.pem")

    # Also output as a Python string for embedding in the agent
    pub_b64 = public_pem.decode()
    print("\n[*] Public key (embed this in ransomware_agent.py):")
    print("PUBLIC_KEY_PEM = \"\"\"\\")
    print(pub_b64)
    print("\"\"\"")

if __name__ == "__main__":
    main()
