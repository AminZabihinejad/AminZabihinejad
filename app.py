from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from datetime import datetime, date, timedelta, time
import requests
import json
import csv
from io import StringIO
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import uuid
from math import ceil
import sqlalchemy as sa

app = Flask(__name__)
app.config['SECRET_KEY'] = 'piggybank2025'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png'}


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


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

    # ✅ NEW ID FIELDS (OPTIONAL)
    id1_type = db.Column(db.String(50))
    id1_issued_by = db.Column(db.String(100))
    id1_number = db.Column(db.String(50))
    id1_expiry_date = db.Column(db.Date)

    id2_type = db.Column(db.String(50))
    id2_issued_by = db.Column(db.String(100))
    id2_number = db.Column(db.String(50))
    id2_expiry_date = db.Column(db.Date)

    id3_type = db.Column(db.String(50))
    id3_issued_by = db.Column(db.String(100))
    id3_number = db.Column(db.String(50))
    id3_expiry_date = db.Column(db.Date)

    # Legacy fields (keep for compatibility)
    #id_card_number = db.Column(db.String(50))
    #id_expiry_date = db.Column(db.Date)

    transactions = db.relationship('Transaction', backref='client', lazy=True)

class Transaction(db.Model):
    id = db.Column(db.String(11), primary_key=True)
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


with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', password='admin123', is_admin=True)
        db.session.add(admin)
        db.session.commit()

# ✅ GLOBAL FEES - 0% PERCENTAGE, $5 FLAT FEE
FEE_PERCENTAGE = 0.0
FLAT_FEE_CAD = 5.0


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def interpolate_color(volume):
    min_volume = 3000
    max_volume = 10000
    if volume < min_volume:
        return "#00FF00"
    if volume >= max_volume:
        return "#FF0000"
    ratio = (volume - min_volume) / (max_volume - min_volume)
    red = int(255 * ratio)
    green = int(255 * (1 - ratio))
    blue = 0
    return f"#{red:02X}{green:02X}{blue:02X}"


def convert_to_usd(amount, currency):
    rates = {'CAD': 0.72, 'EUR': 1.08, 'GBP': 1.30, 'IRR': 0.000024}
    return amount * rates.get(currency, 1.0)


def calculate_clients_data():
    search = request.args.get('search', '')
    risk_level = request.args.get('risk_level', '')
    query = Client.query.order_by(Client.created_at.desc())

    if search:
        query = query.filter(
            db.or_(
                Client.first_name.ilike(f'%{search}%'),
                Client.last_name.ilike(f'%{search}%'),
                Client.email.ilike(f'%{search}%'),
                Client.phone.ilike(f'%{search}%')
            )
        )
    if risk_level:
        query = query.filter(Client.risk_level == risk_level)

    clients = query.all()
    print(f"🔍 LOADED {len(clients)} clients from DB")

    six_months_ago = datetime.utcnow() - timedelta(days=180)
    clients_data = []

    for client in clients:
        try:
            # ✅ FIX: client.transactions IS ALREADY A LIST - NO .all()!
            transactions_list = client.transactions  # ← THIS IS THE FIX!
            total_volume_usd = 0
            for tx in transactions_list:
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
                'transactions_list': transactions_list
            })
        except Exception as e:
            print(f"❌ Client {client.id} error: {e}")
            continue

    print(f"🔍 Returning {len(clients_data)} clients for display")
    return clients_data


def generate_transaction_id(transaction_date):
    date_str = transaction_date.strftime('%Y%m%d')
    start_of_day = datetime.strptime(date_str, '%Y%m%d')
    end_of_day = start_of_day + timedelta(days=1)
    tx_count = Transaction.query.filter(
        Transaction.date >= start_of_day,
        Transaction.date < end_of_day
    ).count()
    seq_number = tx_count + 1
    seq_str = f'{seq_number:03d}'
    return f'{date_str}{seq_str}'


def get_balances():
    if 'user_id' not in session:
        return {}
    client_id = session.get('selected_client_id')
    if session.get('is_admin') and not client_id:
        transactions = Transaction.query.all()
    else:
        if not client_id:
            return {}
        transactions = Transaction.query.filter_by(client_id=client_id).all()

    balances = {}
    for tx in transactions:
        if tx.from_amount == 0:  # DEPOSIT
            balances[tx.to_currency] = balances.get(tx.to_currency, 0) + tx.to_amount
        else:  # EXCHANGE: Exchange RECEIVES from_amount, PAYS to_amount
            balances[tx.from_currency] = balances.get(tx.from_currency, 0) + tx.from_amount
            balances[tx.to_currency] = balances.get(tx.to_currency, 0) - tx.to_amount

    return {k: round(v, 2) for k, v in balances.items()}


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.password == password:
            session['user_id'] = user.id
            session['is_admin'] = user.is_admin
            flash('Login successful!')
            return redirect(url_for('index'))
        flash('Invalid credentials!')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/', methods=['GET', 'POST'])
def index():
    global FEE_PERCENTAGE, FLAT_FEE_CAD

    if 'user_id' not in session:
        return redirect(url_for('login'))

    # ✅ FEE UPDATE FROM DASHBOARD
    if request.method == 'POST' and 'update_fees' in request.form:
        FEE_PERCENTAGE = float(request.form['fee_percentage']) / 100
        FLAT_FEE_CAD = float(request.form['flat_fee_cad'])
        flash(f'✅ Fees updated: {FEE_PERCENTAGE * 100}% + ${FLAT_FEE_CAD} CAD!')
        return redirect(url_for('index'))

    if request.method == 'POST' and not session.get('selected_client_id'):
        flash('👥 SELECT A CLIENT FIRST!')
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

        try:
            rate_to_cad = float(request.form.get('rate_to_cad') or 0)
            rate_from_cad = float(request.form.get('rate_from_cad') or 0)
        except (ValueError, TypeError):
            flash('Invalid rate entered!')
            return redirect(url_for('index'))

        if rate_to_cad <= 0:
            flash('Rate is required!')
            return redirect(url_for('index'))

        if not rate_to_cad:
            flash('Rate is required!')
            return redirect(url_for('index'))

        # Determine which rate to use as exchange_rate
        if fixed_currency == 'CAD' or other_currency == 'CAD':
            if fixed_currency == 'CAD':
                exchange_rate = float(rate_to_cad)  # 1 CAD → OTHER
            else:
                exchange_rate = float(rate_from_cad or 0)
                if exchange_rate == 0:
                    flash('Rate is required!')
                    return redirect(url_for('index'))
        else:
            exchange_rate = float(rate_to_cad)  # 1 fixed → CAD
            # Optional: store second rate in notes
            if rate_from_cad:
                notes = f"{notes} | Rate (1 {other_currency}→CAD): {rate_from_cad}".strip()

        tx_id = generate_transaction_id(datetime.utcnow())

        # === CALCULATE FROM/TO AMOUNTS ===
        if mode == 'client_fixed':
            from_currency = fixed_currency
            to_currency = other_currency
            from_amount = fixed_amount

            if from_currency == 'CAD':
                remaining_cad = fixed_amount - FLAT_FEE_CAD
                if remaining_cad <= 0:
                    flash(f'Amount too small! Need > ${FLAT_FEE_CAD} CAD')
                    return redirect(url_for('index'))
                to_amount = remaining_cad / exchange_rate
            elif to_currency == 'CAD':
                gross_to_amount = fixed_amount * exchange_rate
                to_amount = gross_to_amount - FLAT_FEE_CAD
                if to_amount <= 0:
                    flash(f'Amount too small after fee!')
                    return redirect(url_for('index'))
            else:
                gross_to_amount = fixed_amount * rate_to_cad
                gross_to_amount = gross_to_amount - FLAT_FEE_CAD
                to_amount = gross_to_amount / rate_from_cad
                if to_amount <= 0:
                    flash(f'Amount too small after fee!')
                    return redirect(url_for('index'))

        else:  # bank_fixed
            from_currency = other_currency
            to_currency = fixed_currency
            to_amount = fixed_amount

            if to_currency == 'CAD':
                exchange_needed = (fixed_amount + FLAT_FEE_CAD) / exchange_rate
                from_amount = exchange_needed
                if from_amount <= 0:
                    flash(f'Amount too small after fee!')
                    return redirect(url_for('index'))
            elif from_currency == 'CAD':
                exchange_needed = fixed_amount * exchange_rate
                from_amount = exchange_needed + FLAT_FEE_CAD
                if from_amount <= 0:
                    flash(f'Amount too small after fee!')
                    return redirect(url_for('index'))

            else:
                gross_to_amount = fixed_amount * rate_to_cad
                gross_to_amount = gross_to_amount - FLAT_FEE_CAD
                to_amount = gross_to_amount / rate_from_cad
                if to_amount <= 0:
                    flash(f'Amount too small after fee!')
                    return redirect(url_for('index'))

        # === FLASH CONFIRMATION ===
        client_pays = f"{from_amount:,.2f} {from_currency}"
        bank_receives = f"{to_amount:,.2f} {to_currency}"
        fee_in_client_currency = f"{(FLAT_FEE_CAD / exchange_rate):,.2f} {from_currency}" if from_currency != 'CAD' else f"{FLAT_FEE_CAD:,.2f} CAD"

        flash(
            f"Transaction ready!<br>"
            f"• You pay: <strong>{client_pays}</strong><br>"
            f"• Bank receives: <strong>{bank_receives}</strong><br>"
            f"• Flat fee ({FLAT_FEE_CAD} CAD): {fee_in_client_currency}"
        )
        new_tx = Transaction(
            id=tx_id,
            from_currency=from_currency,
            to_currency=to_currency,
            from_amount=from_amount,
            to_amount=to_amount,
            exchange_rate=exchange_rate,
            notes=f"{notes} (Fee: ${FLAT_FEE_CAD} CAD)",
            is_fintrac=is_fintrac or (max(from_amount, to_amount) >= 10000),
            client_id=session['selected_client_id'],
            status=status
        )
        db.session.add(new_tx)
        db.session.commit()

        flash(f'✅ {from_amount:.2f} {from_currency} → {to_amount:.2f} {to_currency} (Fee: ${FLAT_FEE_CAD} CAD)')
        return redirect(url_for('index'))

    # GET: Render dashboard (UNCHANGED)
    client = None
    total_volume_usd = 0
    led_color = '#00FF00'
    if session.get('selected_client_id'):
        client = Client.query.get(session['selected_client_id'])
        if client:
            six_months_ago = datetime.utcnow() - timedelta(days=180)
            transactions_list = client.transactions  # ✅ CORRECT!
            for tx in transactions_list:
                if tx.date >= six_months_ago:
                    if tx.from_currency == 'USD':
                        total_volume_usd += tx.from_amount
                    elif tx.to_currency == 'USD':
                        total_volume_usd += tx.to_amount
                    else:
                        total_volume_usd += convert_to_usd(tx.from_amount, tx.from_currency)
            led_color = interpolate_color(total_volume_usd)
            total_volume_usd = round(total_volume_usd, 2)

    balances = get_balances()
    open_transactions = Transaction.query.filter_by(status='pending').all()
    other_currency = 'CAD'
    current_fee = round(FEE_PERCENTAGE * 100, 1)
    current_flat_fee = round(FLAT_FEE_CAD, 2)

    return render_template('index.html',
                           client=client,
                           balances=balances,
                           open_transactions=open_transactions,
                           other_currency=other_currency,
                           current_fee=current_fee,
                           current_flat_fee=current_flat_fee,
                           total_volume_usd=total_volume_usd,
                           led_color=led_color,
                           fee_percentage=current_fee,
                           flat_fee_cad=current_flat_fee)


@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    current_user = User.query.get(session['user_id'])
    total_transactions = Transaction.query.count()
    total_clients = Client.query.count()
    current_fee = round(FEE_PERCENTAGE * 100, 1)
    current_flat_fee = round(FLAT_FEE_CAD, 2)
    return render_template('profile.html',
                           user=current_user,
                           total_transactions=total_transactions,
                           total_clients=total_clients,
                           current_fee=current_fee, current_flat_fee=current_flat_fee)


@app.route('/customers', methods=['GET', 'POST'])
def customers():
    if 'user_id' not in session:
        flash('🔒 Please log in first!')
        return redirect(url_for('login'))

    # ✅ REMOVED OLD POST HANDLING
    print(f"🔍 Customers page - loading {Client.query.count()} total clients")

    return render_template('customers.html',
                           clients_data=calculate_clients_data(),
                           request=request,
                           form_data={},
                           now=datetime.utcnow().date())


@app.route('/select_customer/<int:client_id>')
def select_customer(client_id):
    session['selected_client_id'] = client_id
    selected_client = Client.query.get(client_id)
    session['selected_client_name'] = f"{selected_client.first_name} {selected_client.last_name}"
    flash('✅ Client selected!')
    return redirect(url_for('index'))


@app.route('/edit_client/<client_id>', methods=['GET', 'POST'])
def edit_client(client_id):
    print(f"🔍 DEBUG: edit_client called with client_id={client_id}, method={request.method}")  # DEBUG

    if 'user_id' not in session:
        return redirect(url_for('login'))

    if client_id == 'new':
        client = None
    else:
        client = Client.query.get_or_404(int(client_id))

    if request.method == 'POST':
        print(f"🔍 POST DATA: {dict(request.form)}")  # DEBUG - SEE WHAT'S SENT

        if client_id == 'new':
            client = Client()

        # Parse dates safely
        def parse_date(date_str):
            try:
                return datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else None
            except:
                return None

        # REQUIRED FIELDS
        client.first_name = request.form['first_name']
        client.last_name = request.form['last_name']
        client.email = request.form['email']
        client.phone = request.form['phone']
        client.civic_number = request.form['civic_number']
        client.street = request.form['street']
        client.city = request.form['city']
        client.province = request.form['province']
        client.postal_code = request.form['postal_code']

        # OPTIONAL FIELDS
        client.apartment = request.form.get('apartment', '')
        client.risk_level = request.form.get('risk_level', 'low risk')
        client.notes = request.form.get('notes', '')

        # 3 IDs (OPTIONAL)
        client.id1_type = request.form.get('id1_type', '')
        client.id1_issued_by = request.form.get('id1_issued_by', '')
        client.id1_number = request.form.get('id1_number', '')
        client.id1_expiry_date = parse_date(request.form.get('id1_expiry_date'))

        client.id2_type = request.form.get('id2_type', '')
        client.id2_issued_by = request.form.get('id2_issued_by', '')
        client.id2_number = request.form.get('id2_number', '')
        client.id2_expiry_date = parse_date(request.form.get('id2_expiry_date'))

        client.id3_type = request.form.get('id3_type', '')
        client.id3_issued_by = request.form.get('id3_issued_by', '')
        client.id3_number = request.form.get('id3_number', '')
        client.id3_expiry_date = parse_date(request.form.get('id3_expiry_date'))

        try:
            db.session.add(client)
            db.session.commit()
            print(f"✅ SAVED client ID: {client.id}")  # DEBUG
            flash(f"✅ Client {'updated' if client_id != 'new' else 'added'} successfully! ID: {client.id}")
            return redirect(url_for('customers'))
        except Exception as e:
            db.session.rollback()
            print(f"❌ SAVE ERROR: {e}")  # DEBUG
            flash(f"❌ Save failed: {str(e)}")
            return redirect(url_for('edit_client', client_id='new'))

    return render_template('edit_client.html', client=client)

@app.route('/edit_transaction/<tx_id>', methods=['GET', 'POST'])
def edit_transaction(tx_id):
    tx = Transaction.query.get_or_404(tx_id)
    if request.method == 'POST':
        tx.from_amount = float(request.form['from_amount'])
        tx.to_amount = tx.from_amount * float(request.form['exchange_rate'])
        tx.exchange_rate = float(request.form['exchange_rate'])
        tx.notes = request.form.get('notes')
        tx.is_fintrac = request.form.get('is_fintrac', False) == 'on'
        db.session.commit()
        flash(f'✅ Transaction #{tx.id} updated!')
        return redirect(url_for('transactions'))
    return render_template('edit_transaction.html', tx=tx)



@app.route('/transactions')
def transactions():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # === GET PAGINATION & FILTERS ===
    page = int(request.args.get('page', 1))
    per_page = 10

    from_date = request.args.get('from_date', '')
    to_date = request.args.get('to_date', '')
    search_client = request.args.get('client_name', '')
    search_from = request.args.get('from_currency', '').upper()
    search_to = request.args.get('to_currency', '').upper()
    fintrac = request.args.get('fintrac', '')
    status = request.args.get('status', '')

    # === BUILD BASE QUERY ===
    query = Transaction.query.order_by(Transaction.date.desc())

    # === APPLY CLIENT FILTER (ADMIN vs USER) ===
    if not session.get('is_admin'):
        client_id = session.get('selected_client_id')
        if not client_id:
            return render_template('transactions.html', transactions=[], total_count=0, total_pages=0, page=1,
                                   from_date=from_date, to_date=to_date,
                                   search_client=search_client, search_from=search_from, search_to=search_to,
                                   fintrac=fintrac, status=status,
                                   current_fee=round(FEE_PERCENTAGE * 100, 1),
                                   current_flat_fee=round(FLAT_FEE_CAD, 2))
        query = query.filter(Transaction.client_id == client_id)

    # === DATE RANGE FILTER ===
    if from_date:
        try:
            start_dt = datetime.strptime(from_date, '%Y-%m-%d')
            query = query.filter(Transaction.date >= start_dt)
        except ValueError:
            pass
    if to_date:
        try:
            end_dt = datetime.strptime(to_date, '%Y-%m-%d')
            end_dt = datetime.combine(end_dt, time.max)
            query = query.filter(Transaction.date <= end_dt)
        except ValueError:
            pass

    # === OTHER FILTERS (SQL) ===
    if search_client:
        name = f"%{search_client}%"
        query = query.join(Client).filter(
            sa.or_(
                Client.first_name.ilike(name),
                Client.last_name.ilike(name),
                sa.func.concat(Client.first_name, ' ', Client.last_name).ilike(name)
            )
        )
    if search_from:
        query = query.filter(Transaction.from_currency == search_from)
    if search_to:
        query = query.filter(Transaction.to_currency == search_to)
    if fintrac == 'yes':
        query = query.filter(Transaction.is_fintrac == True)
    elif fintrac == 'no':
        query = query.filter(Transaction.is_fintrac == False)
    if status:
        query = query.filter(Transaction.status == status)

    # === COUNT TOTAL FOR PAGINATION ===
    total_count = query.count()
    total_pages = ceil(total_count / per_page) if total_count > 0 else 1
    page = max(1, min(page, total_pages))  # Clamp page

    # === PAGINATE ===
    transactions = query.offset((page - 1) * per_page).limit(per_page).all()

    # === RENDER ===
    return render_template('transactions.html',
                           transactions=transactions,
                           page=page,
                           total_count=total_count,
                           total_pages=total_pages,
                           from_date=from_date,
                           to_date=to_date,
                           search_client=search_client,
                           search_from=search_from,
                           search_to=search_to,
                           fintrac=fintrac,
                           status=status,
                           current_fee=round(FEE_PERCENTAGE * 100, 1),
                           current_flat_fee=round(FLAT_FEE_CAD, 2))


@app.route('/update_status/<tx_id>', methods=['POST'])
def update_status(tx_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    tx = Transaction.query.get_or_404(tx_id)
    tx.status = request.form['status']
    db.session.commit()
    flash(f'✅ Transaction #{tx.id} status: {tx.status.upper()}')
    return redirect(url_for('transactions'))


@app.route('/charts')
def charts():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    client_id = session.get('selected_client_id')
    query = Transaction.query.filter(Transaction.date >= thirty_days_ago)
    if client_id:
        query = query.filter_by(client_id=client_id)
    transactions = query.order_by(Transaction.date).all()

    daily_balances = {}
    for tx in transactions:
        date_str = tx.date.strftime('%Y-%m-%d')
        if date_str not in daily_balances:
            daily_balances[date_str] = {'USD': 0, 'EUR': 0, 'GBP': 0, 'IRR': 0, 'CAD': 0}
        daily_balances[date_str][tx.from_currency] += tx.from_amount
        daily_balances[date_str][tx.to_currency] -= tx.to_amount

    dates = sorted(daily_balances.keys())
    usd_data = [daily_balances[date].get('USD', 0) for date in dates]
    eur_data = [daily_balances[date].get('EUR', 0) for date in dates]
    chart_data = {'dates': dates, 'usd': usd_data, 'eur': eur_data}
    return render_template('charts.html', chart_data=json.dumps(chart_data))


@app.route('/delete/<tx_id>')
def delete_transaction(tx_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    tx = Transaction.query.get_or_404(tx_id)
    if not session.get('is_admin'):
        flash('Access denied!')
        return redirect(url_for('transactions'))
    db.session.delete(tx)
    db.session.commit()
    flash('✅ Transaction deleted!')
    return redirect(url_for('transactions'))


@app.route('/get_live_rate_with_fee/<from_curr>/<to_curr>')
def get_live_rate_with_fee(from_curr, to_curr):
    try:
        url = f"https://api.exchangerate-api.com/v4/latest/{from_curr}"
        response = requests.get(url)
        data = response.json()
        live_rate = data['rates'][to_curr]
        return str(round(live_rate, 10))
    except:
        return str(round(0.85, 10))


@app.route('/get_rate/<from_curr>/<to_curr>')
def get_live_rate(from_curr, to_curr):
    try:
        url = f"https://api.exchangerate-api.com/v4/latest/{from_curr}"
        response = requests.get(url)
        data = response.json()
        rate = data['rates'][to_curr]
        return str(round(rate, 4))
    except:
        return "0.85"


@app.route('/export')
def export_csv():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    search_date = request.args.get('date', '')
    search_client = request.args.get('client_name', '')
    search_from = request.args.get('from_currency', '')
    search_to = request.args.get('to_currency', '')
    search_fintrac = request.args.get('fintrac', '')
    search_status = request.args.get('status', '')

    query = Transaction.query.order_by(Transaction.date.desc())
    if session.get('is_admin'):
        all_tx = query.all()
    else:
        client_id = session.get('selected_client_id')
        if client_id:
            all_tx = query.filter_by(client_id=client_id).all()
        else:
            all_tx = []

    if search_fintrac == 'yes':
        all_tx = [tx for tx in all_tx if tx.is_fintrac]
    elif search_fintrac == 'no':
        all_tx = [tx for tx in all_tx if not tx.is_fintrac]

    if search_status == 'closed':
        all_tx = [tx for tx in all_tx if tx.status == 'closed']
    elif search_status == 'pending':
        all_tx = [tx for tx in all_tx if tx.status == 'pending']

    if search_date:
        search_date_obj = datetime.strptime(search_date, '%Y-%m-%d')
        all_tx = [tx for tx in all_tx if tx.date.date() == search_date_obj.date()]
    if search_client:
        all_tx = [tx for tx in all_tx if
                  search_client.lower() in f"{tx.client.first_name} {tx.client.last_name}".lower()]
    if search_from:
        all_tx = [tx for tx in all_tx if tx.from_currency.upper() == search_from.upper()]
    if search_to:
        all_tx = [tx for tx in all_tx if tx.to_currency.upper() == search_to.upper()]

    filename = 'transactions'
    if search_client: filename += f'_{search_client[:10]}'
    if search_from: filename += f'_{search_from}'
    if search_date: filename += f'_{search_date}'
    filename += '.csv'

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Date', 'Client', 'From', 'From Amount', 'To', 'To Amount', 'Rate', 'Notes', 'Profit'])
    total_profit = 0
    for tx in all_tx:
        profit = round((tx.from_amount * FEE_PERCENTAGE * 100) + FLAT_FEE_CAD, 2)
        total_profit += profit
        writer.writerow([
            tx.id, tx.date.strftime('%Y-%m-%d %H:%M'),
            f"{tx.client.first_name} {tx.client.last_name}",
            tx.from_currency, f"{tx.from_amount:.2f}", tx.to_currency,
            f"{tx.to_amount:.2f}", f"{tx.exchange_rate:.4f}", tx.notes or '',
            f"${profit:.2f}"
        ])
    writer.writerow([])
    writer.writerow([f'TOTAL ROWS: {len(all_tx)} | TOTAL PROFIT: ${total_profit:.2f}'])

    response = app.response_class(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment;filename={filename}'}
    )
    return response


@app.route('/deposit', methods=['GET', 'POST'])
def deposit():
    if 'user_id' not in session or not session.get('selected_client_id'):
        flash('👥 SELECT A CLIENT FIRST!')
        return redirect(url_for('index'))

    selected_client = Client.query.get(session['selected_client_id'])
    current_fee = round(FEE_PERCENTAGE * 100, 1)
    current_flat_fee = round(FLAT_FEE_CAD, 2)

    if request.method == 'POST':
        currency = request.form['currency']
        amount = float(request.form['amount'])
        notes = request.form.get('notes', f'Deposit {amount} {currency}')

        tx_id = generate_transaction_id(datetime.utcnow())

        new_tx = Transaction(
            id=tx_id,
            from_currency=currency, to_currency=currency,
            from_amount=0, to_amount=amount,
            exchange_rate=1.0, notes=notes,
            is_fintrac=(amount >= 10000),
            client_id=session['selected_client_id'],
            status=request.form.get('status', 'closed'),
        )
        db.session.add(new_tx)
        db.session.commit()
        flash(f'✅ Deposited ${amount} {currency}!')
        return redirect(url_for('deposit'))

    total_deposits = db.session.query(func.sum(Transaction.to_amount)).filter_by(
        client_id=session['selected_client_id']).scalar() or 0

    return render_template('deposit.html',
                           total_deposits=total_deposits,
                           client=selected_client,
                           current_fee=current_fee, current_flat_fee=current_flat_fee)


@app.route('/reports')
def reports():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # Get closed transactions only
    transactions = Transaction.query.filter_by(status='closed').all()

    # ✅ Initialize all variables
    daily_profit = {}
    week_total = 0
    month_total = 0
    today = datetime.utcnow().strftime('%Y-%m-%d')

    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    # Calculate daily profits
    for tx in transactions:
        date_str = tx.date.strftime('%Y-%m-%d')
        total_value = (tx.from_amount + tx.to_amount) / 2  # Average for volume
        profit = abs(tx.to_amount - (tx.from_amount * tx.exchange_rate))  # Fee profit

        if date_str not in daily_profit:
            daily_profit[date_str] = {'count': 0, 'volume': 0, 'profit': 0}

        daily_profit[date_str]['count'] += 1
        daily_profit[date_str]['volume'] += total_value
        daily_profit[date_str]['profit'] += profit

        # Time-based totals
        if tx.date >= week_ago:
            week_total += profit
        if tx.date >= month_ago:
            month_total += profit

    # Sort by date (newest first)
    sorted_daily = dict(sorted(daily_profit.items(), key=lambda x: x[0], reverse=True))

    # Current fees
    current_fee = round(FEE_PERCENTAGE * 100, 1)
    current_flat_fee = round(FLAT_FEE_CAD, 2)

    return render_template('reports.html',
                           daily_profit=sorted_daily,
                           today=today,
                           week_total=week_total,
                           month_total=month_total,
                           current_fee=current_fee,
                           current_flat_fee=current_flat_fee)


@app.route('/download_receipt/<tx_id>')
def download_receipt(tx_id):
    tx = Transaction.query.get_or_404(tx_id)
    if not tx.receipt_filename:
        flash('❌ No receipt found!')
        return redirect(url_for('transactions'))
    return send_from_directory(app.config['UPLOAD_FOLDER'], tx.receipt_filename)


@app.route('/set_fees', methods=['POST'])
def set_fees():
    if 'user_id' not in session or not session.get('is_admin'):
        return redirect(url_for('login'))
    global FEE_PERCENTAGE, FLAT_FEE_CAD
    FEE_PERCENTAGE = float(request.form['fee_percentage']) / 100
    FLAT_FEE_CAD = float(request.form['flat_fee_cad'])
    flash(f'✅ Fees: {FEE_PERCENTAGE * 100}% + ${FLAT_FEE_CAD} CAD!')
    return redirect(url_for('transactions'))


if __name__ == '__main__':
    app.run(debug=True)