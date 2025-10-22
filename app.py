from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
from datetime import datetime, date, timedelta
import requests
import json
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'piggybank2025'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

UPLOAD_FOLDER = 'Uploads'
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
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    apartment = db.Column(db.String(10))
    civic_number = db.Column(db.String(10), nullable=False)
    street = db.Column(db.String(100), nullable=False)
    city = db.Column(db.String(50), nullable=False)
    province = db.Column(db.String(10), nullable=False)
    postal_code = db.Column(db.String(10), nullable=False)
    id_card_number = db.Column(db.String(20))
    id_expiry_date = db.Column(db.Date)
    risk_level = db.Column(db.String(20), default='low risk')
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    transactions = db.relationship('Transaction', backref='client', lazy='dynamic')

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

# Global fees
FEE_PERCENTAGE = 0.02
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
    query = Client.query
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
    six_months_ago = datetime.utcnow() - timedelta(days=180)
    clients_data = []
    for client in clients:
        if client is None:
            print(f"DEBUG: Skipping None client in calculate_clients_data")
            continue
        try:
            # ✅ CONVERT QUERY TO LIST
            transactions_list = client.transactions.all()
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
                'transactions_list': transactions_list  # ✅ PASS LIST TO TEMPLATE
            })
            print(f"DEBUG: Client {client.email}, Volume: {total_volume_usd}, Color: {led_color}, Tx: {len(transactions_list)}")
        except AttributeError as e:
            print(f"DEBUG: Error processing client {client.id if client else 'None'}: {str(e)}")
            continue
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

@app.route('/set_fees', methods=['POST'])
def set_fees():
    if 'user_id' not in session or not session.get('is_admin'):
        return redirect(url_for('login'))
    global FEE_PERCENTAGE, FLAT_FEE_CAD
    FEE_PERCENTAGE = float(request.form['fee_percentage']) / 100
    FLAT_FEE_CAD = float(request.form['flat_fee_cad'])
    flash(f'✅ Fees: {FEE_PERCENTAGE * 100}% + ${FLAT_FEE_CAD} CAD!')
    return redirect(url_for('transactions'))


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
        # ✅ FIXED: Proper deposit vs exchange logic
        if tx.from_amount == 0:  # Pure deposit (from_amount=0)
            balances[tx.to_currency] = balances.get(tx.to_currency, 0) + tx.to_amount
        else:  # Exchange (both from_amount > 0 and to_amount > 0)
            balances[tx.from_currency] = balances.get(tx.from_currency, 0) - tx.from_amount
            balances[tx.to_currency] = balances.get(tx.to_currency, 0) + tx.to_amount
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
    if 'user_id' not in session:
        flash('🔒 Please log in first!')
        return redirect(url_for('login'))

    if request.method == 'POST':
        if not session.get('selected_client_id'):
            flash('👥 SELECT A CLIENT FIRST!')
            return redirect(url_for('customers'))

        mode = request.form['mode']
        fixed_currency = request.form['fixed_currency']
        fixed_amount = float(request.form['fixed_amount'])
        other_currency = request.form['other_currency']
        exchange_rate = float(request.form['exchange_rate'])
        notes = request.form.get('notes', '')
        is_fintrac = 'is_fintrac' in request.form
        status = request.form['status']

        if fixed_currency == other_currency:
            flash('❌ Cannot exchange same currency!')
            return redirect(url_for('index'))

        tx_id = generate_transaction_id(datetime.utcnow())

        # ✅ FIXED: Proper exchange calculation
        if mode == 'client_fixed':  # Client pays fixed amount
            from_currency = fixed_currency
            to_currency = other_currency
            from_amount = fixed_amount
            to_amount = fixed_amount * exchange_rate  # CAD → USD
        else:  # Client receives fixed amount
            from_currency = other_currency
            to_currency = fixed_currency
            to_amount = fixed_amount
            from_amount = fixed_amount / exchange_rate  # USD → CAD

        new_tx = Transaction(
            id=tx_id,
            from_currency=from_currency,
            to_currency=to_currency,
            from_amount=from_amount,
            to_amount=to_amount,
            exchange_rate=exchange_rate,
            notes=notes,
            is_fintrac=is_fintrac or (max(from_amount, to_amount) >= 10000),
            client_id=session['selected_client_id'],
            status=status
        )
        db.session.add(new_tx)
        db.session.commit()
        flash(f'✅ {from_amount:.2f} {from_currency} → {to_amount:.2f} {to_currency} ({tx_id})')
        return redirect(url_for('index'))

    # GET: Render dashboard (unchanged)
    client = None
    total_volume_usd = 0
    led_color = '#00FF00'
    if session.get('selected_client_id'):
        client = Client.query.get(session['selected_client_id'])
        if client:
            six_months_ago = datetime.utcnow() - timedelta(days=180)
            total_volume_usd = 0
            transactions_list = client.transactions.all()  # ✅ Fix for dynamic
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

    balances = get_balances()  # ✅ Use your fixed function

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
                           led_color=led_color)

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

    if request.method == 'POST':
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        email = request.form['email']
        phone = request.form['phone']
        apartment = request.form.get('apartment', '')
        civic_number = request.form['civic_number']
        street = request.form['street']
        city = request.form['city']
        province = request.form['province']
        postal_code = request.form['postal_code']
        id_card_number = request.form.get('id_card_number', '')
        id_expiry_date = request.form.get('id_expiry_date')
        risk_level = request.form['risk_level']
        notes = request.form.get('notes', '')

        existing_client = Client.query.filter_by(email=email).first()
        if existing_client:
            flash('❌ Email already exists! Please use a different email.', 'error')
            return render_template('customers.html',
                                   clients_data=calculate_clients_data(),
                                   request=request,
                                   form_data=request.form,
                                   now=datetime.utcnow().date())

        try:
            # Parse id_expiry_date to date object if provided
            parsed_expiry_date = None
            if id_expiry_date:
                parsed_expiry_date = datetime.strptime(id_expiry_date, '%Y-%m-%d').date()

            new_client = Client(
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=phone,
                apartment=apartment,
                civic_number=civic_number,
                street=street,
                city=city,
                province=province,
                postal_code=postal_code,
                id_card_number=id_card_number,
                id_expiry_date=parsed_expiry_date,  # Use parsed date
                risk_level=risk_level,
                notes=notes,
                created_at=datetime.utcnow()
            )
            db.session.add(new_client)
            db.session.commit()
            flash('✅ Customer added successfully!')
            return redirect(url_for('customers'))
        except IntegrityError:
            db.session.rollback()
            flash('❌ Email already exists! Please use a different email.', 'error')
            return render_template('customers.html',
                                   clients_data=calculate_clients_data(),
                                   request=request,
                                   form_data=request.form,
                                   now=datetime.utcnow().date())

    # GET: Display customers with BR indicator
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


@app.route('/edit_client/<int:client_id>', methods=['GET', 'POST'])
def edit_client(client_id):
    client = Client.query.get_or_404(client_id)

    if request.method == 'POST':
        client.first_name = request.form['first_name']
        client.last_name = request.form['last_name']
        client.email = request.form['email']
        client.phone = request.form['phone']
        client.apartment = request.form.get('apartment', '')
        client.civic_number = request.form['civic_number']
        client.street = request.form['street']
        client.city = request.form['city']
        client.province = request.form['province']
        client.postal_code = request.form['postal_code']
        client.id_card_number = request.form.get('id_card_number', '')

        # ✅ FIXED DATE PARSING
        id_expiry_date_str = request.form.get('id_expiry_date', '').strip()
        if id_expiry_date_str:
            try:
                client.id_expiry_date = datetime.strptime(id_expiry_date_str, '%Y-%m-%d').date()
            except ValueError:
                client.id_expiry_date = None
                flash('⚠️ Invalid expiry date format. Cleared.', 'warning')
        else:
            client.id_expiry_date = None

        client.risk_level = request.form['risk_level']
        client.notes = request.form.get('notes', '')

        try:
            db.session.commit()
            flash(f'✅ {client.first_name} {client.last_name} updated!')
            return redirect(url_for('customers'))
        except IntegrityError:
            db.session.rollback()
            flash('❌ Email already exists! Please use a different email.', 'error')
            # ✅ Form repopulation
            form_data = request.form.copy()
            return render_template('edit_client.html',
                                   client=client,
                                   form_data=form_data,
                                   now=datetime.utcnow().date())  # ✅ ADD NOW

    # ✅ GET: Render with now
    return render_template('edit_client.html',
                           client=client,
                           now=datetime.utcnow().date())  # ✅ ADD NOW



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

    current_fee = round(FEE_PERCENTAGE * 100, 1)
    current_flat_fee = round(FLAT_FEE_CAD, 2)

    return render_template('transactions.html', transactions=all_tx,
                           search_date=search_date, search_client=search_client,
                           search_from=search_from, search_to=search_to,
                           search_fintrac=search_fintrac, search_status=search_status,
                           current_fee=current_fee, current_flat_fee=current_flat_fee,
                           filtered_transactions=len(all_tx))

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
        daily_balances[date_str][tx.from_currency] -= tx.from_amount
        daily_balances[date_str][tx.to_currency] += tx.to_amount

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
        fee_multiplier = 1 + FEE_PERCENTAGE
        fee_rate = live_rate * fee_multiplier
        return str(round(fee_rate, 10))
    except:
        return str(round(0.85 * (1 + FEE_PERCENTAGE), 10))

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

    import csv
    from io import StringIO

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
    if search_client: filename += f'_John{search_client[:10]}'
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

    total_deposits = db.session.query(db.func.sum(Transaction.to_amount)).filter_by(
        client_id=session['selected_client_id']).scalar() or 0

    return render_template('deposit.html',
                           total_deposits=total_deposits,
                           client=selected_client,
                           current_fee=current_fee, current_flat_fee=current_flat_fee)

@app.route('/reports')
def reports():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    query = Transaction.query.filter(Transaction.date >= thirty_days_ago).order_by(Transaction.date.desc())
    if session.get('selected_client_id'):
        query = query.filter_by(client_id=session.get('selected_client_id'))
    transactions = query.all()

    daily_profit = {}
    for tx in transactions:
        date_str = tx.date.strftime('%Y-%m-%d')
        if date_str not in daily_profit:
            daily_profit[date_str] = {'count': 0, 'volume': 0, 'profit': 0}
        daily_profit[date_str]['count'] += 1
        daily_profit[date_str]['volume'] += tx.from_amount
        profit_per_tx = ((tx.from_amount * (FEE_PERCENTAGE * 100) / 100) + FLAT_FEE_CAD) if tx.from_amount > 0 else 0
        daily_profit[date_str]['profit'] += round(profit_per_tx, 2)

    today = datetime.utcnow().strftime('%Y-%m-%d')
    week_total = sum(daily['profit'] for daily in list(daily_profit.values())[:7])
    month_total = sum(daily['profit'] for daily in daily_profit.values())

    current_fee = round(FEE_PERCENTAGE * 100, 1)
    current_flat_fee = round(FLAT_FEE_CAD, 2)

    return render_template('reports.html',
                           daily_profit=daily_profit,
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

if __name__ == '__main__':
    app.run(debug=True)