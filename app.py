from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, send_file, \
    jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from sqlalchemy import func, or_, text
from sqlalchemy.exc import IntegrityError
from datetime import datetime, date, timedelta, time
import requests
import json
import csv
from io import StringIO, BytesIO
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
import os
import uuid
from math import ceil
import sqlalchemy as sa
import pdfkit
import imgkit
from flask_mail import Mail, Message
import secrets
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import pickle
from cryptography.fernet import Fernet
from apscheduler.schedulers.background import BackgroundScheduler
import shutil
import boto3
from botocore.exceptions import ClientError
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from telegram.error import TelegramError  # ADD THIS IMPORT
# AFTER: from flask_mail import Mail, Message
from telegram import Bot
import asyncio
import threading
from dotenv import load_dotenv
import os
import re

load_dotenv()



# === CONFIGURATION ===
BACKUP_MODE = "email"          # "local" | "email" | "s3" | "google_drive"
BACKUP_LOCAL_DIR = "backups"
BACKUP_EMAIL_RECIPIENT = "piggy.bank.exchanger@gmail.com"
S3_BUCKET = "your-moneyexchange-backups"
S3_PREFIX = "moneyexchange/"
GOOGLE_DRIVE_FOLDER_ID = "1h1_QuBbPgwxdD1lW5klpsQjQXuKTJ3dB"

# === GLOBALS ===
EXCHANGE_NAME = "MoneyExchange Pro"
FEE_PERCENTAGE = 0.0
FLAT_FEE_CAD = 5.0

# === FLASK APP ===
app = Flask(__name__)

# === ABSOLUTELY REQUIRED ON RENDER.COM ===
app.wsgi_app = ProxyFix(
    app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1
)

# Session & cookies MUST be secure over HTTPS (Render uses HTTPS)
app.config.update(
    SECRET_KEY=os.getenv('SECRET_KEY') or 'fallback-dev-key-do-not-use-in-prod-123',  # MUST set in Render Env Vars
    SESSION_COOKIE_SECURE=True,       # Only send cookie over HTTPS
    SESSION_COOKIE_SAMESITE='Lax',    # Prevents CSRF + allows redirect
    SESSION_COOKIE_HTTPONLY=True,
    REMEMBER_COOKIE_SECURE=True,
    REMEMBER_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=60)
)

# === CUSTOM JINJA TEST (FIX regex error) ===
@app.template_test('numeric')
def is_numeric(value):
    return bool(re.match(r'^\d+$', str(value).strip())) if value else False
# === EMAIL CONFIG ===
app.config.update(
    MAIL_SERVER='smtp.gmail.com',
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USERNAME='piggy.bank.exchanger@gmail.com',
    MAIL_PASSWORD='bsfc smqg nxtd nsxz',
    MAIL_DEFAULT_SENDER='piggy.bank.exchanger@gmail.com',
    MAIL_SUPPRESS_SEND=False  # ← CRITICAL FOR DEBUG
)

# === UPLOAD CONFIG ===
UPLOAD_FOLDER = 'uploads'
RECEIPT_FOLDER = os.path.join(UPLOAD_FOLDER, 'receipts')
ID_UPLOAD_FOLDER = os.path.join(UPLOAD_FOLDER, 'id_files')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RECEIPT_FOLDER, exist_ok=True)
os.makedirs(ID_UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['RECEIPT_FOLDER'] = RECEIPT_FOLDER
app.config['ID_UPLOAD_FOLDER'] = ID_UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png'}

# === INSTANCE PATH (FOR TENANT DBs) ===
INSTANCE_DIR = Path(app.instance_path)
os.makedirs(INSTANCE_DIR, exist_ok=True)
DB_GLOB = "tenant_*.db"

# === EXTENSIONS ===
db = SQLAlchemy()
mail = Mail(app)
login_manager = LoginManager()
login_manager.login_view = 'login'

# === DEFAULT DB URI ===
DEFAULT_DB_PATH = INSTANCE_DIR / "tenant_1.db"
DEFAULT_DB_URI = f"sqlite:///{DEFAULT_DB_PATH.resolve()}"
app.config['SQLALCHEMY_DATABASE_URI'] = DEFAULT_DB_URI

# === INIT ONCE ===
db.init_app(app)
login_manager.init_app(app)

# === MODELS ===
class Tenant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    client_name = db.Column(db.String(100), nullable=False)
    client_email = db.Column(db.String(120), unique=True, nullable=False)
    client_phone = db.Column(db.String(30))
    is_active = db.Column(db.Boolean, default=True)
    max_users = db.Column(db.Integer, default=5)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    users = db.relationship('User', backref='tenant', lazy=True)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_super_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
    requires_password_change = db.Column(db.Boolean, default=True)

class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    apartment = db.Column(db.String(20))
    civic_number = db.Column(db.String(20), nullable=False)
    street = db.Column(db.String(200), nullable=False)
    city = db.Column(db.String(100), nullable=False)
    province = db.Column(db.String(10), nullable=False)
    postal_code = db.Column(db.String(10), nullable=False)
    risk_level = db.Column(db.String(20), default='low risk')
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    telegram_id = db.Column(db.String(50), nullable=True)  # ← ADD THIS LINE
    id1_type = db.Column(db.String(50))
    id1_issued_by = db.Column(db.String(100))
    id1_number = db.Column(db.String(50))
    id1_expiry_date = db.Column(db.Date)
    id1_filename = db.Column(db.String(255))
    id1_filesize = db.Column(db.Integer)
    id1_last_download = db.Column(db.DateTime)
    telegram_id = db.Column(db.String(50), nullable=True)
    id2_type = db.Column(db.String(50))
    id2_issued_by = db.Column(db.String(100))
    id2_number = db.Column(db.String(50))
    id2_expiry_date = db.Column(db.Date)
    id2_filename = db.Column(db.String(255))
    id2_filesize = db.Column(db.Integer)
    id2_last_download = db.Column(db.DateTime)

    id3_type = db.Column(db.String(50))
    id3_issued_by = db.Column(db.String(100))
    id3_number = db.Column(db.String(50))
    id3_expiry_date = db.Column(db.Date)
    id3_filename = db.Column(db.String(255))
    id3_filesize = db.Column(db.Integer)
    id3_last_download = db.Column(db.DateTime)

    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
    transactions = db.relationship('Transaction', backref='client', lazy=True)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tx_ref = db.Column(db.String(11), unique=True, nullable=False, index=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    from_currency = db.Column(db.String(3), nullable=False)
    to_currency = db.Column(db.String(3), nullable=False)
    from_amount = db.Column(db.Float, nullable=False)
    to_amount = db.Column(db.Float, nullable=False)
    exchange_rate = db.Column(db.Float, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    is_fintrac = db.Column(db.Boolean, default=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    receipt_filename = db.Column(db.String(100))
    status = db.Column(db.String(10), default='closed')
    is_deposit = db.Column(db.Boolean, default=False)
    total_fee_cad = db.Column(db.Float, default=0.0)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
    user = db.relationship('User', backref='transactions')

# === DYNAMIC DB SWITCH (CORRECT) ===
@app.before_request
def set_tenant_db():
    tenant_id = session.get('tenant_id') or 1
    db_path = INSTANCE_DIR / f"tenant_{tenant_id}.db"
    new_uri = f'sqlite:///{db_path.resolve()}'

    current_uri = app.config.get('SQLALCHEMY_DATABASE_URI')
    if current_uri != new_uri:
        db.session.remove()
        db.engine.dispose()
        app.config['SQLALCHEMY_DATABASE_URI'] = new_uri
        db.session.bind = db.create_engine(new_uri, pool_pre_ping=True)
        db.create_all()

# === USER LOADER ===
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# === CREATE DEFAULT DB + SUPER ADMIN ===
DEFAULT_DB_FILE = INSTANCE_DIR / "tenant_1.db"
if not DEFAULT_DB_FILE.exists():
    with app.app_context():
        db.create_all()

        inspector = sa.inspect(db.engine)
        user_columns = [c['name'] for c in inspector.get_columns('user')]
        if 'is_super_admin' not in user_columns:
            with db.engine.connect() as conn:
                conn.execute(text('ALTER TABLE user ADD COLUMN is_super_admin BOOLEAN DEFAULT 0'))
                conn.commit()

        if not db.session.query(Tenant).first():
            tenant = Tenant(
                name='MoneyExchange Pro - Admin',
                client_name='Super Admin',
                client_email='admin@moneyexchange.com',
                client_phone='+1 555-000-0000',
                is_active=True,
                max_users=5
            )
            db.session.add(tenant)
            db.session.flush()

            admin = User(
                username='admin',
                password=generate_password_hash('admin123'),
                is_admin=True,
                is_super_admin=True,
                tenant_id=tenant.id,
                requires_password_change=False
            )
            db.session.add(admin)
            db.session.commit()

            print("DEFAULT SUPER ADMIN: username=admin, password=admin123")
            print("Login: http://127.0.0.1:5000/login")
        else:
            print("Default tenant exists.")
else:
    print("Default DB exists.")

# === WKHTMLTOPDF ===
if os.name == 'nt':
    WKHTMLTOPDF_PATH = r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe'
    WKHTMLTOIMAGE_PATH = r'C:\Program Files\wkhtmltopdf\bin\wkhtmltoimage.exe'
else:
    WKHTMLTOPDF_PATH = '/usr/bin/wkhtmltopdf'
    WKHTMLTOIMAGE_PATH = '/usr/bin/wkhtmltoimage'

if not os.path.exists(WKHTMLTOPDF_PATH):
    raise FileNotFoundError(f"wkhtmltopdf not found: {WKHTMLTOPDF_PATH}")

config_pdf = pdfkit.configuration(wkhtmltopdf=WKHTMLTOPDF_PATH)
config_img = imgkit.config(wkhtmltoimage=WKHTMLTOIMAGE_PATH)

# === GOOGLE DRIVE BACKUP ===
# === GOOGLE DRIVE BACKUP (FIXED) ===
# === GOOGLE DRIVE BACKUP (100% WORKING) ===
# === GOOGLE DRIVE BACKUP (100% WORKING + DEBUG) ===
# === FIXED ENCRYPTION KEY (NEVER NONE AGAIN) ===
def get_encryption_key():
    key = os.getenv('DB_ENCRYPT_KEY')
    if not key:
        # AUTO-GENERATE if missing (safe for local dev)
        key = Fernet.generate_key().decode()
        print("WARNING: DB_ENCRYPT_KEY missing! Generated temporary key (will break on restart)")
        print(f"TEMP KEY: {key}")
        print("ADD THIS TO RENDER.COM ENV VARS NOW!")
    # Always return bytes
    return key.encode()

KEY = get_encryption_key()  # ← NOW 100% SAFE
SCOPES = ['https://www.googleapis.com/auth/drive.file']
TOKEN_FILE = 'token.pickle'
CREDS_FILE = 'credentials.json'
FOLDER_ID = '1h1_QuBbPgwxdD1lW5klpsQjQXuKTJ3dB'

def encrypt_db(db_path, key_bytes):
    try:
        f = Fernet(key_bytes)
        with open(db_path, 'rb') as file:
            data = file.read()
        encrypted = f.encrypt(data)
        encrypted_path = db_path + '.encrypted'
        with open(encrypted_path, 'wb') as file:
            file.write(encrypted)
        print(f"ENCRYPTED: {db_path} → {encrypted_path}")
        return encrypted_path
    except Exception as e:
        print(f"ENCRYPT FAILED: {e}")
        return None

def backup_local(db_path, key):
    os.makedirs(BACKUP_LOCAL_DIR, exist_ok=True)
    encrypted_path = encrypt_db(db_path, key)
    if not encrypted_path:
        return None
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    final_path = os.path.join(
        BACKUP_LOCAL_DIR,
        f"{os.path.basename(db_path)}_{timestamp}.encrypted"
    )
    shutil.move(encrypted_path, final_path)
    print(f"LOCAL BACKUP: {final_path}")
    return final_path

def backup_email(db_path, key):
    encrypted_path = encrypt_db(db_path, key)
    if not encrypted_path:
        return None

    filename = os.path.basename(encrypted_path)
    subject = f"MoneyExchange DB Backup – {datetime.now():%Y-%m-%d %H:%M}"
    body = (
        f"Encrypted backup of {os.path.basename(db_path)} is attached.\n\n"
        f"Generated on: {datetime.now():%Y-%m-%d %H:%M:%S}\n"
        f"Use this key to decrypt: {KEY}\n\n"
        "Warning: Keep this key secure!"
    )

    try:
        msg = Message(
            subject=subject,
            recipients=[BACKUP_EMAIL_RECIPIENT],
            body=body,
            sender=app.config['MAIL_DEFAULT_SENDER']
        )
        with open(encrypted_path, "rb") as f:
            encrypted_data = f.read()
        msg.attach(
            filename=filename,
            content_type='application/octet-stream',
            data=encrypted_data
        )

        # === FIX: ADD APP CONTEXT ===
        with app.app_context():
            mail.send(msg)
        print(f"EMAIL BACKUP SENT → {BACKUP_EMAIL_RECIPIENT}")

    except Exception as e:
        print(f"EMAIL BACKUP FAILED: {e}")
        if os.path.exists(encrypted_path):
            os.remove(encrypted_path)
        return None
    else:
        os.remove(encrypted_path)
        return encrypted_path

def backup_s3(db_path, key):
    encrypted_path = encrypt_db(db_path, key)
    if not encrypted_path:
        return None

    s3 = boto3.client('s3')
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    key_name = f"{S3_PREFIX}{os.path.basename(db_path)}_{timestamp}.encrypted"

    try:
        s3.upload_file(
            encrypted_path,
            S3_BUCKET,
            key_name,
            ExtraArgs={'ServerSideEncryption': 'AES256'}
        )
        print(f"S3 BACKUP: s3://{S3_BUCKET}/{key_name}")
    except ClientError as e:
        print(f"S3 UPLOAD FAILED: {e}")
        os.remove(encrypted_path)
        return None

    os.remove(encrypted_path)
    return key_name

def backup_one_file(db_path):
    """Encrypt + route to the selected backup method."""
    if BACKUP_MODE == "local":
        return backup_local(db_path, KEY)
    elif BACKUP_MODE == "email":
        return backup_email(db_path, KEY)
    elif BACKUP_MODE == "s3":
        return backup_s3(db_path, KEY)
    elif BACKUP_MODE == "google_drive":
        return upload_to_drive(str(db_path), FOLDER_ID)  # ← CALL GOOGLE DRIVE!
    else:
        print(f"UNKNOWN BACKUP_MODE: {BACKUP_MODE}")
        return None

# AFTER: def backup_one_file(...)

def authenticate_drive():
    try:
        creds = None
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, 'rb') as token:
                creds = pickle.load(token)
            print("Loaded token.pickle")
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                print("Token refreshed")
            else:
                print("No valid token. Opening browser for auth...")
                flow = InstalledAppFlow.from_client_secrets_file(CREDS_FILE, SCOPES)
                creds = flow.run_local_server(port=0)
            with open(TOKEN_FILE, 'wb') as token:
                pickle.dump(creds, token)
            print("Saved new token.pickle")
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        print(f"AUTH FAILED: {e}")
        return None

def upload_to_drive(db_path, folder_id):
    if not os.path.exists(db_path):
        print(f"DB FILE NOT FOUND: {db_path}")
        return None
    try:
        service = authenticate_drive()
        if not service:
            print("Google Drive auth failed.")
            return None
        encrypted_path = encrypt_db(db_path, KEY)
        if not encrypted_path:
            return None
        file_metadata = {
            'name': f'backup_{os.path.basename(db_path)}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.encrypted',
            'parents': [folder_id]
        }
        media = MediaFileUpload(encrypted_path, mimetype='application/octet-stream')
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        os.remove(encrypted_path)
        file_id = file.get('id')
        print(f"BACKED UP: {db_path} → Google Drive ID: {file_id}")
        return file_id
    except Exception as e:
        print(f"UPLOAD FAILED: {e}")
        return None

# === BACKUP ALL DB FILES (NO DB QUERY!) ===
def backup_all_tenants():
    db_files = list(INSTANCE_DIR.glob(DB_GLOB))
    if not db_files:
        print("NO TENANT DB FILES FOUND in instance folder!")
        return

    print(f"FOUND {len(db_files)} DB files:")
    for f in db_files:
        print(f"  → {f} (exists: {f.exists()})")

    for db_path in db_files:
        result = backup_one_file(str(db_path))
        if result:
            print(f"SUCCESS: {db_path.name} → {result}")
        else:
            print(f"FAILED: {db_path.name}")


# === SCHEDULE ===
scheduler = BackgroundScheduler()
scheduler.add_job(func=backup_all_tenants, trigger="interval", minutes=5)  # ← EVERY 5 MIN FOR TESTING
scheduler.start()

# === MANUAL BACKUP ROUTE (SUPER ADMIN ONLY) ===
@app.route('/backup_now')
@login_required
def backup_now():
    if not current_user.is_super_admin:
        flash('SUPER ADMIN ONLY!', 'danger')
        return redirect(url_for('profile'))

    backup_all_tenants()
    flash('Backup completed! Check the chosen destination.', 'success')
    return redirect(url_for('profile'))

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_id_file(file, client_id, id_num):
    if file and file.filename and allowed_file(file.filename):
        ext = file.filename.rsplit('.', 1)[1].lower()
        filename = secure_filename(f"{client_id}_{id_num}_{uuid.uuid4().hex[:8]}.{ext}")
        path = os.path.join(app.config['ID_UPLOAD_FOLDER'], filename)
        file.save(path)
        return filename, os.path.getsize(path)
    return None, None

def interpolate_color(volume):
    min_volume = 3000
    max_volume = 10000
    if volume < min_volume: return "#00FF00"
    if volume >= max_volume: return "#FF0000"
    ratio = (volume - min_volume) / (max_volume - min_volume)
    red = int(255 * ratio)
    green = int(255 * (1 - ratio))
    return f"#{red:02X}{green:02X}00"

def convert_to_usd(amount, currency):
    rates = {'CAD': 0.72, 'EUR': 1.08, 'GBP': 1.30, 'IRR': 0.000024}
    return amount * rates.get(currency, 1.0)

def calculate_clients_data():
    search = request.args.get('search', '')
    risk_level = request.args.get('risk_level', '')
    query = Client.query.filter_by(tenant_id=session.get('tenant_id')).order_by(Client.created_at.desc())

    if search:
        search_term = f"%{search}%"
        query = query.filter(or_(
            Client.first_name.ilike(search_term),
            Client.last_name.ilike(search_term),
            func.concat(Client.first_name, ' ', Client.last_name).ilike(search_term)
        ))
    if risk_level:
        query = query.filter(Client.risk_level == risk_level)

    clients = query.all()
    six_months_ago = datetime.utcnow() - timedelta(days=180)
    clients_data = []

    for client in clients:
        total_volume_usd = 0
        for tx in client.transactions:
            if tx.date >= six_months_ago:
                if tx.from_currency == 'USD':
                    total_volume_usd += tx.from_amount
                elif tx.to_currency == 'USD':
                    total_volume_usd += tx.to_amount
                else:
                    total_volume_usd += convert_to_usd(tx.from_amount, tx.from_currency)
        led_color = interpolate_color(total_volume_usd)
        clients_data.append({
            'client': client,
            'total_volume_usd': round(total_volume_usd, 2),
            'led_color': led_color,
            'transactions_list': client.transactions
        })
    return clients_data

def generate_tx_ref():
    today = datetime.utcnow().strftime('%Y%m%d')
    last_tx = Transaction.query.filter(
        Transaction.tx_ref.like(f"{today}%")
    ).order_by(Transaction.id.desc()).first()

    seq = 1
    if last_tx and last_tx.tx_ref and len(last_tx.tx_ref) >= 11 and last_tx.tx_ref.startswith(today):
        try:
            seq = int(last_tx.tx_ref[-3:]) + 1
        except ValueError:
            seq = 1
    return f"{today}{seq:03d}"

def get_balances():
    if 'user_id' not in session: return {}
    client_id = session.get('selected_client_id')
    if session.get('is_admin') and not client_id:
        transactions = Transaction.query.filter_by(tenant_id=session.get('tenant_id')).all()
    else:
        if not client_id: return {}
        transactions = Transaction.query.filter_by(client_id=client_id, tenant_id=session.get('tenant_id')).all()

    balances = {}
    for tx in transactions:
        if tx.is_deposit:
            balances[tx.to_currency] = balances.get(tx.to_currency, 0) + tx.to_amount
        else:
            balances[tx.from_currency] = balances.get(tx.from_currency, 0) + tx.from_amount
            balances[tx.to_currency] = balances.get(tx.to_currency, 0) - tx.to_amount
    return {k: round(v, 2) for k, v in balances.items()}

# === JINJA FILTER ===
def filesizeformat(value):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if value < 1024.0: return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} TB"
app.jinja_env.filters['filesizeformat'] = filesizeformat

# === ROUTES ===
@app.route('/edit_exchange_name', methods=['POST'])
@login_required
def edit_exchange_name():
    if not session.get('is_admin'):
        flash('Admin access required!', 'danger')
        return redirect(url_for('profile'))

    global EXCHANGE_NAME
    new_name = request.form['exchange_name'].strip()
    if new_name:
        EXCHANGE_NAME = new_name
        flash(f'Exchange name updated to: {EXCHANGE_NAME}', 'success')
    else:
        flash('Name cannot be empty!', 'danger')
    return redirect(url_for('profile'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    # If already logged in → go to dashboard
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if not username or not password:
            flash('Please fill in both fields.', 'danger')
            return render_template('login.html')

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            # === THIS IS THE KEY PART ===
            login_user(user, remember=True)

            # Populate session (optional but you were using it)
            session['user_id'] = user.id
            session['is_admin'] = user.is_admin
            session['tenant_id'] = user.tenant_id

            # First-time password change
            if getattr(user, 'requires_password_change', False):
                flash('Please change your password.', 'warning')
                return redirect(url_for('change_password', first_time=1))

            flash('Login successful!', 'success')

            # === PROPER REDIRECT WITH next SUPPORT ===
            next_page = request.args.get('next')
            if not next_page or not next_page.startswith('/'):
                next_page = url_for('index')

            return redirect(next_page)

        else:
            flash('Invalid username or password.', 'danger')

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.pop('tenant_id', None)
    session.pop('selected_client_id', None)
    flash('Logged out!', 'success')
    return redirect(url_for('login'))

@app.route('/create_tenant', methods=['POST'])
@login_required
def create_tenant():
    if not current_user.is_super_admin:
        flash('Super admin only!', 'danger')
        return redirect(url_for('profile'))

    name = request.form['exchange_name'].strip()
    client_name = request.form['client_name'].strip()
    email = request.form['client_email'].strip().lower()
    phone = request.form['client_phone'].strip()
    package = int(request.form['package'])

    if package not in [1, 5]:
        flash('Invalid package!', 'danger')
        return redirect(url_for('profile'))

    if not all([name, client_name, email]):
        flash('All fields required!', 'danger')
        return redirect(url_for('profile'))

    if Tenant.query.filter_by(name=name).first():
        flash('Name taken!', 'danger')
        return redirect(url_for('profile'))
    if Tenant.query.filter_by(client_email=email).first():
        flash('Email registered!', 'danger')
        return redirect(url_for('profile'))

    # === 1. Create Tenant in tenant_1.db (admin DB) ===
    temp_password = secrets.token_urlsafe(10)
    tenant = Tenant(
        name=name,
        client_name=client_name,
        client_email=email,
        client_phone=phone,
        is_active=True,
        max_users=package
    )
    db.session.add(tenant)
    db.session.flush()  # Get tenant.id

    admin_username = email.split('@')[0][:20]  # ← SAVE BEFORE COMMIT!
    admin_user = User(
        username=admin_username,
        password=generate_password_hash(temp_password),
        is_admin=True,
        is_super_admin=False,
        tenant_id=tenant.id,
        requires_password_change=True
    )
    db.session.add(admin_user)
    db.session.commit()  # ← Now safe to commit

    # === 2. CREATE NEW DB FILE: tenant_{id}.db ===
    # === 2. CREATE NEW DB FILE: tenant_{id}.db ===
    new_db_path = os.path.join(app.instance_path, f"tenant_{tenant.id}.db")
    abs_db_path = os.path.abspath(new_db_path)
    new_uri = f"sqlite:///{abs_db_path}"

    print(f"CREATING NEW DB: {abs_db_path}")

    # Save old config
    old_uri = app.config['SQLALCHEMY_DATABASE_URI']

    # Switch to new DB
    app.config['SQLALCHEMY_DATABASE_URI'] = new_uri
    db.session.remove()
    db.engine.dispose()
    new_engine = db.create_engine(new_uri, pool_pre_ping=True)
    db.session.bind = new_engine

    # Create tables
    db.create_all()

    # FORCE FILE CREATION
    from sqlalchemy import text
    with new_engine.connect() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS _init (id INTEGER PRIMARY KEY)"))
        conn.execute(text("INSERT INTO _init DEFAULT VALUES"))
        conn.commit()
    print(f"DB FILE CREATED ON DISK: {abs_db_path}")

    # Clean up
    with new_engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS _init"))
        conn.commit()

    # Restore original DB
    app.config['SQLALCHEMY_DATABASE_URI'] = old_uri
    db.session.remove()
    db.engine.dispose()
    db.session.bind = db.create_engine(old_uri, pool_pre_ping=True)

    print(f"NEW DB FULLY CREATED: {abs_db_path}")

    # === 3. Send Email ===
    # === 3. Send Email (FORCE SYNC) ===
    try:
        msg = Message(
            subject=f"Your {name} Account",
            recipients=[email],
            sender=app.config['MAIL_DEFAULT_SENDER'],
            body=f"""
    Hello {client_name},

    Exchange: {name}
    Login: http://127.0.0.1:5000/login
    Username: {admin_username}
    Password: {temp_password}

    Change password on first login.

    ---
    MoneyExchange Pro
            """
        )
        with app.app_context():
            mail.send(msg)
        print(f"EMAIL SENT TO: {email}")
        flash(f'Client created & email sent to {email}', 'success')
    except Exception as e:
        print(f"EMAIL FAILED: {e}")
        flash(f'Client created, email failed: {str(e)}', 'warning')

    return redirect(url_for('profile'))

@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    global FEE_PERCENTAGE, FLAT_FEE_CAD

    # === UPDATE FEES ===
    if request.method == 'POST' and 'update_fees' in request.form:
        try:
            FEE_PERCENTAGE = float(request.form['fee_percentage']) / 100
            FLAT_FEE_CAD = float(request.form['flat_fee_cad'])
            flash(f'Fees updated: {FEE_PERCENTAGE*100:.1f}% + ${FLAT_FEE_CAD:.2f} CAD', 'success')
        except ValueError:
            flash('Invalid fee values!', 'danger')
        return redirect(url_for('index'))

    # === REQUIRE CLIENT ===
    if request.method == 'POST' and not session.get('selected_client_id'):
        flash('Select client first!', 'danger')
        return redirect(url_for('customers'))

    # === CREATE TRANSACTION ===
    if request.method == 'POST':
        mode = request.form['mode']
        fixed_currency = request.form['fixed_currency']
        fixed_amount = float(request.form['fixed_amount'])
        other_currency = request.form['other_currency']
        notes = request.form.get('notes', '')
        is_fintrac = 'is_fintrac' in request.form
        status = request.form['status']

        rate_to_cad = float(request.form.get('rate_to_cad') or 0)
        if rate_to_cad <= 0:
            flash('Rate required!', 'danger')
            return redirect(url_for('index'))

        if fixed_currency == other_currency:
            flash('Same currency!', 'danger')
            return redirect(url_for('index'))

        tx_ref = generate_tx_ref()

        # Determine actual FROM and TO currencies
        if mode == 'client_fixed':
            from_currency = fixed_currency
            to_currency = other_currency
            from_amount = fixed_amount
        else:
            from_currency = other_currency
            to_currency = fixed_currency
            to_amount = fixed_amount

        # === CASE 1: CAD involved (one side is CAD) ===
        if from_currency == 'CAD' or to_currency == 'CAD':
            if from_currency == 'CAD':
                # CAD → X
                remaining = from_amount - FLAT_FEE_CAD
                if remaining <= 0:
                    flash(f'Need > ${FLAT_FEE_CAD} CAD', 'danger')
                    return redirect(url_for('index'))
                to_amount = remaining / rate_to_cad
            else:
                # X → CAD
                gross_cad = from_amount * rate_to_cad
                to_amount = gross_cad - FLAT_FEE_CAD
                if to_amount <= 0:
                    flash('Amount too small after fee!', 'danger')
                    return redirect(url_for('index'))

        # === CASE 2: NO CAD (e.g. USD → EUR) ===
        else:
            rate_from_cad = float(request.form.get('rate_from_cad') or 0)
            if rate_from_cad <= 0:
                flash('Second rate required for non-CAD pairs!', 'danger')
                return redirect(url_for('index'))

            if mode == 'client_fixed':
                # Client sells USD → gets EUR
                gross_cad = from_amount * rate_to_cad        # USD → CAD
                net_cad = gross_cad - FLAT_FEE_CAD
                if net_cad <= 0:
                    flash('Amount too small after fee!', 'danger')
                    return redirect(url_for('index'))
                to_amount = net_cad / rate_from_cad           # CAD → EUR (correct!)
            else:
                # Client wants EUR → pays USD
                gross_cad = to_amount * rate_from_cad         # EUR → CAD
                total_cad = gross_cad + FLAT_FEE_CAD
                from_amount = total_cad / rate_to_cad         # CAD → USD

        # === PROFIT CALCULATION ===
        profit_cad = FLAT_FEE_CAD + (from_amount * FEE_PERCENTAGE)
        total_fee = round(profit_cad, 2)

        # === SAVE TRANSACTION ===
        new_tx = Transaction(
            tx_ref=tx_ref,
            from_currency=from_currency,
            to_currency=to_currency,
            from_amount=round(from_amount, 6),
            to_amount=round(to_amount, 6),
            exchange_rate=rate_to_cad,
            notes=f"{notes} (Profit: ${total_fee} CAD)" if notes else f"Profit: ${total_fee} CAD",
            is_fintrac=is_fintrac or (max(from_amount, to_amount) >= 10000),
            client_id=session['selected_client_id'],
            status=status,
            total_fee_cad=total_fee,
            user_id=current_user.id,
            tenant_id=session.get('tenant_id')
        )
        db.session.add(new_tx)
        db.session.commit()

        flash(f'Tx {tx_ref} created!', 'success')
        return redirect(url_for('index'))

    # === LOAD DATA FOR RENDER ===
    client = Client.query.get(session.get('selected_client_id')) if session.get('selected_client_id') else None
    total_volume_usd = 0
    led_color = '#00FF00'
    if client:
        six_months_ago = datetime.utcnow() - timedelta(days=180)
        for tx in client.transactions:
            if tx.date >= six_months_ago:
                total_volume_usd += convert_to_usd(tx.from_amount, tx.from_currency)
        led_color = interpolate_color(total_volume_usd)
        total_volume_usd = round(total_volume_usd, 2)

    balances = get_balances()
    open_transactions = Transaction.query.filter_by(
        status='pending',
        tenant_id=session.get('tenant_id')
    ).all()

    return render_template(
        'index.html',
        client=client,
        balances=balances,
        open_transactions=open_transactions,
        total_volume_usd=total_volume_usd,
        led_color=led_color,
        fee_percentage=round(FEE_PERCENTAGE * 100, 1),
        flat_fee_cad=round(FLAT_FEE_CAD, 2),
        current_flat_fee=round(FLAT_FEE_CAD, 2),
    )

@app.route('/profile')
@login_required
def profile():
    tenant = Tenant.query.get(session.get('tenant_id'))
    if not tenant:
        flash('Invalid tenant!', 'danger')
        return redirect(url_for('login'))

    total_transactions = Transaction.query.filter_by(tenant_id=tenant.id).count()
    total_clients = Client.query.filter_by(tenant_id=tenant.id).count()
    total_users = User.query.filter_by(tenant_id=tenant.id).count()
    users = User.query.filter_by(tenant_id=tenant.id).all()

    return render_template('profile.html',
                           user=current_user,
                           tenant=tenant,
                           total_transactions=total_transactions,
                           total_clients=total_clients,
                           total_users=total_users,
                           users=users,
                           exchange_name=EXCHANGE_NAME,
                           max_users=tenant.max_users,
                           current_fee=round(FEE_PERCENTAGE * 100, 1),
                           current_flat_fee=round(FLAT_FEE_CAD, 2),
                           is_super_admin=current_user.is_super_admin)

@app.route('/manage_users', methods=['GET', 'POST'])
@login_required
def manage_users():
    tenant = Tenant.query.get(session.get('tenant_id'))
    if not (current_user.is_admin or current_user.is_super_admin):
        flash('Admin only!', 'danger')
        return redirect(url_for('profile'))

    current_count = User.query.filter_by(tenant_id=tenant.id).count()

    if request.method == 'POST':
        action = request.form.get('action')
        username = request.form.get('username')
        password = request.form.get('password')

        if action == 'add':
            if User.query.filter_by(username=username, tenant_id=tenant.id).first():
                flash(f'User {username} exists!', 'danger')
            elif current_count >= tenant.max_users:
                flash(f'Limit: {current_count}/{tenant.max_users}', 'danger')
            else:
                new_user = User(
                    username=username,
                    password=generate_password_hash(password),
                    is_admin=False,
                    tenant_id=tenant.id,
                    requires_password_change=True
                )
                db.session.add(new_user)
                db.session.commit()
                flash(f'User {username} added!', 'success')

        elif action == 'delete':
            user_id = request.form.get('user_id')
            user_to_delete = User.query.filter_by(id=user_id, tenant_id=tenant.id).first()
            if user_to_delete and not user_to_delete.is_admin and not user_to_delete.is_super_admin:
                db.session.delete(user_to_delete)
                db.session.commit()
                flash(f'User {user_to_delete.username} deleted!', 'success')
            else:
                flash('Cannot delete!', 'danger')

    current_count = User.query.filter_by(tenant_id=tenant.id).count()
    users = User.query.filter_by(tenant_id=tenant.id).order_by(User.created_at.desc()).all()

    return render_template('manage_users.html',
                           users=users,
                           current_count=current_count,
                           max_users=tenant.max_users,
                           tenant=tenant,
                           exchange_name=EXCHANGE_NAME)

@app.route('/reset_user_password/<int:user_id>', methods=['POST'])
@login_required
def reset_user_password(user_id):
    if not current_user.is_super_admin:
        flash('Super admin only!', 'danger')
        return redirect(url_for('manage_users'))

    user = User.query.get_or_404(user_id)
    if user.is_super_admin:
        flash('Cannot reset super admin!', 'danger')
        return redirect(url_for('manage_users'))

    temp_password = secrets.token_urlsafe(8)
    user.password = generate_password_hash(temp_password)
    user.requires_password_change = True
    db.session.commit()

    flash(f'Password reset. Temp: {temp_password}', 'info')
    return redirect(url_for('manage_users'))

@app.route('/manage_tenants')
@login_required
def manage_tenants():
    if not current_user.is_super_admin:
        flash('Super admin only!', 'danger')
        return redirect(url_for('profile'))

    tenants = Tenant.query.order_by(Tenant.created_at.desc()).all()
    return render_template('manage_tenants.html', tenants=tenants)

@app.route('/switch_tenant', methods=['POST'])
@login_required
def switch_tenant():
    if not current_user.is_super_admin:
        flash('Super admin only!', 'danger')
        return redirect(url_for('index'))

    tenant_id = request.form.get('tenant_id')
    tenant = Tenant.query.get(int(tenant_id))
    if not tenant:
        flash('Tenant not found!', 'danger')
        return redirect(url_for('manage_tenants'))

    session['tenant_id'] = tenant.id
    session.pop('selected_client_id', None)
    flash(f'Switched to {tenant.name}', 'success')
    return redirect(url_for('index'))

@app.route('/toggle_tenant/<int:tenant_id>', methods=['POST'])
@login_required
def toggle_tenant(tenant_id):
    if not current_user.is_super_admin:
        flash('Super admin only!', 'danger')
        return redirect(url_for('profile'))

    tenant = Tenant.query.get_or_404(tenant_id)
    tenant.is_active = not tenant.is_active
    status = 'activated' if tenant.is_active else 'disabled'
    db.session.commit()
    flash(f'Client {tenant.name} {status}', 'success' if tenant.is_active else 'warning')
    return redirect(url_for('manage_tenants'))

@app.route('/customers')
@login_required
def customers():
    return render_template('customers.html', clients_data=calculate_clients_data(), now=datetime.utcnow().date())

@app.route('/select_customer/<int:client_id>')
@login_required
def select_customer(client_id):
    client = Client.query.filter_by(id=client_id, tenant_id=session.get('tenant_id')).first()
    if not client:
        flash('Client not found!', 'danger')
        return redirect(url_for('customers'))
    session['selected_client_id'] = client.id
    session['selected_client_name'] = f"{client.first_name} {client.last_name}"
    flash('Client selected!', 'success')
    return redirect(url_for('index'))

@app.route('/edit_client/<client_id>', methods=['GET', 'POST'])
@login_required
def edit_client(client_id):
    client = None if client_id == 'new' else Client.query.filter_by(id=int(client_id), tenant_id=session.get('tenant_id')).first_or_404()

    if request.method == 'POST':
        if not client: client = Client(tenant_id=session.get('tenant_id'))
        client.first_name = request.form['first_name']
        client.last_name = request.form['last_name']
        client.email = request.form['email']
        client.phone = request.form['phone']
        client.civic_number = request.form['civic_number']
        client.street = request.form['street']
        client.city = request.form['city']
        client.province = request.form['province']
        client.postal_code = request.form['postal_code']
        client.apartment = request.form.get('apartment', '')
        client.risk_level = request.form.get('risk_level', 'low risk')
        client.notes = request.form.get('notes', '')
        client.telegram_id = request.form.get('telegram_id', '').strip() or None

        for i in range(1, 4):
            prefix = f'id{i}_'
            setattr(client, prefix + 'type', request.form.get(prefix + 'type', ''))
            setattr(client, prefix + 'issued_by', request.form.get(prefix + 'issued_by', ''))
            setattr(client, prefix + 'number', request.form.get(prefix + 'number', ''))
            date_str = request.form.get(prefix + 'expiry_date')
            expiry = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else None
            setattr(client, prefix + 'expiry_date', expiry)
            file = request.files.get(prefix + 'file')
            if file and file.filename:
                filename, filesize = save_id_file(file, client.id or 'temp', i)
                if filename:
                    setattr(client, prefix + 'filename', filename)
                    setattr(client, prefix + 'filesize', filesize)
        db.session.add(client)
        db.session.commit()
        flash(f"Client {'added' if client_id == 'new' else 'updated'}!")
        return redirect(url_for('customers'))
    return render_template('edit_client.html', client=client)

@app.route('/download_id/<int:client_id>/<int:id_num>')
@login_required
def download_id_file(client_id, id_num):
    client = Client.query.filter_by(id=client_id, tenant_id=session.get('tenant_id')).first_or_404()
    filename = getattr(client, f'id{id_num}_filename')
    if not filename:
        flash('File not found!')
        return redirect(url_for('edit_client', client_id=client_id))
    setattr(client, f'id{id_num}_last_download', datetime.utcnow())
    db.session.commit()
    return send_from_directory(app.config['ID_UPLOAD_FOLDER'], filename, as_attachment=True)

@app.route('/edit_transaction/<int:tx_id>', methods=['GET', 'POST'])
@login_required
def edit_transaction(tx_id):
    tx = Transaction.query.filter_by(id=tx_id, tenant_id=session.get('tenant_id')).first_or_404()

    if request.method == 'POST':
        try:
            from_amount = float(request.form['from_amount'])
            rate_from_cad = float(request.form['rate_from_cad'])
            rate_to_cad = float(request.form['rate_to_cad'])
            status = request.form['status']
            notes = request.form.get('notes', '')
            is_fintrac = 'is_fintrac' in request.form

            # === RECALCULATE TO_AMOUNT ===
            if tx.from_currency == 'CAD':
                remaining = from_amount - FLAT_FEE_CAD
                to_amount = remaining / rate_to_cad if remaining > 0 else 0
            elif tx.to_currency == 'CAD':
                gross_cad = from_amount * rate_from_cad
                to_amount = gross_cad - FLAT_FEE_CAD
            else:
                gross_cad = from_amount * rate_from_cad
                net_cad = gross_cad - FLAT_FEE_CAD
                to_amount = net_cad / rate_to_cad if net_cad > 0 else 0

            exchange_rate = to_amount / from_amount if from_amount > 0 else 0
            profit_cad = FLAT_FEE_CAD + (from_amount * FEE_PERCENTAGE)

            # === UPDATE DB ===
            tx.from_amount = round(from_amount, 6)
            tx.to_amount = round(to_amount, 6)
            tx.exchange_rate = round(exchange_rate, 6)
            tx.status = status
            tx.notes = notes
            tx.is_fintrac = is_fintrac or (max(from_amount, to_amount) >= 10000)
            tx.total_fee_cad = round(profit_cad, 2)

            # === UPLOAD RECEIPT ===
            if 'receipt_file' in request.files:
                file = request.files['receipt_file']
                if file and file.filename.endswith('.pdf'):
                    filename = secure_filename(f"receipt_{tx.tx_ref}.pdf")
                    filepath = os.path.join('receipts', filename)
                    os.makedirs('receipts', exist_ok=True)
                    file.save(filepath)
                    tx.receipt_filename = filename

            db.session.commit()
            flash(f'Tx #{tx.tx_ref} updated!', 'success')
        except Exception as e:
            flash(f'Error: {str(e)}', 'danger')

        return redirect(url_for('transactions'))

    # GET: pre-calculate rates
    gross_cad = tx.from_amount * tx.exchange_rate
    rate_from_cad = gross_cad / tx.from_amount if tx.from_amount else 0
    net_cad = gross_cad - FLAT_FEE_CAD
    rate_to_cad = net_cad / tx.to_amount if tx.to_amount else 0

    return render_template(
        'edit_transaction.html',
        tx=tx,
        client=tx.client,
        flat_fee_cad=FLAT_FEE_CAD,
        fee_percentage=FEE_PERCENTAGE,
        profit_cad=tx.total_fee_cad or 0,
        rate_from_cad=rate_from_cad,
        rate_to_cad=rate_to_cad
    )

@app.route('/transactions')
@login_required
def transactions():
    page = int(request.args.get('page', 1))
    per_page = 10
    from_date = request.args.get('from_date', '')
    to_date = request.args.get('to_date', '')
    search_client = request.args.get('client_name', '')
    search_from = request.args.get('from_currency', '').upper()
    search_to = request.args.get('to_currency', '').upper()
    fintrac = request.args.get('fintrac', '')
    status = request.args.get('status', '')

    query = Transaction.query.filter_by(tenant_id=session.get('tenant_id')).order_by(Transaction.date.desc())
    if not session.get('is_admin'):
        client_id = session.get('selected_client_id')
        if not client_id:
            return render_template('transactions.html', transactions=[], total_count=0, total_pages=0, page=1)
        query = query.filter(Transaction.client_id == client_id)

    if from_date:
        try: query = query.filter(Transaction.date >= datetime.strptime(from_date, '%Y-%m-%d'))
        except: pass
    if to_date:
        try: end_dt = datetime.combine(datetime.strptime(to_date, '%Y-%m-%d'), time.max)
        except: pass; query = query.filter(Transaction.date <= end_dt)

    if search_client:
        name = f"%{search_client}%"
        query = query.join(Client).filter(or_(
            Client.first_name.ilike(name),
            Client.last_name.ilike(name),
            func.concat(Client.first_name, ' ', Client.last_name).ilike(name)
        ))
    if search_from: query = query.filter(Transaction.from_currency == search_from)
    if search_to: query = query.filter(Transaction.to_currency == search_to)
    if fintrac == 'yes': query = query.filter(Transaction.is_fintrac == True)
    elif fintrac == 'no': query = query.filter(Transaction.is_fintrac == False)
    if status: query = query.filter(Transaction.status == status)

    total_count = query.count()
    total_pages = ceil(total_count / per_page) if total_count > 0 else 1
    page = max(1, min(page, total_pages))
    transactions = query.offset((page - 1) * per_page).limit(per_page).all()

    return render_template('transactions.html', transactions=transactions, page=page, total_count=total_count,
                           total_pages=total_pages, from_date=from_date, to_date=to_date, search_client=search_client,
                           search_from=search_from, search_to=search_to, fintrac=fintrac, status=status,
                           current_fee=round(FEE_PERCENTAGE*100, 1), current_flat_fee=round(FLAT_FEE_CAD, 2))

@app.route('/update_status/<int:tx_id>', methods=['POST'])
@login_required
def update_status(tx_id):
    tx = Transaction.query.filter_by(id=tx_id, tenant_id=session.get('tenant_id')).first_or_404()
    tx.status = request.form['status']
    db.session.commit()
    flash(f'Tx #{tx.tx_ref} → {tx.status.upper()}')
    return redirect(url_for('transactions'))

@app.route('/delete/<int:tx_id>')
@login_required
def delete_transaction(tx_id):
    tx = Transaction.query.filter_by(id=tx_id, tenant_id=session.get('tenant_id')).first_or_404()
    if not session.get('is_admin'):
        flash('Admin only!')
        return redirect(url_for('transactions'))
    tx_ref = tx.tx_ref
    db.session.delete(tx)
    db.session.commit()
    flash(f'Tx {tx_ref} deleted!')
    return redirect(url_for('transactions'))

@app.route('/charts')
@login_required
def charts():
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    client_id = session.get('selected_client_id')
    query = Transaction.query.filter(Transaction.date >= thirty_days_ago, Transaction.tenant_id==session.get('tenant_id'))
    if client_id: query = query.filter_by(client_id=client_id)
    transactions = query.order_by(Transaction.date).all()

    daily_balances = {}
    for tx in transactions:
        date_str = tx.date.strftime('%Y-%m-%d')
        if date_str not in daily_balances:
            daily_balances[date_str] = {'USD': 0, 'EUR': 0, 'GBP': 0, 'IRR': 0, 'CAD': 0}
        if tx.is_deposit:
            daily_balances[date_str][tx.to_currency] += tx.to_amount
        else:
            daily_balances[date_str][tx.from_currency] += tx.from_amount
            daily_balances[date_str][tx.to_currency] -= tx.to_amount

    dates = sorted(daily_balances.keys())
    usd_data = [daily_balances[d].get('USD', 0) for d in dates]
    eur_data = [daily_balances[d].get('EUR', 0) for d in dates]
    chart_data = {'dates': dates, 'usd': usd_data, 'eur': eur_data}
    return render_template('charts.html', chart_data=json.dumps(chart_data))

@app.route('/get_live_rate_with_fee/<from_curr>/<to_curr>')
def get_live_rate_with_fee(from_curr, to_curr):
    try:
        url = f"https://api.exchangerate-api.com/v4/latest/{from_curr}"
        data = requests.get(url).json()
        return str(round(data['rates'][to_curr], 10))
    except: return str(round(0.85, 10))

@app.route('/get_rate/<from_curr>/<to_curr>')
def get_live_rate(from_curr, to_curr):
    try:
        url = f"https://api.exchangerate-api.com/v4/latest/{from_curr}"
        data = requests.get(url).json()
        return str(round(data['rates'][to_curr], 4))
    except: return "0.85"

@app.route('/export')
@login_required
def export_csv():
    query = Transaction.query.filter_by(tenant_id=session.get('tenant_id')).order_by(Transaction.date.desc())
    all_tx = query.all() if session.get('is_admin') else \
             query.filter_by(client_id=session.get('selected_client_id')).all() if session.get('selected_client_id') else []

    search_date = request.args.get('date', '')
    search_client = request.args.get('client_name', '')
    search_from = request.args.get('from_currency', '')
    search_to = request.args.get('to_currency', '')
    search_fintrac = request.args.get('fintrac', '')
    search_status = request.args.get('status', '')

    if search_fintrac == 'yes': all_tx = [tx for tx in all_tx if tx.is_fintrac]
    elif search_fintrac == 'no': all_tx = [tx for tx in all_tx if not tx.is_fintrac]
    if search_status: all_tx = [tx for tx in all_tx if tx.status == search_status]
    if search_date:
        d = datetime.strptime(search_date, '%Y-%m-%d').date()
        all_tx = [tx for tx in all_tx if tx.date.date() == d]
    if search_client:
        all_tx = [tx for tx in all_tx if search_client.lower() in f"{tx.client.first_name} {tx.client.last_name}".lower()]
    if search_from: all_tx = [tx for tx in all_tx if tx.from_currency.upper() == search_from.upper()]
    if search_to: all_tx = [tx for tx in all_tx if tx.to_currency.upper() == search_to.upper()]

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Date', 'Client', 'From', 'From Amount', 'To', 'To Amount', 'Rate', 'Notes', 'Profit'])
    total_profit = 0
    for tx in all_tx:
        profit = round((tx.from_amount * FEE_PERCENTAGE * 100) + FLAT_FEE_CAD, 2)
        total_profit += profit
        writer.writerow([
            tx.tx_ref, tx.date.strftime('%Y-%m-%d %H:%M'),
            f"{tx.client.first_name} {tx.client.last_name}",
            tx.from_currency, f"{tx.from_amount:.2f}", tx.to_currency,
            f"{tx.to_amount:.2f}", f"{tx.exchange_rate:.4f}", tx.notes or '',
            f"${profit:.2f}"
        ])
    writer.writerow([])
    writer.writerow([f'TOTAL: {len(all_tx)} | PROFIT: ${total_profit:.2f}'])
    return app.response_class(output.getvalue(), mimetype='text/csv',
                              headers={'Content-Disposition': 'attachment;filename=transactions.csv'})

@app.route('/deposit', methods=['GET', 'POST'])
@login_required
def deposit():
    client = Client.query.filter_by(id=session.get('selected_client_id'), tenant_id=session.get('tenant_id')).first()

    if request.method == 'POST':
        if not session.get('selected_client_id'):
            flash('Select client first!')
            return redirect(url_for('customers'))

        currency = request.form['currency']
        amount = float(request.form['amount'])
        notes = request.form.get('notes', f'Deposit {amount} {currency}')
        tx_ref = generate_tx_ref()

        new_tx = Transaction(
            tx_ref=tx_ref,
            from_currency=currency,
            to_currency=currency,
            from_amount=0,
            to_amount=amount,
            exchange_rate=1.0,
            notes=notes,
            is_fintrac=(amount >= 10000),
            client_id=session['selected_client_id'],
            status=request.form.get('status', 'closed'),
            is_deposit=True,
            total_fee_cad=0.0,
            tenant_id=session.get('tenant_id')
        )
        db.session.add(new_tx)
        db.session.commit()
        flash(f'Deposited ${amount} {currency}!')
        return redirect(url_for('deposit'))

    total_deposits = 0
    if client:
        total_deposits = db.session.query(func.sum(Transaction.to_amount)).filter_by(
            client_id=client.id, is_deposit=True, tenant_id=session.get('tenant_id')
        ).scalar() or 0

    return render_template('deposit.html', total_deposits=total_deposits, client=client)

@app.route('/reports')
@login_required
def reports():
    transactions = Transaction.query.filter_by(status='closed', tenant_id=session.get('tenant_id')).all()

    daily_profit = {}
    week_total = 0
    month_total = 0
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    import re
    profit_pattern = re.compile(r'Profit:\s*\$(?P<profit>[\d.]+)\s*CAD', re.IGNORECASE)

    for tx in transactions:
        date_str = tx.date.strftime('%Y-%m-%d')
        profit = 0.0
        if tx.notes:
            match = profit_pattern.search(tx.notes)
            if match:
                try: profit = float(match.group('profit'))
                except: profit = 0.0

        volume = round((tx.from_amount + tx.to_amount) / 2, 2)

        if date_str not in daily_profit:
            daily_profit[date_str] = {'count': 0, 'volume': 0, 'profit': 0}
        daily_profit[date_str]['count'] += 1
        daily_profit[date_str]['volume'] += volume
        daily_profit[date_str]['profit'] += profit

        if tx.date >= week_ago: week_total += profit
        if tx.date >= month_ago: month_total += profit

    sorted_daily = dict(sorted(daily_profit.items(), key=lambda x: x[0], reverse=True))

    return render_template('reports.html',
                           daily_profit=sorted_daily,
                           today=now.strftime('%Y-%m-%d'),
                           week_total=round(week_total, 2),
                           month_total=round(month_total, 2),
                           current_fee=round(FEE_PERCENTAGE * 100, 1),
                           current_flat_fee=round(FLAT_FEE_CAD, 2))

@app.route('/print_receipt/<int:tx_id>')
@login_required
def print_receipt(tx_id):
    tx = Transaction.query.filter_by(id=tx_id, tenant_id=session.get('tenant_id')).first_or_404()
    client = tx.client

    profit_cad = round(FLAT_FEE_CAD + (tx.from_amount * FEE_PERCENTAGE), 2)

    return render_template('print_receipt.html',
                           tx=tx, client=client, exchange_name=EXCHANGE_NAME,
                           profit_cad=profit_cad, flat_fee_cad=FLAT_FEE_CAD,
                           current_fee=round(FEE_PERCENTAGE * 100, 1), fee_percentage=FEE_PERCENTAGE)

@app.route('/download_pdf/<int:tx_id>')
@login_required
def download_pdf(tx_id):
    tx = Transaction.query.filter_by(id=tx_id, tenant_id=session.get('tenant_id')).first_or_404()
    client = tx.client
    profit_cad = round(FLAT_FEE_CAD + (tx.from_amount * FEE_PERCENTAGE), 2)

    html_content = render_template('print_receipt.html',
                                   tx=tx, client=client, exchange_name=EXCHANGE_NAME,
                                   profit_cad=profit_cad, flat_fee_cad=FLAT_FEE_CAD,
                                   current_fee=round(FEE_PERCENTAGE * 100, 1), fee_percentage=FEE_PERCENTAGE,
                                   is_download=True)

    pdf = pdfkit.from_string(html_content, False, configuration=config_pdf)
    return send_file(BytesIO(pdf), as_attachment=True, download_name=f"Receipt_{tx.tx_ref}.pdf", mimetype='application/pdf')

@app.route('/download_png/<int:tx_id>')
@login_required
def download_png(tx_id):
    tx = Transaction.query.filter_by(id=tx_id, tenant_id=session.get('tenant_id')).first_or_404()
    client = tx.client
    profit_cad = round(FLAT_FEE_CAD + (tx.from_amount * FEE_PERCENTAGE), 2)

    html_content = render_template('print_receipt.html',
                                   tx=tx, client=client, exchange_name=EXCHANGE_NAME,
                                   profit_cad=profit_cad, flat_fee_cad=FLAT_FEE_CAD,
                                   current_fee=round(FEE_PERCENTAGE * 100, 1), fee_percentage=FEE_PERCENTAGE,
                                   is_download=True)

    png_data = imgkit.from_string(html_content, False, config=config_img, options={'format': 'png', 'width': 300})
    return send_file(BytesIO(png_data), as_attachment=True, download_name=f"Receipt_{tx.tx_ref}.png", mimetype='image/png')

@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    first_time = request.args.get('first_time')

    if request.method == 'POST':
        current_pwd = request.form.get('current_password')
        new_pwd = request.form.get('new_password')
        confirm_pwd = request.form.get('confirm_password')

        if not check_password_hash(current_user.password, current_pwd):
            flash('Current password incorrect.', 'danger')
            return redirect(url_for('change_password', first_time=first_time))

        if new_pwd != confirm_pwd:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('change_password', first_time=first_time))

        if len(new_pwd) < 6:
            flash('Password too short.', 'danger')
            return redirect(url_for('change_password', first_time=first_time))

        current_user.password = generate_password_hash(new_pwd)
        current_user.requires_password_change = False
        db.session.commit()
        flash('Password changed!', 'success')
        return redirect(url_for('index'))

    return render_template('change_password.html', first_time=first_time)



@app.route('/set_fees', methods=['POST'])
@login_required
def set_fees():
    if not session.get('is_admin'):
        flash('Admin access required!', 'danger')
        return redirect(url_for('profile'))

    global FEE_PERCENTAGE, FLAT_FEE_CAD
    updated = False
    messages = []

    # === PERCENTAGE FEE ===
    perc_raw = request.form['fee_percentage'].strip()
    if perc_raw:  # Only update if not empty
        try:
            perc = float(perc_raw)
            if 0 <= perc <= 10:
                FEE_PERCENTAGE = perc / 100
                messages.append(f"{perc:.1f}%")
                updated = True
            else:
                flash('Percentage must be 0–10!', 'danger')
                return redirect(url_for('profile'))
        except ValueError:
            flash('Invalid percentage! Use numbers only.', 'danger')
            return redirect(url_for('profile'))
    else:
        messages.append(f"{FEE_PERCENTAGE * 100:.1f}%")

    # === FLAT FEE ===
    flat_raw = request.form['flat_fee_cad'].strip()
    if flat_raw:  # Only update if not empty
        try:
            flat = float(flat_raw)
            if 0 <= flat <= 50:
                FLAT_FEE_CAD = flat
                messages.append(f"${flat:.2f} CAD")
                updated = True
            else:
                flash('Flat fee must be 0–50!', 'danger')
                return redirect(url_for('profile'))
        except ValueError:
            flash('Invalid flat fee! Use numbers only.', 'danger')
            return redirect(url_for('profile'))
    else:
        messages.append(f"${FLAT_FEE_CAD:.2f} CAD")

    # === FINAL MESSAGE ===
    if updated:
        flash(f'Fees updated → {" + ".join(messages)}', 'success')
    else:
        flash('No changes made.', 'info')

    return redirect(url_for('profile'))



@app.route('/send_telegram_receipt/<int:tx_id>', methods=['POST'])
@login_required
def send_telegram_receipt(tx_id):
    tx = Transaction.query.get_or_404(tx_id)
    client = tx.client
    raw_id = client.telegram_id.strip() if client.telegram_id else ""

    if not raw_id:
        return jsonify({'error': 'No Telegram ID'}), 400

    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        return jsonify({'error': 'Bot token missing'}), 500

    # SUPPORT @username OR numeric
    chat_id = None
    bot = Bot(token=token)
    if raw_id.startswith('@'):
        try:
            chat = bot.get_chat(raw_id)
            chat_id = chat.id
        except TelegramError as e:
            app.logger.error(f"Invalid @username: {e}")
            return jsonify({'error': 'Invalid @username'}), 400
    else:
        if not raw_id.isdigit():
            return jsonify({'error': 'Invalid ID'}), 400
        chat_id = int(raw_id)

    # Generate PDF
    pdf_path = os.path.join(app.config['RECEIPT_FOLDER'], f"{tx.tx_ref}.pdf")
    try:
        html = render_template('print_receipt.html',
                               tx=tx, client=client, exchange_name=EXCHANGE_NAME,
                               profit_cad=tx.total_fee_cad or 0,
                               flat_fee_cad=FLAT_FEE_CAD,
                               current_fee=round(FEE_PERCENTAGE * 100, 1),
                               fee_percentage=FEE_PERCENTAGE,
                               is_download=True)
        pdf_data = pdfkit.from_string(html, False, configuration=config_pdf)
        with open(pdf_path, 'wb') as f:
            f.write(pdf_data)

        # === ASYNC SEND (FIXED) ===
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            with open(pdf_path, 'rb') as f:
                loop.run_until_complete(
                    bot.send_document(
                        chat_id=chat_id,
                        document=f,
                        caption=f"Receipt {tx.tx_ref}\n{EXCHANGE_NAME}",
                        filename=f"Receipt_{tx.tx_ref}.pdf"
                    )
                )
            return jsonify({'status': 'sent'}), 200
        except TelegramError as e:
            app.logger.error(f"Telegram send failed: {e}")
            return jsonify({'error': 'Send failed'}), 500
        finally:
            loop.close()

    except Exception as e:
        app.logger.error(f"PDF error: {e}")
        return jsonify({'error': 'PDF failed'}), 500
    finally:
        if os.path.exists(pdf_path):
            try: os.remove(pdf_path)
            except: pass

@app.route('/download_receipt/<int:tx_id>')
@login_required
def download_receipt(tx_id):
    """Legacy alias — redirects to download_pdf"""
    return redirect(url_for('download_pdf', tx_id=tx_id))

if __name__ == '__main__':
    app.run(debug=True)