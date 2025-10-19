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
    transactions = db.relationship('Transaction', backref='user', lazy=True)


class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    from_currency = db.Column(db.String(3), nullable=False)
    to_currency = db.Column(db.String(3), nullable=False)
    from_amount = db.Column(db.Float, nullable=False)
    to_amount = db.Column(db.Float, nullable=False)
    exchange_rate = db.Column(db.Float, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)


with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', password='admin123', is_admin=True)
        db.session.add(admin)
        db.session.commit()
    else:
        admin = User.query.filter_by(username='admin').first()
        admin.password = 'admin123'
        db.session.commit()


def get_balances():
    if 'user_id' not in session:
        return {}
    user_id = session['user_id']
    if session.get('is_admin'):
        transactions = Transaction.query.all()
    else:
        transactions = Transaction.query.filter_by(user_id=user_id).all()
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
        print(f"DEBUG: Username={username}, Password={password}, DB={user.password if user else 'None'}")  # DEBUG
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

    if request.method == 'POST':
        mode = request.form['mode']
        fixed_curr = request.form['fixed_currency']
        fixed_amt = float(request.form['fixed_amount'])
        other_curr = request.form['other_currency']
        rate = float(request.form['exchange_rate'])
        notes = request.form.get('notes')

        if mode == 'client_fixed':
            # CLIENT GIVES $100 → GET ? EUR
            from_curr = fixed_curr
            from_amt = fixed_amt
            to_curr = other_curr
            to_amt = from_amt * rate
        else:  # bank_fixed
            # BANK GIVES €85 → GET ? USD
            from_curr = other_curr
            from_amt = fixed_amt / rate
            to_curr = fixed_curr
            to_amt = fixed_amt

        # ✅ BLOCK NEGATIVE BALANCE!
        current_balance = get_balances().get(from_curr, 0)
        if current_balance < from_amt:
            flash('invalid transaction, Low Balance')
            return render_template('index.html', balances=get_balances())

        new_tx = Transaction(
            from_currency=from_curr, to_currency=to_curr,
            from_amount=from_amt, to_amount=to_amt,
            exchange_rate=rate, notes=notes,
            user_id=session['user_id']
        )
        db.session.add(new_tx)
        db.session.commit()
        flash(f'✅ {mode.replace("_", " ").title()}: ${from_amt:.2f} {from_curr} → ${to_amt:.2f} {to_curr}')
        return redirect(url_for('index'))

    balances = get_balances()
    return render_template('index.html', balances=balances)


@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    current_user = User.query.get(session['user_id'])
    total_transactions = Transaction.query.filter_by(user_id=current_user.id).count()
    total_users = User.query.count()
    return render_template('profile.html',
                           user=current_user,
                           total_transactions=total_transactions,
                           total_users=total_users)


@app.route('/transactions')
def transactions():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    search_date = request.args.get('date', '')
    search_from = request.args.get('from_currency', '')
    search_to = request.args.get('to_currency', '')

    query = Transaction.query
    if session.get('is_admin'):
        all_tx = query.order_by(Transaction.date.desc()).all()
    else:
        all_tx = query.filter_by(user_id=session['user_id']).order_by(Transaction.date.desc()).all()

    if search_date:
        search_date_obj = datetime.strptime(search_date, '%Y-%m-%d')
        all_tx = [tx for tx in all_tx if tx.date.date() == search_date_obj.date()]
    if search_from:
        all_tx = [tx for tx in all_tx if tx.from_currency.upper() == search_from.upper()]
    if search_to:
        all_tx = [tx for tx in all_tx if tx.to_currency.upper() == search_to.upper()]

    return render_template('transactions.html', transactions=all_tx,
                           search_date=search_date, search_from=search_from, search_to=search_to)


@app.route('/charts')
def charts():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    from datetime import timedelta
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    query = Transaction.query.filter(Transaction.date >= thirty_days_ago)
    if not session.get('is_admin'):
        query = query.filter_by(user_id=session['user_id'])
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
    if not session.get('is_admin') and tx.user_id != session['user_id']:
        flash('Access denied!')
        return redirect(url_for('transactions'))
    db.session.delete(tx)
    db.session.commit()
    return redirect(url_for('transactions'))


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
    if session.get('is_admin'):
        all_tx = Transaction.query.order_by(Transaction.date.desc()).all()
    else:
        all_tx = Transaction.query.filter_by(user_id=session['user_id']).order_by(Transaction.date.desc()).all()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Date', 'From', 'From Amount', 'To', 'To Amount', 'Rate', 'Notes'])
    for tx in all_tx:
        writer.writerow([
            tx.id, tx.date.strftime('%Y-%m-%d %H:%M'), tx.from_currency,
            f"{tx.from_amount:.2f}", tx.to_currency, f"{tx.to_amount:.2f}",
            f"{tx.exchange_rate:.4f}", tx.notes or ''
        ])
    response = app.response_class(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment;filename=transactions.csv'}
    )
    return response


@app.route('/deposit', methods=['GET', 'POST'])
def deposit():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        currency = request.form['currency']
        amount = float(request.form['amount'])
        notes = request.form.get('notes', f'Deposit {amount} {currency}')

        # DEPOSIT = Positive to balance (no "from")
        new_tx = Transaction(
            from_currency=currency,
            to_currency=currency,
            from_amount=0,  # No outflow
            to_amount=amount,  # Pure inflow
            exchange_rate=1.0,
            notes=notes,
            user_id=session['user_id']
        )
        db.session.add(new_tx)
        db.session.commit()
        flash(f'✅ Deposited ${amount} {currency}!')
        return redirect(url_for('deposit'))

    current_user = User.query.get(session['user_id'])
    total_deposits = db.session.query(db.func.sum(Transaction.to_amount)).filter_by(
        user_id=current_user.id).scalar() or 0

    return render_template('deposit.html', total_deposits=total_deposits)


if __name__ == '__main__':
    app.run(debug=True)