

from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Define the Transaction model
class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    from_currency = db.Column(db.String(3), nullable=False)  # e.g., 'USD'
    to_currency = db.Column(db.String(3), nullable=False)    # e.g., 'EUR'
    from_amount = db.Column(db.Float, nullable=False)
    to_amount = db.Column(db.Float, nullable=False)
    exchange_rate = db.Column(db.Float, nullable=False)
    notes = db.Column(db.Text, nullable=True)

# Create the database tables (run this once)
with app.app_context():
    db.create_all()

# Helper function to compute balances per currency
def get_balances():
    transactions = Transaction.query.all()
    balances = {}
    for tx in transactions:
        # Subtract from 'from_currency'
        balances[tx.from_currency] = balances.get(tx.from_currency, 0) - tx.from_amount
        # Add to 'to_currency'
        balances[tx.to_currency] = balances.get(tx.to_currency, 0) + tx.to_amount
    return balances

# Routes below...

# ... (continue from above)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # Add new transaction from form data
        from_curr = request.form['from_currency']
        to_curr = request.form['to_currency']
        from_amt = float(request.form['from_amount'])
        rate = float(request.form['exchange_rate'])
        to_amt = from_amt * rate  # Calculate to_amount
        notes = request.form.get('notes')

        new_tx = Transaction(
            from_currency=from_curr,
            to_currency=to_curr,
            from_amount=from_amt,
            to_amount=to_amt,
            exchange_rate=rate,
            notes=notes
        )
        db.session.add(new_tx)
        db.session.commit()
        return redirect(url_for('index'))

    balances = get_balances()
    return render_template('index.html', balances=balances)

@app.route('/transactions')
def transactions():
    all_tx = Transaction.query.order_by(Transaction.date.desc()).all()
    return render_template('transactions.html', transactions=all_tx)