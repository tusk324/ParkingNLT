from flask import Flask, render_template, request, redirect, url_for, send_file, jsonify, Response
import stripe
import os
import csv
import json
from datetime import datetime, time
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

# Load environment variables from .env file (useful for local development)
load_dotenv()

app = Flask(__name__)

# Set your Stripe secret key from environment variables
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

# Path to the reservation log file
RESERVATION_FILE = 'reservations.csv'

# Read the admin username and password hash from environment variables
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'default_user')
ADMIN_PASSWORD_HASH = os.getenv(
    'ADMIN_PASSWORD_HASH',
    generate_password_hash('default_password', method='pbkdf2:sha256')
)



# -------------------------------------------------
# ✅ BLACKOUT TIME FUNCTION (NEW)
# -------------------------------------------------
def booking_allowed():
    """
    Reads blackout windows from Render environment variable:

    BLACKOUT_WINDOWS

    Example value:
    [
      {"start":"00:00","end":"06:00"},
      {"start":"22:00","end":"23:59"}
    ]
    """

    raw = os.getenv("BLACKOUT_WINDOWS")

    # If nothing set → always allow
    if not raw:
        return True

    now = datetime.now().time()

    try:
        windows = json.loads(raw)

        for w in windows:
            start = time.fromisoformat(w["start"])
            end = time.fromisoformat(w["end"])

            if start <= now <= end:
                return False
    except:
        return True  # fail safe if formatting wrong

    return True


# -------------------------------------------------
# ROUTES
# -------------------------------------------------

@app.route('/')
def home():
    return render_template('index.html')


@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():

    # ✅ BLOCK BOOKINGS HERE
    if not booking_allowed():
        return "Parking is unavailable at this time.", 403

    # Get the car information from the form
    car_model = request.form.get('car_model')
    license_plate = request.form.get('license_plate')

    # Simple input validation
    if not car_model or not license_plate:
        return "Invalid input. Please enter both the car model and license plate.", 400

    # Check if the CSV file exists and has data
    file_exists = os.path.isfile(RESERVATION_FILE)

    # Open the CSV file in append mode
    with open(RESERVATION_FILE, mode='a', newline='') as file:
        writer = csv.writer(file)

        # Write headers if new
        if not file_exists or os.stat(RESERVATION_FILE).st_size == 0:
            writer.writerow(['Make', 'License Plate', 'Date and Time'])

        # Write reservation details
        writer.writerow([car_model, license_plate, datetime.now().strftime("%Y-%m-%d %H:%M:%S")])

    try:
        # Create a Stripe Checkout session
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': f"Parking for {car_model} ({license_plate})",
                    },
                    'unit_amount': 1000,
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=url_for('success', _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=url_for('cancel', _external=True),
        )

        return redirect(session.url, code=303)

    except Exception as e:
        return str(e)


@app.route('/success')
def success():
    return render_template('success.html')


@app.route('/cancel')
def cancel():
    return 'Payment canceled!'


# Admin route to view reservation records
@app.route('/admin/reservations')
def admin_view_reservations():

    auth = request.authorization

    if not auth:
        return Response(
            'Login required', 401,
            {'WWW-Authenticate': 'Basic realm="Login Required"'}
        )

    if auth.username != ADMIN_USERNAME or not check_password_hash(ADMIN_PASSWORD_HASH, auth.password):
        return Response(
            'Could not verify login', 401,
            {'WWW-Authenticate': 'Basic realm="Login Required"'}
        )

    try:
        return send_file(RESERVATION_FILE, as_attachment=True)
    except Exception as e:
        return str(e)


if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
