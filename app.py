import math
import os

import mysql.connector
from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, url_for

import real_estate_db

# Load the settings from the .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")

# --- Database settings (read from .env, never written in the code) ---
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "3306"))
DB_USER = os.environ.get("DB_USER", "root")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_NAME = os.environ.get("DB_NAME", "product_crud")

# price is DECIMAL(10, 2), so this is the largest value the column can hold.
MAX_PRICE = 99999999.99


def get_connection():
    """Open a new connection to the products database."""
    return mysql.connector.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
    )


# Realistic catalog used the first time the table is created, so the dashboard
# and the statistics have something to show. See seed_products().
DEMO_PRODUCTS = [
    ("Aurora Wireless Headphones", 249.99,
     "Over-ear noise cancelling headphones with 40-hour battery life and spatial audio."),
    ("Nebula 27-inch 4K Monitor", 619.00,
     "27-inch IPS display, 144Hz, 99% sRGB coverage and a single-cable USB-C hub."),
    ("Orbit Mechanical Keyboard", 139.50,
     "Hot-swappable 75% layout with per-key RGB and a machined aluminium case."),
    ("Pulse Ergonomic Mouse", 74.90,
     "Vertical grip mouse with 8 programmable buttons and a 70-day charge."),
    ("Vertex Laptop Stand", 58.25,
     "Anodised aluminium riser with six height positions and full airflow underneath."),
    ("Quasar 100W GaN Charger", 65.00,
     "Compact three-port charger that fast-charges a laptop and two phones at once."),
    ("Lumen Studio Webcam", 189.99,
     "4K sensor with an f/1.8 lens, hardware privacy shutter and dual noise-cancelling mics."),
    ("Comet Portable SSD 2TB", 214.75,
     "Pocket-sized NVMe drive rated 1,050 MB/s with hardware AES-256 encryption."),
    ("Solstice Desk Lamp", 96.40,
     "Adjustable colour-temperature lamp with a glare-free bar and a USB-C passthrough."),
]


def seed_products(cursor):
    """Insert the demo catalog, but only while the table is still empty.

    This keeps the seed repeatable and safe: it never duplicates rows on the
    next start, and it never touches products the user created themselves.
    """
    cursor.execute("SELECT COUNT(*) FROM products")
    row = cursor.fetchone()
    if row and row[0] > 0:
        return 0

    cursor.executemany(
        "INSERT INTO products (name, price, description) VALUES (%s, %s, %s)",
        DEMO_PRODUCTS,
    )
    return cursor.rowcount


def init_db():
    """Create the database, the products table and the demo rows if missing."""
    # First connect without a database, so we can create it if it is missing.
    connection = mysql.connector.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD
    )
    cursor = connection.cursor()
    # The name comes from .env (not from a user), so it is safe to insert here.
    cursor.execute("CREATE DATABASE IF NOT EXISTS `" + DB_NAME + "`")
    cursor.close()
    connection.close()

    # Now connect to that database and create the table.
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS products (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(120) NOT NULL,
            price DECIMAL(10, 2) NOT NULL,
            description TEXT NOT NULL
        )
        """
    )
    seeded = seed_products(cursor)
    connection.commit()
    cursor.close()

    # Real Estate schema (Phase 1): property_types, locations, agents,
    # properties, property_images, inquiries. Additive only - the legacy
    # `products` table above is untouched. See real_estate_db.py.
    re_summary = real_estate_db.init_real_estate(connection)
    connection.close()

    if seeded:
        app.logger.info("Seeded %s demo products.", seeded)
    if any(re_summary.values()):
        app.logger.info("Real estate schema seeded: %s", re_summary)


def bootstrap():
    """Prepare the database however the app was started.

    `python app.py` and `flask run` both import this module, so doing the setup
    here means the table always exists - not only when app.py is run directly.
    A database that is briefly unreachable must not stop the app from starting,
    so the failure is logged and every page still shows its own error message.
    """
    try:
        init_db()
    except mysql.connector.Error as error:
        app.logger.error("Could not initialise the database: %s", error)


bootstrap()


def get_stats():
    """Read the dashboard numbers straight from MySQL.

    Everything here comes from real aggregate queries - nothing is hard coded,
    so the cards update by themselves after every create, update and delete.
    """
    stats = {"total": 0, "total_value": 0.0, "average_price": 0.0, "latest": None}

    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(price) AS total_value,
                   AVG(price) AS average_price
            FROM products
            """
        )
        totals = cursor.fetchone() or {}

        # No created_at column exists, so the highest id is the newest product.
        cursor.execute("SELECT name FROM products ORDER BY id DESC LIMIT 1")
        latest = cursor.fetchone()

        cursor.close()
        connection.close()
    except mysql.connector.Error as error:
        # Log the technical detail for us, show nothing scary to the visitor.
        app.logger.error("Database error while loading statistics: %s", error)
        return stats

    stats["total"] = int(totals.get("total") or 0)
    # SUM and AVG are NULL while the table is still empty.
    stats["total_value"] = float(totals.get("total_value") or 0)
    stats["average_price"] = float(totals.get("average_price") or 0)
    if latest:
        stats["latest"] = latest["name"]

    return stats


@app.template_filter("money")
def money(value):
    """Format a price the way the dashboard shows it, e.g. 8420.5 -> 8,420.50"""
    try:
        return "{:,.2f}".format(float(value))
    except (TypeError, ValueError):
        return "0.00"


def get_form_data():
    """Read the product fields that were sent by the form."""
    return {
        "name": request.form.get("name", "").strip(),
        "price": request.form.get("price", "").strip(),
        "description": request.form.get("description", "").strip(),
    }


def validate(data):
    """Check the form values. Returns an error message, or None if all is fine."""
    if not data["name"]:
        return "Name is required!"
    if not data["price"]:
        return "Price is required!"
    if not data["description"]:
        return "Description is required!"

    if len(data["name"]) > 120:
        return "Name must be 120 characters or fewer!"

    try:
        price = float(data["price"])
    except ValueError:
        return "Price must be a number!"

    # float() also accepts "nan", "inf" and "1e400" - none of which the
    # DECIMAL(10, 2) column can store, so they are rejected here with a real
    # message instead of failing later as a raw database error.
    if not math.isfinite(price):
        return "Price must be a real number!"

    if price < 0:
        return "Price cannot be negative!"

    if price > MAX_PRICE:
        return "Price must be less than 100,000,000!"

    return None


# ===== READ - show all products =====
@app.route("/")
def index():
    products = []
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT id, name, price, description FROM products ORDER BY id DESC")
        products = cursor.fetchall()
        cursor.close()
        connection.close()
    except mysql.connector.Error as error:
        app.logger.error("Database error: %s", error)
        flash("Could not load the products. Please try again later.", "error")

    return render_template("index.html", products=products, stats=get_stats())


# ===== CREATE - add a new product =====
@app.route("/add", methods=["GET", "POST"])
def add_product():
    if request.method == "POST":
        data = get_form_data()

        error = validate(data)
        if error:
            flash(error, "error")
            # Stay on the page and keep what the user already typed.
            return render_template("add.html", product=data)

        try:
            connection = get_connection()
            cursor = connection.cursor()
            cursor.execute(
                "INSERT INTO products (name, price, description) VALUES (%s, %s, %s)",
                (data["name"], float(data["price"]), data["description"]),
            )
            connection.commit()
            cursor.close()
            connection.close()
        except mysql.connector.Error as error:
            app.logger.error("Database error: %s", error)
            flash("Could not save the product. Please try again later.", "error")
            return render_template("add.html", product=data)

        flash('"' + data["name"] + '" has been added!', "success")
        return redirect(url_for("index"))

    # GET - show an empty form
    empty_product = {"name": "", "price": "", "description": ""}
    return render_template("add.html", product=empty_product)


# ===== UPDATE - edit an existing product =====
@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit_product(id):
    if request.method == "POST":
        data = get_form_data()
        data["id"] = id

        error = validate(data)
        if error:
            flash(error, "error")
            return render_template("edit.html", product=data)

        try:
            connection = get_connection()
            cursor = connection.cursor()
            cursor.execute(
                "UPDATE products SET name = %s, price = %s, description = %s WHERE id = %s",
                (data["name"], float(data["price"]), data["description"], id),
            )
            connection.commit()
            updated = cursor.rowcount
            cursor.close()
            connection.close()
        except mysql.connector.Error as error:
            app.logger.error("Database error: %s", error)
            flash("Could not update the product. Please try again later.", "error")
            return render_template("edit.html", product=data)

        if updated == 0:
            flash("That product does not exist!", "error")
            return redirect(url_for("index"))

        flash('"' + data["name"] + '" has been updated!', "success")
        return redirect(url_for("index"))

    # GET - load the current values into the form
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT id, name, price, description FROM products WHERE id = %s", (id,))
        product = cursor.fetchone()
        cursor.close()
        connection.close()
    except mysql.connector.Error as error:
        app.logger.error("Database error: %s", error)
        flash("Could not load the product. Please try again later.", "error")
        return redirect(url_for("index"))

    if product is None:
        flash("That product does not exist!", "error")
        return redirect(url_for("index"))

    return render_template("edit.html", product=product)


# ===== DELETE - remove a product =====
@app.route("/delete/<int:id>", methods=["POST"])
def delete_product(id):
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute("DELETE FROM products WHERE id = %s", (id,))
        connection.commit()
        deleted = cursor.rowcount
        cursor.close()
        connection.close()
    except mysql.connector.Error as error:
        app.logger.error("Database error: %s", error)
        flash("Could not delete the product. Please try again later.", "error")
        return redirect(url_for("index"))

    if deleted == 0:
        flash("That product does not exist!", "error")
    else:
        flash("The product has been deleted!", "success")

    return redirect(url_for("index"))


# ===== Handle unknown pages / invalid product ids =====
@app.errorhandler(404)
def page_not_found(error):
    flash("That page does not exist!", "error")
    return redirect(url_for("index"))


# ===== Handle a wrong method, e.g. opening /delete/1 in the address bar =====
@app.errorhandler(405)
def method_not_allowed(error):
    # Delete is POST only, so reaching it any other way lands back on the
    # catalog inside our own design instead of on the default error page.
    flash("That action has to be done from the page itself!", "error")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)
