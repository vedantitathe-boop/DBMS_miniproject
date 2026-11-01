import os
from functools import wraps
import mysql.connector
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from mysql.connector.errors import IntegrityError
from dotenv import load_dotenv
from db import get_db, get_demo_db, fetch_all, fetch_one, execute
from queries import DEMO_QUERIES

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first.')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper
def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get('role') != 'Admin':
            flash('Admin access only.')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return wrapper


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['full_name'].strip()
        email = request.form['email'].strip().lower()
        phone = request.form['phone'].strip() or None
        password = request.form['password']
        try:
            execute(
                'INSERT INTO Users (full_name, email, password_hash, phone) '
                'VALUES (%s, %s, %s, %s)',
                (name, email, generate_password_hash(password), phone))
        except IntegrityError:
            # the UNIQUE constraint on email rejected a duplicate
            flash('That email is already registered.')
            return redirect(url_for('register'))
        flash('Account created. Please log in.')
        return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        user = fetch_one('SELECT * FROM Users WHERE email = %s', (email,))
        if user and check_password_hash(user['password_hash'], request.form['password']):
            session['user_id'] = user['user_id']
            session['name'] = user['full_name']
            session['role'] = user['role']
            return redirect(url_for('index'))
        flash('Wrong email or password.')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/sell', methods=['GET', 'POST'])
@login_required
def sell():
    if request.method == 'POST':
        conn = get_db()
        try:
            cur = conn.cursor()
            # 1. register the physical device
            cur.execute(
                'INSERT INTO Devices (owner_id, model_id, device_condition, years_used, description) '
                'VALUES (%s, %s, %s, %s, %s)',
                (session['user_id'], request.form['model_id'],
                 request.form['device_condition'], request.form['years_used'],
                 request.form['description'].strip() or None))
            device_id = cur.lastrowid
            # 2. create its listing; it starts as Pending until an admin approves it
            cur.execute(
                'INSERT INTO Listings (device_id, listing_type, asking_price) '
                'VALUES (%s, %s, %s)',
                (device_id, request.form['listing_type'], request.form['asking_price']))
            conn.commit()          # both inserts saved together
            flash('Listing submitted. It will appear after admin approval.')
        except mysql.connector.Error as e:
            conn.rollback()        # neither insert is saved
            flash('Could not save the listing: ' + str(e))
        finally:
            conn.close()
        return redirect(url_for('sell'))

    models = fetch_all('SELECT model_id, brand, model_name FROM DeviceModels '
                       'ORDER BY brand, model_name')
    mine = fetch_all(
        'SELECT L.listing_id, DM.brand, DM.model_name, L.asking_price, '
        '       L.listing_status, L.rejection_reason '
        'FROM Listings L '
        'JOIN Devices D ON L.device_id = D.device_id '
        'JOIN DeviceModels DM ON D.model_id = DM.model_id '
        'WHERE D.owner_id = %s ORDER BY L.listing_id DESC', (session['user_id'],))
    return render_template('sell.html', models=models, mine=mine)
@app.route('/admin')
@admin_required
def admin():
    pending = fetch_all(
        'SELECT P.listing_id, P.brand, P.model_name, P.asking_price, '
        '       P.estimated_value, P.price_flag, U.full_name AS seller, '
        '       D.device_condition, D.years_used '
        'FROM PriceCheck P '
        'JOIN Listings L ON P.listing_id = L.listing_id '
        'JOIN Devices D ON L.device_id = D.device_id '
        'JOIN Users U ON D.owner_id = U.user_id '
        "WHERE P.listing_status = 'Pending' ORDER BY P.listing_id")
    return render_template('admin.html', pending=pending)


@app.route('/admin/approve/<int:listing_id>', methods=['POST'])
@admin_required
def approve(listing_id):
    execute("UPDATE Listings SET listing_status = 'Available', "
            "reviewed_by = %s, reviewed_at = NOW() "
            "WHERE listing_id = %s AND listing_status = 'Pending'",
            (session['user_id'], listing_id))
    flash(f'Listing {listing_id} approved.')
    return redirect(url_for('admin'))


@app.route('/admin/reject/<int:listing_id>', methods=['POST'])
@admin_required
def reject(listing_id):
    reason = request.form['reason'].strip() or None
    try:
        execute("UPDATE Listings SET listing_status = 'Rejected', "
                "reviewed_by = %s, reviewed_at = NOW(), rejection_reason = %s "
                "WHERE listing_id = %s AND listing_status = 'Pending'",
                (session['user_id'], reason, listing_id))
        flash(f'Listing {listing_id} rejected.')
    except mysql.connector.Error as e:
        # chk_rejected: a rejection without a reason is refused by the database
        flash('Rejection not saved: ' + str(e))
    return redirect(url_for('admin'))

@app.route('/buy')
@login_required
def buy():
    category = request.args.get('category', '')
    sql = ('SELECT A.*, D.owner_id '
           'FROM AvailableListings A '
           'JOIN Listings L ON A.listing_id = L.listing_id '
           'JOIN Devices D ON L.device_id = D.device_id ')
    params = ()
    if category:
        sql += 'WHERE A.device_category = %s '
        params = (category,)
    sql += 'ORDER BY A.listing_id'
    listings = fetch_all(sql, params)
    categories = fetch_all('SELECT DISTINCT device_category FROM DeviceModels '
                           'ORDER BY device_category')
    return render_template('buy.html', listings=listings,
                           categories=categories, selected=category)


@app.route('/buy/request/<int:listing_id>', methods=['POST'])
@login_required
def request_purchase(listing_id):
    row = fetch_one(
        'SELECT D.owner_id FROM Listings L '
        'JOIN Devices D ON L.device_id = D.device_id '
        "WHERE L.listing_id = %s AND L.listing_status = 'Available'", (listing_id,))
    if not row:
        flash('That listing is no longer available.')
        return redirect(url_for('buy'))
    if row['owner_id'] == session['user_id']:
        flash('You cannot buy your own listing.')
        return redirect(url_for('buy'))
    already = fetch_one(
        'SELECT transaction_id FROM Transactions '
        "WHERE listing_id = %s AND buyer_id = %s AND transaction_status = 'Requested'",
        (listing_id, session['user_id']))
    if already:
        flash('You have already sent a request for this listing.')
        return redirect(url_for('buy'))
    try:
        execute('INSERT INTO Transactions (listing_id, buyer_id, final_price) '
                'VALUES (%s, %s, %s)',
                (listing_id, session['user_id'], request.form['offer']))
        flash('Request sent to the seller.')
    except mysql.connector.Error as e:
        # chk_final_price refuses a price of zero or less
        flash('Request not saved: ' + str(e))
    return redirect(url_for('buy'))
@app.context_processor
def inject_counts():
    # number of purchase requests waiting on the logged-in user's listings
    if 'user_id' in session:
        row = fetch_one(
            'SELECT COUNT(*) AS n FROM Transactions T '
            'JOIN Listings L ON T.listing_id = L.listing_id '
            'JOIN Devices D ON L.device_id = D.device_id '
            "WHERE D.owner_id = %s AND T.transaction_status = 'Requested'",
            (session['user_id'],))
        return {'incoming_count': row['n']}
    return {'incoming_count': 0}


@app.route('/activity')
@login_required
def activity():
    incoming = fetch_all(
        'SELECT T.transaction_id, T.final_price, T.transaction_status, '
        '       DM.brand, DM.model_name, L.asking_price, U.full_name AS buyer '
        'FROM Transactions T '
        'JOIN Listings L ON T.listing_id = L.listing_id '
        'JOIN Devices D ON L.device_id = D.device_id '
        'JOIN DeviceModels DM ON D.model_id = DM.model_id '
        'JOIN Users U ON T.buyer_id = U.user_id '
        'WHERE D.owner_id = %s ORDER BY T.transaction_id DESC',
        (session['user_id'],))
    outgoing = fetch_all(
        'SELECT T.transaction_id, T.final_price, T.transaction_status, '
        '       DM.brand, DM.model_name, U.full_name AS seller '
        'FROM Transactions T '
        'JOIN Listings L ON T.listing_id = L.listing_id '
        'JOIN Devices D ON L.device_id = D.device_id '
        'JOIN DeviceModels DM ON D.model_id = DM.model_id '
        'JOIN Users U ON D.owner_id = U.user_id '
        'WHERE T.buyer_id = %s ORDER BY T.transaction_id DESC',
        (session['user_id'],))
    return render_template('activity.html', incoming=incoming, outgoing=outgoing)


@app.route('/activity/accept/<int:transaction_id>', methods=['POST'])
@login_required
def accept_request(transaction_id):
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        # lock the rows so two sellers/clicks cannot accept at the same time
        cur.execute(
            'SELECT T.listing_id, D.owner_id, T.transaction_status, L.listing_status '
            'FROM Transactions T '
            'JOIN Listings L ON T.listing_id = L.listing_id '
            'JOIN Devices D ON L.device_id = D.device_id '
            'WHERE T.transaction_id = %s FOR UPDATE', (transaction_id,))
        row = cur.fetchone()
        if (not row or row['owner_id'] != session['user_id']
                or row['transaction_status'] != 'Requested'
                or row['listing_status'] != 'Available'):
            conn.rollback()
            flash('This request can no longer be accepted.')
            return redirect(url_for('activity'))
        # three changes that must happen together
        cur.execute("UPDATE Transactions SET transaction_status = 'Completed' "
                    'WHERE transaction_id = %s', (transaction_id,))
        cur.execute("UPDATE Listings SET listing_status = 'Sold' "
                    'WHERE listing_id = %s', (row['listing_id'],))
        cur.execute("UPDATE Transactions SET transaction_status = 'Cancelled' "
                    "WHERE listing_id = %s AND transaction_id <> %s "
                    "AND transaction_status = 'Requested'",
                    (row['listing_id'], transaction_id))
        conn.commit()
        flash('Sale completed. Other requests for this listing were cancelled.')
    except mysql.connector.Error as e:
        conn.rollback()
        flash('Could not complete the sale: ' + str(e))
    finally:
        conn.close()
    return redirect(url_for('activity'))


@app.route('/activity/decline/<int:transaction_id>', methods=['POST'])
@login_required
def decline_request(transaction_id):
    execute(
        "UPDATE Transactions T "
        "JOIN Listings L ON T.listing_id = L.listing_id "
        "JOIN Devices D ON L.device_id = D.device_id "
        "SET T.transaction_status = 'Cancelled' "
        "WHERE T.transaction_id = %s AND D.owner_id = %s "
        "AND T.transaction_status = 'Requested'",
        (transaction_id, session['user_id']))
    flash('Request declined.')
    return redirect(url_for('activity'))
@app.route('/ewaste', methods=['GET', 'POST'])
@login_required
def ewaste():
    if request.method == 'POST':
        device_id = request.form.get('device_id') or None
        item_name = request.form['item_name'].strip() or None
        if device_id:
            owned = fetch_one('SELECT device_id FROM Devices WHERE device_id = %s AND owner_id = %s',
                              (device_id, session['user_id']))
            if not owned:
                flash('That device is not yours.')
                return redirect(url_for('ewaste'))

            open_listing = fetch_one(
                'SELECT listing_id FROM Listings WHERE device_id = %s '
                "AND listing_status IN ('Pending', 'Available')", (device_id,))
            if open_listing:
                flash('This device has an open listing. Withdraw the listing before reporting it as e-waste.')
                return redirect(url_for('ewaste'))
            
        try:
            execute('INSERT INTO EwasteRecords (reported_by, device_id, item_name, item_type, reason) '
                    'VALUES (%s, %s, %s, %s, %s)',
                    (session['user_id'], device_id, item_name,
                     request.form['item_type'], request.form['reason']))
            flash('E-waste reported.')
        except mysql.connector.Error as e:
            # chk_item_identified refuses a report with no device and no item name
            flash('Report not saved: ' + str(e))
        return redirect(url_for('ewaste'))

    # my devices that are not already reported and have no open listing
    devices = fetch_all(
        'SELECT D.device_id, DM.brand, DM.model_name FROM Devices D '
        'JOIN DeviceModels DM ON D.model_id = DM.model_id '
        'WHERE D.owner_id = %s '
        'AND NOT EXISTS (SELECT 1 FROM EwasteRecords E WHERE E.device_id = D.device_id) '
        "AND NOT EXISTS (SELECT 1 FROM Listings L WHERE L.device_id = D.device_id "
        "               AND L.listing_status IN ('Pending', 'Available'))",
        (session['user_id'],))
    mine = fetch_all(
        "SELECT E.ewaste_id, COALESCE(E.item_name, CONCAT(DM.brand, ' ', DM.model_name)) AS item, "
        '       E.item_type, E.reason, E.recycling_status, E.reported_at '
        'FROM EwasteRecords E '
        'LEFT JOIN Devices D ON E.device_id = D.device_id '
        'LEFT JOIN DeviceModels DM ON D.model_id = DM.model_id '
        'WHERE E.reported_by = %s ORDER BY E.ewaste_id DESC', (session['user_id'],))
    everyone = []
    if session.get('role') == 'Admin':
        everyone = fetch_all(
            "SELECT E.ewaste_id, COALESCE(E.item_name, CONCAT(DM.brand, ' ', DM.model_name)) AS item, "
            '       U.full_name AS reporter, E.item_type, E.reason, E.recycling_status '
            'FROM EwasteRecords E '
            'JOIN Users U ON E.reported_by = U.user_id '
            'LEFT JOIN Devices D ON E.device_id = D.device_id '
            'LEFT JOIN DeviceModels DM ON D.model_id = DM.model_id '
            'ORDER BY E.ewaste_id')
    return render_template('ewaste.html', devices=devices, mine=mine, everyone=everyone)


@app.route('/admin/ewaste/<int:ewaste_id>', methods=['POST'])
@admin_required
def update_ewaste(ewaste_id):
    status = request.form['status']
    if status in ('Submitted', 'Under Assessment', 'Sent for Recycling', 'Recycled'):
        execute('UPDATE EwasteRecords SET recycling_status = %s WHERE ewaste_id = %s',
                (status, ewaste_id))
        flash(f'E-waste record {ewaste_id} is now: {status}.')
    return redirect(url_for('ewaste'))
@app.route('/demo')
@login_required
def demo():
    results = []
    conn = get_demo_db()          # read-only account, never the main one
    try:
        cur = conn.cursor()
        cur.execute('SELECT CURRENT_USER()')
        account = cur.fetchone()[0]
        for i, q in enumerate(DEMO_QUERIES, 1):
            item = dict(q, number=i, columns=[], rows=[], error=None)
            try:
                cur.execute(q['sql'])
                item['columns'] = [c[0] for c in cur.description]
                item['rows'] = cur.fetchall()
            except mysql.connector.Error as e:
                item['error'] = str(e)
            results.append(item)
    finally:
        conn.close()
    return render_template('demo.html', results=results, account=account)


@app.route('/demo/try-delete', methods=['POST'])
@login_required
def demo_try_delete():
    # Proves the demo account cannot change data. MySQL checks privileges
    # before running the statement, so nothing is ever deleted.
    conn = get_demo_db()
    try:
        cur = conn.cursor()
        cur.execute('DELETE FROM Users')
        conn.commit()
        flash('Unexpected: the delete was allowed.')
    except mysql.connector.Error as e:
        flash('MySQL refused the DELETE: ' + str(e))
    finally:
        conn.close()
    return redirect(url_for('demo'))
if __name__ == '__main__':
    app.run(debug=True)