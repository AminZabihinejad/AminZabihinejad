from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from datetime import datetime, date, timedelta, time
import requests
import json
import csv
from io import StringIO
from werkzeug.utils import secure_filename
import os
import uuid
from math import ceil
import sqlalchemy as sa
import pdfkit
import io
import os
import imgkit
from flask_mail import Mail, Message  # ADD AT TOP
import secrets
# === EXCHANGE NAME (GLOBAL) ===
EXCHANGE_NAME = "MoneyExchange Pro"
MAX_USERS = 5  # 5-user package

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///moneyexchange.db'
db = SQLAlchemy(app)

# FLASK-LOGIN SETUP
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# ATTACH TO APP (THIS WAS MISSING)
app.login_manager = login_manager

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


# === EMAIL CONFIG (GMAIL) ===
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'piggy.bank.exchanger@gmail.com'  # CHANGE
app.config['MAIL_PASSWORD'] = 'bsfc smqg nxtd nsxz'     # CHANGE (App Password!)
app.config['MAIL_DEFAULT_SENDER'] = 'piggy.bank.exchanger@gmail.com'

mail = Mail(app)

class Tenant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    client_name = db.Column(db.String(100), nullable=False)
    client_email = db.Column(db.String(120), unique=True, nullable=False)
    client_phone = db.Column(db.String(30))
    is_active = db.Column(db.Boolean, default=True)
    max_users = db.Column(db.Integer, default=5)  # ← NEW
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    users = db.relationship('User', backref='tenant', lazy=True)

# === MODELS ===
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_super_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)

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

    id1_type = db.Column(db.String(50))
    id1_issued_by = db.Column(db.String(100))
    id1_number = db.Column(db.String(50))
    id1_expiry_date = db.Column(db.Date)
    id1_filename = db.Column(db.String(255))
    id1_filesize = db.Column(db.Integer)
    id1_last_download = db.Column(db.DateTime)

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
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)  # AUTO
    tx_ref = db.Column(db.String(11), unique=True, nullable=False, index=True)  # DISPLAY ID
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
    total_fee_cad = db.Column(db.Float, default=0.0)  # ← PROFIT PER TX
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
    user = db.relationship('User', backref='transactions')

# === DATABASE INIT ===
# === DATABASE INIT ===
# === DATABASE INIT ===
with app.app_context():
    db.create_all()

    # Add is_super_admin column if missing
    import sqlalchemy as sa
    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    if 'is_super_admin' not in [c['name'] for c in inspector.get_columns('user')]:
        with db.engine.connect() as conn:
            conn.execute(sa.text('ALTER TABLE user ADD COLUMN is_super_admin BOOLEAN'))
            conn.execute(sa.text('UPDATE user SET is_super_admin = 0'))
            conn.commit()

    # === CREATE DEFAULT SUPER ADMIN TENANT + USER ===
    if not Tenant.query.first():
        # Create default tenant
        default_tenant = Tenant(
            name='MoneyExchange Pro - Admin',
            client_name='Super Admin',
            client_email='admin@moneyexchange.com',
            client_phone='+1 555-000-0000',
            is_active=True,
            max_users=5
        )
        db.session.add(default_tenant)
        db.session.flush()  # Get ID

        # Create super admin user
        admin = User(
            username='admin',
            password='admin123',  # TODO: Hash in production
            is_admin=True,
            is_super_admin=True,
            tenant_id=default_tenant.id
        )
        db.session.add(admin)
        db.session.commit()

        print("DEFAULT SUPER ADMIN CREATED: username=admin, password=admin123")
        print("Login at: http://127.0.0.1:5000/login")
    else:
        print("Default tenant already exists.")


# === WKHTMLTOPDF CONFIG (GLOBAL) ===

# === AUTO wkhtmltopdf PATH ===
if os.name == 'nt':  # Windows
    WKHTMLTOPDF_PATH = r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe'
    WKHTMLTOIMAGE_PATH = r'C:\Program Files\wkhtmltopdf\bin\wkhtmltoimage.exe'
else:  # Render (Linux)
    WKHTMLTOPDF_PATH = '/usr/bin/wkhtmltopdf'
    WKHTMLTOIMAGE_PATH = '/usr/bin/wkhtmltoimage'

# Validate paths
if not os.path.exists(WKHTMLTOPDF_PATH):
    raise FileNotFoundError(f"wkhtmltopdf not found: {WKHTMLTOPDF_PATH}")

config_pdf = pdfkit.configuration(wkhtmltopdf=WKHTMLTOPDF_PATH)
config_img = imgkit.config(wkhtmltoimage=WKHTMLTOIMAGE_PATH)

# === GLOBALS ===
FEE_PERCENTAGE = 0.0
FLAT_FEE_CAD = 5.0

# === HELPERS ===
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
    query = Client.query.order_by(Client.created_at.desc())

    if search:
        query = Client.query.filter_by(tenant_id=session.get('tenant_id')).order_by(Client.created_at.desc())
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
    """Generate tx_ref like 20251025001 using UTC date"""
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
        transactions = Transaction.query.all()
    else:
        if not client_id: return {}
        transactions = Transaction.query.filter_by(tenant_id=session.get('tenant_id')).all()
        # For admin without selected client, add tenant filter if neededindex

    balances = {}
    for tx in transactions:
        if tx.from_amount == 0:
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





# === REGISTER NEW SOFTWARE CLIENT ===
@app.route('/create_tenant', methods=['POST'])
@login_required
def create_tenant():
    if not current_user.is_super_admin:
        flash('Super admin access only!', 'danger')
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
        flash('Exchange name exists!', 'danger')
        return redirect(url_for('profile'))
    if Tenant.query.filter_by(client_email=email).first():
        flash('Email already registered!', 'danger')
        return redirect(url_for('profile'))

    password = secrets.token_urlsafe(10)

    tenant = Tenant(
        name=name,
        client_name=client_name,
        client_email=email,
        client_phone=phone,
        is_active=True,
        max_users=package
    )
    db.session.add(tenant)
    db.session.flush()

    admin_user = User(
        username=email.split('@')[0][:20],
        password=password,
        is_admin=True,
        is_super_admin=False,
        tenant_id=tenant.id
    )
    db.session.add(admin_user)
    db.session.commit()

    # === SEND EMAIL WITH FULL DEBUG ===
    try:
        msg = Message(
            subject=f"Your {name} Account is Ready!",
            recipients=[email],
            body=f"""
            Hello {client_name},

            Your MoneyExchange Pro is LIVE!

            Exchange: {name}
            Package: {package}-User Plan
            Login URL: http://127.0.0.1:5000/login
            Username: {admin_user.username}
            Password: {password}

            IMPORTANT: After first login, change your password.

            Support: support@moneyexchange.com

            ---
            MoneyExchange Pro Team
            """
        )
        mail.send(msg)
        flash(f'Client registered! Email sent to {email}', 'success')
    except Exception as e:
        error_msg = str(e)
        print(f"EMAIL ERROR: {error_msg}")  # ← SEE IN CONSOLE
        flash(f'Client registered but EMAIL FAILED: {error_msg}', 'danger')

    return redirect(url_for('profile'))
# === MOVE /login HERE ===
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()

        if user and user.password == password:
            login_user(user, remember=True)
            session['user_id'] = user.id
            session['is_admin'] = user.is_admin
            session['tenant_id'] = user.tenant_id
            flash('Login successful!', 'success')
            return redirect(url_for('index'))

        flash('Invalid username or password.', 'danger')

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.pop('tenant_id', None)
    flash('Logged out successfully!', 'success')
    return redirect(url_for('login'))

@app.route('/manage_tenants')
@login_required
def manage_tenants():
    if not current_user.is_super_admin:
        flash('Super admin access only!', 'danger')
        return redirect(url_for('profile'))

    tenants = Tenant.query.order_by(Tenant.created_at.desc()).all()
    return render_template('manage_tenants.html', tenants=tenants)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    global FEE_PERCENTAGE, FLAT_FEE_CAD


    if request.method == 'POST' and 'update_fees' in request.form:
        FEE_PERCENTAGE = float(request.form['fee_percentage']) / 100
        FLAT_FEE_CAD = float(request.form['flat_fee_cad'])
        flash(f'Fees updated: {FEE_PERCENTAGE*100}% + ${FLAT_FEE_CAD} CAD!')
        return redirect(url_for('index'))

    if request.method == 'POST' and not session.get('selected_client_id'):
        flash('SELECT A CLIENT FIRST!')
        return redirect(url_for('customers'))

    if request.method == 'POST':
        mode = request.form['mode']
        fixed_currency = request.form['fixed_currency']
        fixed_amount = float(request.form['fixed_amount'])
        other_currency = request.form['other_currency']
        notes = request.form.get('notes', '')
        is_fintrac = 'is_fintrac' in request.form
        status = request.form['status']

        if fixed_currency == other_currency:
            flash('Cannot exchange same currency!')
            return redirect(url_for('index'))

        rate_to_cad = float(request.form.get('rate_to_cad') or 0)
        if rate_to_cad <= 0:
            flash('Rate is required!')
            return redirect(url_for('index'))

        exchange_rate = rate_to_cad
        tx_ref = generate_tx_ref()

        if mode == 'client_fixed':
            from_currency = fixed_currency
            to_currency = other_currency
            from_amount = fixed_amount
            if from_currency == 'CAD':
                remaining = fixed_amount - FLAT_FEE_CAD
                if remaining <= 0: flash(f'Need > ${FLAT_FEE_CAD} CAD'); return redirect(url_for('index'))
                to_amount = remaining / exchange_rate
            elif to_currency == 'CAD':
                gross = fixed_amount * exchange_rate
                to_amount = gross - FLAT_FEE_CAD
                if to_amount <= 0: flash('Amount too small after fee!'); return redirect(url_for('index'))
            else:
                gross = fixed_amount * rate_to_cad
                gross -= FLAT_FEE_CAD
                to_amount = gross / rate_to_cad
        else:
            from_currency = other_currency
            to_currency = fixed_currency
            to_amount = fixed_amount
            if to_currency == 'CAD':
                from_amount = (fixed_amount + FLAT_FEE_CAD) / exchange_rate
            elif from_currency == 'CAD':
                from_amount = fixed_amount * exchange_rate + FLAT_FEE_CAD
            else:
                gross = fixed_amount * rate_to_cad
                gross -= FLAT_FEE_CAD
                to_amount = gross / rate_to_cad

        # Calculate profit in CAD
        profit_cad = FLAT_FEE_CAD
        profit_cad += from_amount * FEE_PERCENTAGE
        profit_cad = round(profit_cad, 2)
        total_fee = profit_cad

        new_tx = Transaction(
            tx_ref=tx_ref,
            from_currency=from_currency,
            to_currency=to_currency,
            from_amount=from_amount,
            to_amount=to_amount,
            exchange_rate=exchange_rate,
            notes = f"{notes} (Profit: ${profit_cad} CAD)" if notes else f"Profit: ${profit_cad} CAD",
            is_fintrac=is_fintrac or (max(from_amount, to_amount) >= 10000),
            client_id=session['selected_client_id'],
            status=status,
            total_fee_cad = total_fee,  # ← SAVE IT
            user_id = current_user.id,  # ← AUTO-SAVE WHO DID IT
            tenant_id=session.get('tenant_id')
        )
        db.session.add(new_tx)
        db.session.commit()
        flash(f'Transaction {tx_ref} created!')
        return redirect(url_for('index'))

    client = Client.query.get(session.get('selected_client_id')) if session.get('selected_client_id') else None
    total_volume_usd = 0
    led_color = '#00FF00'
    if client:
        six_months_ago = datetime.utcnow() - timedelta(days=180)
        for tx in client.transactions:
            if tx.date >= six_months_ago:
                if tx.from_currency == 'USD': total_volume_usd += tx.from_amount
                elif tx.to_currency == 'USD': total_volume_usd += tx.to_amount
                else: total_volume_usd += convert_to_usd(tx.from_amount, tx.from_currency)
        led_color = interpolate_color(total_volume_usd)
        total_volume_usd = round(total_volume_usd, 2)

    balances = get_balances()
    open_transactions = Transaction.query.filter_by(status='pending', tenant_id=session.get('tenant_id')).all()
    current_fee = round(FEE_PERCENTAGE * 100, 1)
    current_flat_fee = round(FLAT_FEE_CAD, 2)

    return render_template('index.html',
                           client=client, balances=balances, open_transactions=open_transactions,
                           current_fee=current_fee, current_flat_fee=current_flat_fee,
                           total_volume_usd=total_volume_usd, led_color=led_color,
                           fee_percentage=current_fee, flat_fee_cad=current_flat_fee)

@app.route('/profile')
@login_required
def profile():
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('No tenant selected!', 'danger')
        return redirect(url_for('login'))

    tenant = Tenant.query.get(tenant_id)
    if not tenant:
        flash('Invalid tenant!', 'danger')
        return redirect(url_for('login'))

    # Current logged-in user
    user = current_user

    # Tenant-specific stats
    total_transactions = Transaction.query.filter_by(tenant_id=tenant_id).count()
    total_clients = Client.query.filter_by(tenant_id=tenant_id).count()
    total_users = User.query.filter_by(tenant_id=tenant_id).count()
    users = User.query.filter_by(tenant_id=tenant_id).all()

    current_fee = round(FEE_PERCENTAGE * 100, 1)
    current_flat_fee = round(FLAT_FEE_CAD, 2)

    return render_template('profile.html',
                           user=user,
                           tenant=tenant,
                           total_transactions=total_transactions,
                           total_clients=total_clients,
                           total_users=total_users,
                           users=users,
                           exchange_name=EXCHANGE_NAME,
                           max_users=tenant.max_users,
                           current_fee=current_fee,
                           current_flat_fee=current_flat_fee,
                           is_super_admin=user.is_super_admin)
@app.route('/manage_users', methods=['GET', 'POST'])
@login_required
def manage_users():
    # ---- GET CURRENT TENANT (NEW) ----
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        flash('No tenant selected! Switch to a tenant first.', 'danger')
        return redirect(url_for('manage_tenants'))  # Or index()

    tenant = Tenant.query.get(tenant_id)
    if not tenant:
        flash('Invalid tenant!', 'danger')
        return redirect(url_for('manage_tenants'))

    # Only tenant admins or super-admins can manage users (UPDATED)
    if not (current_user.is_admin or current_user.is_super_admin):
        flash('Admin access required!', 'danger')
        return redirect(url_for('profile'))

    if request.method == 'POST':
        action = request.form.get('action')
        username = request.form.get('username')
        password = request.form.get('password')

        if action == 'add':
            # Check if user already exists IN THIS TENANT (UPDATED)
            if User.query.filter_by(username=username, tenant_id=tenant.id).first():
                flash(f'User {username} already exists in this tenant!', 'danger')
            elif User.query.filter_by(tenant_id=tenant.id).count() >= MAX_USERS:
                flash(f'Cannot add more than {MAX_USERS} users per tenant!', 'danger')
            else:
                # CREATE USER WITH TENANT_ID (FIX!)
                new_user = User(
                    username=username,
                    password=password,  # TODO: Hash this in production!
                    is_admin=False,
                    tenant_id=tenant.id  # ← THIS WAS MISSING
                )
                db.session.add(new_user)
                db.session.commit()
                flash(f'User {username} added to tenant "{tenant.name}"!', 'success')

        elif action == 'delete':
            user_to_delete = User.query.filter_by(id=request.form.get('user_id'), tenant_id=tenant.id).first()
            if user_to_delete and not user_to_delete.is_admin and not user_to_delete.is_super_admin:
                username = user_to_delete.username
                db.session.delete(user_to_delete)
                db.session.commit()
                flash(f'User {username} deleted!', 'success')
            else:
                flash('Cannot delete admin users or user not found!', 'danger')

    # Get users FOR THIS TENANT ONLY (UPDATED)
    users = User.query.filter_by(tenant_id=tenant.id).all()

    return render_template('manage_users.html',
                           users=users,
                           max_users=MAX_USERS,
                           exchange_name=EXCHANGE_NAME,
                           tenant=tenant)  # Pass tenant to template
@app.route('/edit_exchange_name', methods=['POST'])
def edit_exchange_name():
    if 'user_id' not in session or not session.get('is_admin'):
        return redirect(url_for('login'))

    global EXCHANGE_NAME
    new_name = request.form['exchange_name'].strip()
    if new_name:
        EXCHANGE_NAME = new_name
        flash(f'Exchange name updated to: {EXCHANGE_NAME}')
    else:
        flash('Name cannot be empty!')
    return redirect(url_for('profile'))

@app.route('/customers')
def customers():
    return render_template('customers.html', clients_data=calculate_clients_data(), now=datetime.utcnow().date())

@app.route('/select_customer/<int:client_id>')
def select_customer(client_id):
    session['selected_client_id'] = client_id
    client = Client.query.filter_by(id=client_id, tenant_id=session.get('tenant_id')).first()
    if not client:
        flash('Client not found or access denied!')
        return redirect(url_for('customers'))
    session['selected_client_name'] = f"{client.first_name} {client.last_name}"
    flash('Client selected!')
    return redirect(url_for('index'))

@app.route('/edit_client/<client_id>', methods=['GET', 'POST'])
def edit_client(client_id):
    client = None if client_id == 'new' else Client.query.filter_by(id=int(client_id), tenant_id=session.get('tenant_id')).first_or_404()

    if request.method == 'POST':
        if not client: client = Client()
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
        client.tenant_id = session.get('tenant_id')

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
def download_id_file(client_id, id_num):

    #client = Client.query.get_or_404(client_id)
    client = Client.query.filter_by(id=client_id, tenant_id=session.get('tenant_id')).first_or_404()
    filename = getattr(client, f'id{id_num}_filename')
    if not filename: flash('File not found!'); return redirect(url_for('edit_client', client_id=client_id))
    setattr(client, f'id{id_num}_last_download', datetime.utcnow())
    db.session.commit()
    return send_from_directory(app.config['ID_UPLOAD_FOLDER'], filename, as_attachment=True)

@app.route('/edit_transaction/<int:tx_id>', methods=['GET', 'POST'])  # ← ADD <int:>
def edit_transaction(tx_id):
    #tx = Transaction.query.get_or_404(tx_id)
    tx = Transaction.query.filter_by(id=tx_id, tenant_id=session.get('tenant_id')).first_or_404()
    if request.method == 'POST':
        tx.from_amount = float(request.form['from_amount'])
        tx.to_amount = tx.from_amount * float(request.form['exchange_rate'])
        tx.exchange_rate = float(request.form['exchange_rate'])
        tx.notes = request.form.get('notes')
        tx.is_fintrac = request.form.get('is_fintrac', False) == 'on'
        db.session.commit()
        flash(f'Transaction #{tx.tx_ref} updated!')
        return redirect(url_for('transactions'))
    return render_template('edit_transaction.html', tx=tx)

@app.route('/transactions')
@login_required
def transactions():

    page = int(request.args.get('page', 1)); per_page = 10
    from_date = request.args.get('from_date', ''); to_date = request.args.get('to_date', '')
    search_client = request.args.get('client_name', ''); search_from = request.args.get('from_currency', '').upper()
    search_to = request.args.get('to_currency', '').upper(); fintrac = request.args.get('fintrac', '')
    status = request.args.get('status', '')

    query = Transaction.query.filter_by(tenant_id=session.get('tenant_id')).order_by(Transaction.date.desc())
    if not session.get('is_admin'):
        client_id = session.get('selected_client_id')
        if not client_id:
            return render_template('transactions.html', transactions=[], total_count=0, total_pages=0, page=1,
                                   from_date=from_date, to_date=to_date, search_client=search_client,
                                   search_from=search_from, search_to=search_to, fintrac=fintrac, status=status,
                                   current_fee=round(FEE_PERCENTAGE*100, 1), current_flat_fee=round(FLAT_FEE_CAD, 2))
        query = query.filter(Transaction.client_id == client_id)

    if from_date:
        try: query = query.filter(Transaction.date >= datetime.strptime(from_date, '%Y-%m-%d'))
        except: pass
    if to_date:
        try: end_dt = datetime.combine(datetime.strptime(to_date, '%Y-%m-%d'), time.max)
        except: pass; query = query.filter(Transaction.date <= end_dt)

    if search_client:
        name = f"%{search_client}%"
        query = query.join(Client).filter(or_(Client.first_name.ilike(name), Client.last_name.ilike(name),
                                             func.concat(Client.first_name, ' ', Client.last_name).ilike(name)))
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
def update_status(tx_id):

    tx = Transaction.query.filter_by(id=tx_id, tenant_id=session.get('tenant_id')).first_or_404()
    tx.status = request.form['status']
    db.session.commit()
    flash(f'Transaction #{tx.tx_ref} status: {tx.status.upper()}')
    return redirect(url_for('transactions'))

@app.route('/delete/<int:tx_id>')
def delete_transaction(tx_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    tx = Transaction.query.filter_by(id=tx_id, tenant_id=session.get('tenant_id')).first_or_404()
    if not session.get('is_admin'):
        flash('Access denied!')
        return redirect(url_for('transactions'))
    tx_ref = tx.tx_ref  # Save before delete
    db.session.delete(tx)
    db.session.commit()
    flash(f'Transaction {tx_ref} deleted!')
    return redirect(url_for('transactions'))

@app.route('/charts')
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
def export_csv():

    query = Transaction.query.filter_by(tenant_id=session.get('tenant_id')).order_by(Transaction.date.desc())
    all_tx = query.all() if session.get('is_admin') else \
             query.filter_by(client_id=session.get('selected_client_id')).all() if session.get('selected_client_id') else []

    # Apply filters (same as before)
    search_date = request.args.get('date', ''); search_client = request.args.get('client_name', '')
    search_from = request.args.get('from_currency', ''); search_to = request.args.get('to_currency', '')
    search_fintrac = request.args.get('fintrac', ''); search_status = request.args.get('status', '')

    if search_fintrac == 'yes': all_tx = [tx for tx in all_tx if tx.is_fintrac]
    elif search_fintrac == 'no': all_tx = [tx for tx in all_tx if not tx.is_fintrac]
    if search_status == 'closed': all_tx = [tx for tx in all_tx if tx.status == 'closed']
    elif search_status == 'pending': all_tx = [tx for tx in all_tx if tx.status == 'pending']
    if search_date:
        d = datetime.strptime(search_date, '%Y-%m-%d').date()
        all_tx = [tx for tx in all_tx if tx.date.date() == d]
    if search_client:
        all_tx = [tx for tx in all_tx if search_client.lower() in f"{tx.client.first_name} {tx.client.last_name}".lower()]
    if search_from: all_tx = [tx for tx in all_tx if tx.from_currency.upper() == search_from.upper()]
    if search_to: all_tx = [tx for tx in all_tx if tx.to_currency.upper() == search_to.upper()]

    output = StringIO(); writer = csv.writer(output)
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
    writer.writerow([]); writer.writerow([f'TOTAL ROWS: {len(all_tx)} | TOTAL PROFIT: ${total_profit:.2f}'])
    return app.response_class(output.getvalue(), mimetype='text/csv',
                              headers={'Content-Disposition': f'attachment;filename=transactions.csv'})


@app.route('/deposit', methods=['GET', 'POST'])
@login_required
def deposit():
    # FIXED: Allow deposit page without client (shows "Select client first")
    if 'user_id' not in session:
        flash('Please login first!');
        return redirect(url_for('login'))

    client = Client.query.filter_by(id=session.get('selected_client_id'), tenant_id=session.get('tenant_id')).first()

    if request.method == 'POST':
        if not session.get('selected_client_id'):
            flash('SELECT A CLIENT FIRST!');
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
        flash(f'✅ Deposited ${amount} {currency}!')
        return redirect(url_for('deposit'))

    # Show page even without client selected
    total_deposits = 0
    if client:
        total_deposits = db.session.query(func.sum(Transaction.to_amount)).filter_by(
            client_id=client.id,
            tenant_id=session.get('tenant_id')
        ).scalar() or 0

    return render_template('deposit.html',
                           total_deposits=total_deposits,
                           client=client,
                           current_fee=0,
                           current_flat_fee=0)

@app.route('/reports')
def reports():
    if not current_user.is_authenticated:
        return redirect(url_for('login'))

    transactions = Transaction.query.filter_by(status='closed', tenant_id=session.get('tenant_id')).all()

    daily_profit = {}
    week_total = 0
    month_total = 0
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    today_str = now.strftime('%Y-%m-%d')

    import re
    profit_pattern = re.compile(r'Profit:\s*\$(?P<profit>[\d.]+)\s*CAD', re.IGNORECASE)

    for tx in transactions:
        date_str = tx.date.strftime('%Y-%m-%d')

        # Extract profit from notes
        profit = 0.0
        if tx.notes:
            match = profit_pattern.search(tx.notes)
            if match:
                try:
                    profit = float(match.group('profit'))
                except:
                    profit = 0.0

        volume = round((tx.from_amount + tx.to_amount) / 2, 2)

        if date_str not in daily_profit:
            daily_profit[date_str] = {'count': 0, 'volume': 0, 'profit': 0}

        daily_profit[date_str]['count'] += 1
        daily_profit[date_str]['volume'] += volume
        daily_profit[date_str]['profit'] += profit

        if tx.date >= week_ago:
            week_total += profit
        if tx.date >= month_ago:
            month_total += profit

    sorted_daily = dict(sorted(daily_profit.items(), key=lambda x: x[0], reverse=True))

    current_fee = round(FEE_PERCENTAGE * 100, 1)
    current_flat_fee = round(FLAT_FEE_CAD, 2)

    return render_template('reports.html',
                           daily_profit=sorted_daily,
                           today=today_str,
                           week_total=round(week_total, 2),
                           month_total=round(month_total, 2),
                           current_fee=current_fee,
                           current_flat_fee=current_flat_fee)

@app.route('/download_receipt/<int:tx_id>')
def download_receipt(tx_id):
    tx = Transaction.query.filter_by(id=tx_id, tenant_id=session.get('tenant_id')).first_or_404()
    if not tx.receipt_filename: flash('No receipt found!'); return redirect(url_for('transactions'))
    return send_from_directory(app.config['RECEIPT_FOLDER'], tx.receipt_filename)

@app.route('/set_fees', methods=['POST'])
def set_fees():
    if 'user_id' not in session or not session.get('is_admin'): return redirect(url_for('login'))
    global FEE_PERCENTAGE, FLAT_FEE_CAD
    FEE_PERCENTAGE = float(request.form['fee_percentage']) / 100
    FLAT_FEE_CAD = float(request.form['flat_fee_cad'])
    flash(f'Fees: {FEE_PERCENTAGE*100}% + ${FLAT_FEE_CAD} CAD!')
    return redirect(url_for('transactions'))



@app.route('/print_receipt/<int:tx_id>')
def print_receipt(tx_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    tx = Transaction.query.filter_by(id=tx_id, tenant_id=session.get('tenant_id')).first_or_404()
    client = tx.client

    # === CALCULATE PROFIT & FEES ===
    flat_fee_in_tx_currency = FLAT_FEE_CAD

    profit_cad = round(flat_fee_in_tx_currency + (tx.from_amount * FEE_PERCENTAGE), 2)

    return render_template('print_receipt.html',
                           tx=tx,
                           client=client,
                           exchange_name=EXCHANGE_NAME,
                           profit_cad=profit_cad,
                           flat_fee_cad=FLAT_FEE_CAD,
                           current_fee=round(FEE_PERCENTAGE * 100, 1),
                           fee_percentage=FEE_PERCENTAGE)

@app.route('/download_pdf/<int:tx_id>')
def download_pdf(tx_id):
    tx = Transaction.query.filter_by(id=tx_id, tenant_id=session.get('tenant_id')).first_or_404()
    client = tx.client

    flat_fee_in_tx_currency = FLAT_FEE_CAD
    if tx.from_currency != 'CAD':
        flat_fee_in_tx_currency = FLAT_FEE_CAD / tx.exchange_rate
    profit_cad = round(flat_fee_in_tx_currency + (tx.from_amount * FEE_PERCENTAGE), 2)

    html_content = render_template('print_receipt.html',
                                   tx=tx, client=client,
                                   exchange_name=EXCHANGE_NAME,
                                   profit_cad=profit_cad,
                                   flat_fee_cad=FLAT_FEE_CAD,
                                   current_fee=round(FEE_PERCENTAGE * 100, 1),
                                   fee_percentage=FEE_PERCENTAGE,
                                   is_download=True)

    pdf = pdfkit.from_string(html_content, False, configuration=config_pdf)

    return send_file(
        io.BytesIO(pdf),
        as_attachment=True,
        download_name=f"Receipt_{tx.tx_ref}.pdf",
        mimetype='application/pdf'
    )

@app.route('/download_png/<int:tx_id>')
def download_png(tx_id):
    tx = Transaction.query.filter_by(id=tx_id, tenant_id=session.get('tenant_id')).first_or_404()
    client = tx.client

    flat_fee_in_tx_currency = FLAT_FEE_CAD
    if tx.from_currency != 'CAD':
        flat_fee_in_tx_currency = FLAT_FEE_CAD / tx.exchange_rate
    profit_cad = round(flat_fee_in_tx_currency + (tx.from_amount * FEE_PERCENTAGE), 2)

    html_content = render_template('print_receipt.html',
                                   tx=tx, client=client,
                                   exchange_name=EXCHANGE_NAME,
                                   profit_cad=profit_cad,
                                   flat_fee_cad=FLAT_FEE_CAD,
                                   current_fee=round(FEE_PERCENTAGE * 100, 1),
                                   fee_percentage=FEE_PERCENTAGE,
                                   is_download=True)

    png_data = imgkit.from_string(
        html_content,
        False,
        config=config_img,
        options={'format': 'png', 'width': 300}
    )

    return send_file(
        io.BytesIO(png_data),
        as_attachment=True,
        download_name=f"Receipt_{tx.tx_ref}.png",
        mimetype='image/png'
    )

# -------------------------------------------------
#  SWITCH TENANT (Super-Admin only)
# -------------------------------------------------
@app.route('/switch_tenant', methods=['POST'])
@login_required
def switch_tenant():
    if not current_user.is_super_admin:
        flash('Super-admin access required!', 'danger')
        return redirect(url_for('index'))

    tenant_id = request.form.get('tenant_id')
    if not tenant_id:
        flash('Tenant ID missing!', 'danger')
        return redirect(url_for('manage_tenants'))

    tenant = Tenant.query.get(int(tenant_id))
    if not tenant:
        flash('Tenant not found!', 'danger')
        return redirect(url_for('manage_tenants'))

    # ---- Update session ----
    session['tenant_id'] = tenant.id
    session.pop('selected_client_id', None)   # clear client selection
    session.pop('selected_client_name', None)

    flash(f'Switched to tenant: <strong>{tenant.name}</strong>', 'success')
    return redirect(url_for('index'))

@app.route('/toggle_tenant/<int:tenant_id>', methods=['POST'])
@login_required
def toggle_tenant(tenant_id):
    if not current_user.is_super_admin:
        flash('Super admin access only!', 'danger')
        return redirect(url_for('profile'))

    tenant = Tenant.query.get_or_404(tenant_id)
    tenant.is_active = not tenant.is_active
    status = 'activated' if tenant.is_active else 'disabled'
    db.session.commit()
    flash(f'Client {tenant.client_name} ({tenant.name}) {status}',
          'success' if tenant.is_active else 'warning')
    return redirect(url_for('manage_tenants'))

if __name__ == '__main__':
    app.run(debug=True)