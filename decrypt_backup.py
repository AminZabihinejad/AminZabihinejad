"""
DATABASE RECOVERY SCRIPT
========================

This script helps you recover from corrupted database files using encrypted backups.

USAGE:
1. Download the latest backup file from your server (via /download_backups)
2. Run this script with the correct parameters
3. Replace the corrupted database file
4. Restart your application

"""

from cryptography.fernet import Fernet
import os
import sys

# === CONFIGURATION ===
# Replace these values with your actual backup details:

# Path to your encrypted backup file (downloaded from /download_backups)
ENCRYPTED_FILE = "tenant_1.db_20251214_123902.encrypted"  # ← CHANGE THIS

# What you want to name the restored database file
DECRYPTED_FILE = "tenant_1_restored.db"  # ← CHANGE THIS

# Your encryption key (get this from your app's KEY variable or backup email)
# This is the same key used by your Flask application for backups
KEY = "B8x9...YOUR_KEY_HERE..."  # ← CHANGE THIS - GET FROM YOUR APP

def decrypt_backup():
    """Decrypt an encrypted database backup file"""

    print("🔐 DATABASE RECOVERY SCRIPT")
    print("=" * 40)

    # Check if encrypted file exists
    if not os.path.exists(ENCRYPTED_FILE):
        print(f"❌ ERROR: Encrypted file not found: {ENCRYPTED_FILE}")
        print("\n📝 INSTRUCTIONS:")
        print("1. Go to your backup download page (/download_backups)")
        print("2. Download the latest database backup file")
        print("3. Place it in the same directory as this script")
        print(f"4. Update ENCRYPTED_FILE variable to match the filename")
        return False

    # Check if key is configured
    if KEY == "B8x9...YOUR_KEY_HERE...":
        print("❌ ERROR: Encryption key not configured!")
        print("\n📝 HOW TO GET YOUR KEY:")
        print("1. Check your Flask app's KEY variable in app.py")
        print("2. Or check the backup email notifications")
        print("3. Update the KEY variable in this script")
        return False

    try:
        print(f"📁 Processing: {ENCRYPTED_FILE}")
        print(f"🔑 Using encryption key: {KEY[:10]}...")

        # Initialize Fernet with the key
        fernet = Fernet(KEY.encode())

        # Read encrypted file
        print("📖 Reading encrypted file...")
        with open(ENCRYPTED_FILE, 'rb') as enc_file:
            encrypted = enc_file.read()

        # Decrypt the data
        print("🔓 Decrypting data...")
        decrypted = fernet.decrypt(encrypted)

        # Write decrypted data to new file
        print(f"💾 Writing decrypted database to: {DECRYPTED_FILE}")
        with open(DECRYPTED_FILE, 'wb') as dec_file:
            dec_file.write(decrypted)

        # Verify the file was created and get size
        size_kb = os.path.getsize(DECRYPTED_FILE) / 1024
        print(f"📊 File size: {size_kb:.1f} KB")
        print("✅ SUCCESS: Database backup decrypted successfully!")

        print("\n📝 NEXT STEPS:")
        print("1. Stop your Flask application")
        print("2. Backup your current corrupted database (if possible)")
        print(f"3. Replace the corrupted database with: {DECRYPTED_FILE}")
        print("4. Rename it to match your original database filename")
        print("5. Start your Flask application")
        print("6. Verify that your data has been restored")

        return True

    except Exception as e:
        print(f"❌ ERROR during decryption: {e}")
        print("\n🔍 POSSIBLE ISSUES:")
        print("1. Wrong encryption key")
        print("2. Corrupted backup file")
        print("3. File permission issues")
        return False

def show_usage():
    """Show usage instructions"""
    print(__doc__)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--help":
        show_usage()
    else:
        success = decrypt_backup()
        if not success:
            print("\n💡 For help, run: python decrypt_backup.py --help")
            sys.exit(1)