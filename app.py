

from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import requests

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
    # Get search parameters
    search_date = request.args.get('date', '')
    search_from = request.args.get('from_currency', '')
    search_to = request.args.get('to_currency', '')

    # Start with all transactions
    all_tx = Transaction.query.order_by(Transaction.date.desc()).all()

    # Filter by date
    if search_date:
        from datetime import datetime
        search_date_obj = datetime.strptime(search_date, '%Y-%m-%d')
        all_tx = [tx for tx in all_tx if tx.date.date() == search_date_obj.date()]

    # Filter by FROM currency
    if search_from:
        all_tx = [tx for tx in all_tx if tx.from_currency.upper() == search_from.upper()]

    # Filter by TO currency
    if search_to:
        all_tx = [tx for tx in all_tx if tx.to_currency.upper() == search_to.upper()]

    return render_template('transactions.html', transactions=all_tx,
                           search_date=search_date, search_from=search_from, search_to=search_to)


@app.route('/delete/<int:tx_id>')
def delete_transaction(tx_id):
    tx = Transaction.query.get_or_404(tx_id)
    db.session.delete(tx)
    db.session.commit()
    return redirect(url_for('transactions'))

# ADD THIS NEW ROUTE (copy exactly)
@app.route('/export_csv')
def export_csv():
        import csv
        from io import StringIO
        import sys

        all_tx = Transaction.query.order_by(Transaction.date.desc()).all()

        output = StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow(['ID', 'Date', 'From', 'From Amount', 'To', 'To Amount', 'Rate', 'Notes'])

        # Data
        for tx in all_tx:
            writer.writerow([
                tx.id,
                tx.date.strftime('%Y-%m-%d %H:%M'),
                tx.from_currency,
                f"{tx.from_amount:.2f}",
                tx.to_currency,
                f"{tx.to_amount:.2f}",
                f"{tx.exchange_rate:.4f}",
                tx.notes or ''
            ])

        response = app.response_class(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment;filename=transactions.csv'}
        )
        return response
@app.route('/get_rate/<from_curr>/<to_curr>')
def get_live_rate(from_curr, to_curr):
    try:
        # Free API - updates every 60 seconds
        url = f"https://api.exchangerate-api.com/v4/latest/{from_curr}"
        response = requests.get(url)
        data = response.json()
        rate = data['rates'][to_curr]
        return str(round(rate, 4))
    except:
        return "0.85"  # Fallback


@app.route('/charts')
def charts():
    from datetime import datetime, timedelta
    import json

    # Get last 30 days data
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    transactions = Transaction.query.filter(Transaction.date >= thirty_days_ago).order_by(Transaction.date).all()

    # Calculate daily balances
    daily_balances = {}
    for tx in transactions:
        date_str = tx.date.strftime('%Y-%m-%d')
        if date_str not in daily_balances:
            daily_balances[date_str] = {'USD': 0, 'EUR': 0, 'GBP': 0, 'IRR': 0, 'CAD': 0}

        daily_balances[date_str][tx.from_currency] -= tx.from_amount
        daily_balances[date_str][tx.to_currency] += tx.to_amount

    # Format for chart
    dates = sorted(daily_balances.keys())
    usd_data = [daily_balances[date].get('USD', 0) for date in dates]
    eur_data = [daily_balances[date].get('EUR', 0) for date in dates]

    chart_data = {
        'dates': dates,
        'usd': usd_data,
        'eur': eur_data
    }

    return render_template('charts.html', chart_data=json.dumps(chart_data))

if __name__ == '__main__':
    app.run(debug=True)