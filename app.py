from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import requests
import json
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = 'piggybank2025'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    transactions = db.relationship('Transaction', backref='client', lazy=True)


class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    from_currency = db.Column(db.String(3), nullable=False)
    to_currency = db.Column(db.String(3), nullable=False)
    from_amount = db.Column(db.Float, nullable=False)
    to_amount = db.Column(db.Float, nullable=False)
    exchange_rate = db.Column(db.Float, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)


with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', password='admin123', is_admin=True)
        db.session.add(admin)
        db.session.commit()

# ✅ GLOBAL FEES
FEE_PERCENTAGE = 0.02
FLAT_FEE_CAD = 5.0


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
        balances[tx.from_currency] = balances.get(tx.from_currency, 0) - tx.from_amount
        balances[tx.to_currency] = balances.get(tx.to_currency, 0) + tx.to_amount
    return balances


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
        return redirect(url_for('login'))

    current_fee = round(FEE_PERCENTAGE * 100, 1)
    current_flat_fee = round(FLAT_FEE_CAD, 2)
    selected_client = Client.query.get(session.get('selected_client_id'))

    if request.method == 'POST':
        if not session.get('selected_client_id'):
            flash('👥 SELECT A CLIENT FIRST!')
            return render_template('index.html', balances=get_balances(), current_fee=current_fee,
                                   current_flat_fee=current_flat_fee, client=selected_client)

        mode = request.form['mode']
        fixed_curr = request.form['fixed_currency']
        fixed_amt = float(request.form['fixed_amount'])
        other_curr = request.form['other_currency']
        rate = float(request.form['exchange_rate'])
        notes = request.form.get('notes', f'For {selected_client.first_name} {selected_client.last_name}')

        if mode == 'client_fixed':
            from_curr = fixed_curr
            from_amt = fixed_amt
            to_curr = other_curr
            to_amt = from_amt * rate
        else:
            from_curr = other_curr
            from_amt = fixed_amt / rate
            to_curr = fixed_curr
            to_amt = fixed_amt

        current_balance = get_balances().get(from_curr, 0)
        if current_balance < from_amt:
            flash('❌ Low Balance!')
            return render_template('index.html', balances=get_balances(), current_fee=current_fee,
                                   current_flat_fee=current_flat_fee, client=selected_client)

        new_tx = Transaction(
            from_currency=from_curr, to_currency=to_curr,
            from_amount=from_amt, to_amount=to_amt,
            exchange_rate=rate, notes=notes,
            client_id=session['selected_client_id']
        )
        db.session.add(new_tx)
        db.session.commit()
        flash(f'✅ {mode.replace("_", " ").title()}: ${from_amt:.2f} {from_curr} → ${to_amt:.2f} {to_curr}')
        return redirect(url_for('index'))

    balances = get_balances()
    return render_template('index.html', balances=balances, current_fee=current_fee,
                           current_flat_fee=current_flat_fee, client=selected_client)


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
        return redirect(url_for('login'))

    search_query = request.args.get('search', '')

    if request.method == 'POST':
        new_client = Client(
            first_name=request.form['first_name'],
            last_name=request.form['last_name'],
            email=request.form['email'],
            phone=request.form['phone'],
            apartment=request.form.get('apartment'),
            civic_number=request.form['civic_number'],
            street=request.form['street'],
            city=request.form['city'],
            province=request.form['province'],
            postal_code=request.form['postal_code']
        )
        db.session.add(new_client)
        db.session.commit()
        flash(f'✅ Customer {new_client.first_name} {new_client.last_name} added!')
        return redirect(url_for('customers'))

    if search_query:
        all_clients = Client.query.filter(
            db.or_(
                Client.first_name.ilike(f'%{search_query}%'),
                Client.last_name.ilike(f'%{search_query}%'),
                Client.email.ilike(f'%{search_query}%'),
                Client.phone.ilike(f'%{search_query}%')
            )
        ).order_by(Client.last_name).all()
    else:
        all_clients = Client.query.order_by(Client.last_name).all()

    return render_template('customers.html', clients=all_clients)


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
        client.apartment = request.form.get('apartment')
        client.civic_number = request.form['civic_number']
        client.street = request.form['street']
        client.city = request.form['city']
        client.province = request.form['province']
        client.postal_code = request.form['postal_code']
        db.session.commit()
        flash(f'✅ {client.first_name} {client.last_name} updated!')
        return redirect(url_for('customers'))
    return render_template('edit_client.html', client=client)


@app.route('/edit_transaction/<int:tx_id>', methods=['GET', 'POST'])
def edit_transaction(tx_id):
    tx = Transaction.query.get_or_404(tx_id)
    if request.method == 'POST':
        tx.from_amount = float(request.form['from_amount'])
        tx.to_amount = tx.from_amount * float(request.form['exchange_rate'])
        tx.exchange_rate = float(request.form['exchange_rate'])
        tx.notes = request.form.get('notes')
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

    query = Transaction.query.order_by(Transaction.date.desc())
    if session.get('is_admin'):
        all_tx = query.all()
    else:
        client_id = session.get('selected_client_id')
        if client_id:
            all_tx = query.filter_by(client_id=client_id).all()
        else:
            all_tx = []

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
    current_fee = round(FEE_PERCENTAGE * 100, 1)
    current_flat_fee = round(FLAT_FEE_CAD, 2)

    # ✅ PASS FILTERED DATA TO CSV!
    return render_template('transactions.html', transactions=all_tx,
                           search_date=search_date, search_client=search_client,
                           search_from=search_from, search_to=search_to,
                           current_fee=current_fee, current_flat_fee=current_flat_fee,
                           filtered_transactions=len(all_tx))  # ✅ NEW!


@app.route('/charts')
def charts():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    from datetime import timedelta
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


@app.route('/delete/<int:tx_id>')
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
        # ✅ 10 DECIMALS!
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

    # ✅ GET SAME FILTERS AS TABLE!
    search_date = request.args.get('date', '')
    search_client = request.args.get('client_name', '')
    search_from = request.args.get('from_currency', '')
    search_to = request.args.get('to_currency', '')

    # ✅ SAME QUERY AS TRANSACTIONS TABLE!
    query = Transaction.query.order_by(Transaction.date.desc())
    if session.get('is_admin'):
        all_tx = query.all()
    else:
        client_id = session.get('selected_client_id')
        if client_id:
            all_tx = query.filter_by(client_id=client_id).all()
        else:
            all_tx = []

    # ✅ APPLY SAME FILTERS!
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

    # ✅ DYNAMIC FILENAME!
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
    writer.writerow([])  # Blank line
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

        new_tx = Transaction(
            from_currency=currency,
            to_currency=currency,
            from_amount=0,
            to_amount=amount,
            exchange_rate=1.0,
            notes=notes,
            client_id=session['selected_client_id']
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

    # ✅ DAILY PROFIT DATA (30 DAYS)
    from datetime import timedelta
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
        daily_profit[date_str]['profit'] += round((tx.from_amount * FEE_PERCENTAGE * 100) + FLAT_FEE_CAD, 2)

    # ✅ TODAY HIGHLIGHT
    today = datetime.now().strftime('%Y-%m-%d')
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


if __name__ == '__main__':
    app.run(debug=True)