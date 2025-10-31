from cryptography.fernet import Fernet
import os

# === CONFIG ===
ENCRYPTED_FILE = "tenant_2.db_20251031_140500.encrypted"  # ← Change this
DECRYPTED_FILE = "tenant_2_restored.db"                   # ← Output name
KEY = "B8x9...YOUR_KEY_HERE..."                          # ← Paste from email

# === DECRYPT ===
fernet = Fernet(KEY.encode())
with open(ENCRYPTED_FILE, 'rb') as enc_file:
    encrypted = enc_file.read()

decrypted = fernet.decrypt(encrypted)

with open(DECRYPTED_FILE, 'wb') as dec_file:
    dec_file.write(decrypted)

print(f"DECRYPTED: {ENCRYPTED_FILE} → {DECRYPTED_FILE}")
print(f"Size: {os.path.getsize(DECRYPTED_FILE) / 1024:.1f} KB")