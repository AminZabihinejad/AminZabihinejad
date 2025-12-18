# 🛠️ Database Recovery Guide

## Overview
This guide explains how to recover your application data from encrypted backup files in case of database corruption or data loss.

## 📋 Prerequisites
- Access to your server/web application
- Super admin access to download backup files
- The encryption key used by your application
- Python environment with required dependencies

## 🚨 When to Use This Guide
- Database file is corrupted or unreadable
- Accidental data deletion
- Hardware failure affecting database
- Need to restore to a previous point in time

## 📁 Step-by-Step Recovery Process

### Step 1: Access Backup Files
1. **Login as Super Admin** to your application
2. **Navigate to Backup Management**: Click the "📁 Backups" link in the navigation
3. **Identify the Correct Backup**:
   - Look for your client/tenant name (e.g., "Super Admin")
   - Choose the most recent database backup
   - Note: Files are named like `tenant_1.db_20251214_123902.encrypted`

### Step 2: Download the Backup
1. **Click "📥 Download"** next to the database backup file
2. **Save the file** to a secure location on your local machine
3. **Verify the download** completed successfully

### Step 3: Get Your Encryption Key
Your backup files are encrypted for security. You need the encryption key to decrypt them.

**Option A: From Application Code**
```bash
# Look in your app.py file for the KEY variable
grep "KEY.*=" app.py
# Example output: KEY = b'your-secret-key-here'
```

**Option B: From Environment Variables**
```bash
# Check if KEY is set as an environment variable
echo $KEY
```

**Option C: From Backup Email**
- Check your email for backup notifications
- The encryption key is usually included in the email

### Step 4: Prepare the Recovery Script
1. **Locate the recovery script**: `decrypt_backup.py`
2. **Edit the configuration variables**:
   ```python
   # Path to your downloaded backup file
   ENCRYPTED_FILE = "tenant_1.db_20251214_123902.encrypted"  # ← Downloaded file

   # What to name the restored database
   DECRYPTED_FILE = "tenant_1_restored.db"  # ← Output file

   # Your encryption key (from Step 3)
   KEY = "your-actual-encryption-key-here"  # ← From app.py or email
   ```

### Step 5: Run the Decryption
```bash
# Make sure you're in the correct directory
cd /path/to/your/app

# Run the decryption script
python decrypt_backup.py
```

**Expected Output:**
```
🔐 DATABASE RECOVERY SCRIPT
========================================
📁 Processing: tenant_1.db_20251214_123902.encrypted
🔑 Using encryption key: B8x9... (first 10 chars)
📖 Reading encrypted file...
🔓 Decrypting data...
💾 Writing decrypted database to: tenant_1_restored.db
📊 File size: 2456.8 KB
✅ SUCCESS: Database backup decrypted successfully!

📝 NEXT STEPS:
1. Stop your Flask application
2. Backup your current corrupted database (if possible)
3. Replace the corrupted database with: tenant_1_restored.db
4. Rename it to match your original database filename
5. Start your Flask application
6. Verify that your data has been restored
```

### Step 6: Replace the Corrupted Database
1. **Stop your Flask application**:
   ```bash
   # If running with python app.py, press Ctrl+C
   # If running with gunicorn/supervisor, stop the service
   ```

2. **Backup the corrupted database** (if possible):
   ```bash
   cp instance/tenant_1.db instance/tenant_1_CORRUPTED.db
   ```

3. **Replace the database file**:
   ```bash
   # Copy the decrypted backup to the instance directory
   cp tenant_1_restored.db instance/tenant_1.db
   ```

4. **Verify file permissions**:
   ```bash
   ls -la instance/tenant_1.db
   # Should be readable/writable by your application user
   ```

### Step 7: Restart and Verify
1. **Start your Flask application**:
   ```bash
   python app.py
   # Or however you normally start your application
   ```

2. **Verify the recovery**:
   - Login to your application
   - Check that your data is restored
   - Verify recent transactions are present
   - Test key functionality

## 🔧 Troubleshooting

### "Encryption key not configured"
- Make sure you updated the KEY variable in `decrypt_backup.py`
- Verify the key format (should start with the same prefix as in your app)

### "Encrypted file not found"
- Ensure you downloaded the backup file to the correct directory
- Check that the filename in `ENCRYPTED_FILE` matches exactly

### "Wrong encryption key"
- Double-check the KEY variable in your app.py
- Ensure you're using the correct key for this backup file
- Keys may change if you redeploy/reset your application

### "Database still corrupted after restore"
- Check that you stopped the application before replacing the file
- Verify the decrypted file is not empty: `ls -la tenant_1_restored.db`
- Check file permissions allow the application to read the database

### "Application won't start after restore"
- Check the Flask logs for database connection errors
- Verify the database file is in the correct location: `instance/tenant_1.db`
- Try running a simple database integrity check

## 📞 Support
If you encounter issues:
1. Check the error messages carefully
2. Verify all file paths and permissions
3. Ensure you're using the correct encryption key
4. Contact your system administrator if needed

## 🛡️ Security Notes
- Keep backup files and encryption keys secure
- Never share decrypted database files publicly
- Regularly test your backup and recovery procedures
- Store encryption keys in secure password managers

## 📊 Recovery Time Estimate
- **Download backup**: 1-5 minutes (depending on file size)
- **Decrypt database**: 30 seconds - 2 minutes
- **Replace database**: 1 minute
- **Application restart**: 1-2 minutes
- **Verification**: 5-10 minutes

**Total estimated recovery time: 10-25 minutes**

