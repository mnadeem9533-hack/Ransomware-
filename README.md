# RansomSim — Windows Ransomware Simulation with C2

**FOR AUTHORIZED PENETRATION TESTING AND SECURITY RESEARCH ONLY**

A realistic ransomware simulation toolkit featuring hybrid AES-256 + RSA-4096
encryption, C2 server communication, and full decryption capability.

## Architecture



┌─────────────────┐ HTTP/HTTPS ┌──────────────────┐ │ Ransomware │ ◄─────────────────────────► │ C2 Server │ │ Agent (Python) │ POST /beacon │ (Controller) │ │ (Target Host) │ POST /exfil │ (Attacker) │ └─────────────────┘ └──────────────────┘

Install Dependencies

pip install -r requirements.txt
Generate RSA Keypair
bash



python keygen.py
This creates keys/private.pem and keys/public.pem.
Copy the public key output and paste it into ransomware_agent.py as PUBLIC_KEY_PEM.
Start the C2 Server
bash



python c2_server.py
The C2 listens on 0.0.0.0:8443 by default.

4. Deploy the Agent
Edit ransomware_agent.py and set:

C2_HOST to your C2 server IP
PUBLIC_KEY_PEM (already done if you followed step 2)
Run on the target:
python ransomware_agent.py
Select encryption mode and target path.

C2 Endpoints


Method	Path	Description
GET	/	Server status
GET	/admin/agents	List all agents
GET	/admin/decrypt/<agent_id>	View agent details
GET	/admin/restore/<agent_id>	Extract decryption key
POST	/beacon	Agent check-in
POST	/exfil
Encryption Details

Per-file: AES-256-CTR with random 16-byte nonce
Key protection: RSA-4096 OAEP SHA-256
File structure: [16-byte nonce][ciphertext]
Extension: Appends .encrypted to original filename
Safety Features
Skips system directories (Windows, Program Files, etc.)
Skips running executables (.exe, .dll, .sys)
Full decryption capability via C2 or manual key
Confirm prompt before encryption starts



---

## How It All Works

### The Encryption Flow (Real-World Ransomware Pattern)

1. **Agent starts** → generates a random AES-256 key in memory
2. **Walks target directories** → skips system paths
3. **For each target file**:
   - Renames file to `filename.ext.encrypted`
   - Encrypts content with AES-256-CTR using a random nonce
   - Prepends the nonce (16 bytes) to the ciphertext
4. **AES key is RSA-wrapped**: encrypted with the embedded RSA-4096 public key using OAEP/SHA-256
5. **Wrapped key is exfiltrated** to the C2 via HTTP POST `/beacon`
6. **Ransom note** dropped on desktop
7. **Persistence** added via HKCU Run registry key
8. **Continuous beaconing** every 60 seconds to maintain C2 contact

### The Decryption Flow

1. Attacker visits `GET /admin/agents` on the C2 to see all infected hosts
2. Attacker visits `GET /admin/restore/<agent_id>`
3. C2 uses its RSA private key to decrypt the AES key
4. Returns the AES key in hex format
5. Operator runs the agent in decryption mode with that key

### C2 Communication

The agent uses HTTP POST beacons (simulating HTTPS beaconing). The beacon payload contains:

```json
{
  "agent_id": "DESKTOP-ABC123-a1b2c3d4e5f6",
  "system_info": {
    "hostname": "DESKTOP-ABC123",
    "username": "jdoe",
    "ip": "192.168.1.50",
    "platform": "Windows-10-10.0.19045",
    "timestamp": "2026-05-09T14:30:00"
  },
  "encrypted_keys": "<RSA-wrapped-AES-key-base64>",
  "file_count": 142,
  "status": "active"
}
