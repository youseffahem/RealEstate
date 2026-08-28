import datetime
import decimal
import math
import os

import mysql.connector
from dotenv import load_dotenv
from flask import Flask, flash, jsonify, redirect, render_template, request, url_for

import property_queries
import property_validation
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
    if _wants_json():
        return jsonify({"error": "That page does not exist."}), 404
    flash("That page does not exist!", "error")
    return redirect(url_for("index"))


# ===== Handle a wrong method, e.g. opening /delete/1 in the address bar =====
@app.errorhandler(405)
def method_not_allowed(error):
    if _wants_json():
        return jsonify({"error": "That method is not allowed on this URL."}), 405
    # Delete is POST only, so reaching it any other way lands back on the
    # catalog inside our own design instead of on the default error page.
    flash("That action has to be done from the page itself!", "error")
    return redirect(url_for("index"))


# =====================================================================
# PHASE 2 - REAL ESTATE BACKEND
# =====================================================================
#
# The routes below are the backend of the REAL ESTATE Management
# System: full CRUD for `properties`, plus the reference data (property
# types, locations, agents) and dashboard statistics a future UI needs.
#
# The visual system is frozen for this phase and none of the existing
# templates model a property (title, type, location, agent, listing type,
# area, bedrooms/bathrooms...), and index.html/add.html/edit.html hard-code
# url_for('edit_product'/'delete_product') links that would silently point
# a "property" row at the unrelated legacy product with the same id. Rather
# than force property data through a template built for a different shape
# and quietly break those links, these routes are a small JSON API - a
# real, working backend layer that Phase 3 can wire a dedicated UI onto
# without ever having needed to touch app.py again. See the Phase 2 report
# for the full reasoning.


def _wants_json():
    """True for the new /properties API, so its own error responses are
    JSON instead of the legacy flash-and-redirect used by the product
    pages. Non-/properties URLs (typos, old bookmarks, etc.) keep the
    existing behaviour untouched."""
    return request.path.startswith("/properties")


def _json_safe(value):
    """Make a database value JSON-serialisable: DECIMAL -> float,
    TIMESTAMP -> ISO 8601 text. Everything else passes through unchanged."""
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    return value


def _serialize_property(row):
    """A property row (from property_queries) as a plain JSON-ready dict."""
    return {key: _json_safe(value) for key, value in row.items()}


def get_property_form_data():
    """Read the property fields sent by the form/JSON body."""
    return {
        "title": request.form.get("title", ""),
        "description": request.form.get("description", ""),
        "property_type_id": request.form.get("property_type_id", ""),
        "location_id": request.form.get("location_id", ""),
        "agent_id": request.form.get("agent_id", ""),
        "listing_type": request.form.get("listing_type", ""),
        "price": request.form.get("price", ""),
        "area_sqm": request.form.get("area_sqm", ""),
        "bedrooms": request.form.get("bedrooms", ""),
        "bathrooms": request.form.get("bathrooms", ""),
        "status": request.form.get("status", ""),
    }


def _property_filters_from_query_string():
    """Turn ?status=Available&min_price=100000... into the filters dict
    property_queries.get_all_properties() understands. Anything missing or
    malformed is simply left out - filtering is best-effort, it never 500s."""
    args = request.args
    filters = {}

    if args.get("status"):
        filters["status"] = args["status"]
    if args.get("listing_type"):
        filters["listing_type"] = args["listing_type"]
    if args.get("q"):
        filters["q"] = args["q"]

    for key in ("property_type_id", "location_id"):
        raw = args.get(key)
        if raw:
            try:
                filters[key] = int(raw)
            except ValueError:
                pass

    for key in ("min_price", "max_price", "min_area", "max_area"):
        raw = args.get(key)
        if raw:
            try:
                filters[key] = float(raw)
            except ValueError:
                pass

    return filters


def _reference_payload(reference):
    """Reference data plus the fixed enum choices, ready for jsonify."""
    payload = dict(reference)
    payload["listing_types"] = list(property_validation.LISTING_TYPES)
    payload["statuses"] = list(property_validation.STATUSES)
    return payload


# ===== READ - list properties, with optional filters =====
@app.route("/properties")
def properties_list():
    try:
        connection = get_connection()
        rows = property_queries.get_all_properties(connection, _property_filters_from_query_string())
        connection.close()
    except mysql.connector.Error as error:
        app.logger.error("Database error while listing properties: %s", error)
        return jsonify({"error": "Could not load the properties. Please try again later."}), 500

    return jsonify({
        "count": len(rows),
        "properties": [_serialize_property(row) for row in rows],
    })


# ===== READ - dashboard statistics (see property_queries.get_property_stats) =====
@app.route("/properties/stats")
def properties_stats():
    try:
        connection = get_connection()
        stats = property_queries.get_property_stats(connection)
        connection.close()
    except mysql.connector.Error as error:
        app.logger.error("Database error while loading property statistics: %s", error)
        return jsonify({"error": "Could not load the statistics. Please try again later."}), 500

    return jsonify(stats)


# ===== READ - one property, joined with its type/location/agent =====
@app.route("/properties/<int:id>")
def property_detail(id):
    try:
        connection = get_connection()
        row = property_queries.get_property_by_id(connection, id)
        connection.close()
    except mysql.connector.Error as error:
        app.logger.error("Database error while loading property %s: %s", id, error)
        return jsonify({"error": "Could not load this property. Please try again later."}), 500

    if row is None:
        return jsonify({"error": "That property does not exist."}), 404

    return jsonify({"property": _serialize_property(row)})


# ===== CREATE - add a new property =====
@app.route("/properties/add", methods=["GET", "POST"])
def properties_add():
    try:
        connection = get_connection()
    except mysql.connector.Error as error:
        app.logger.error("Database error: %s", error)
        return jsonify({"error": "The database is unavailable. Please try again later."}), 500

    if request.method == "GET":
        reference = property_queries.get_reference_data(connection)
        connection.close()
        return jsonify(_reference_payload(reference))

    try:
        valid_ids = property_queries.get_valid_ids(connection)
        errors, cleaned = property_validation.validate_property_payload(
            get_property_form_data(), valid_ids
        )
        if errors:
            connection.close()
            return jsonify({"errors": errors}), 400

        new_id = property_queries.create_property(connection, cleaned)
    except mysql.connector.Error as error:
        app.logger.error("Database error while creating a property: %s", error)
        return jsonify({"error": "Could not save the property. Please try again later."}), 500
    finally:
        connection.close()

    return redirect(url_for("property_detail", id=new_id), code=303)


# ===== UPDATE - edit an existing property =====
@app.route("/properties/edit/<int:id>", methods=["GET", "POST"])
def properties_edit(id):
    try:
        connection = get_connection()
    except mysql.connector.Error as error:
        app.logger.error("Database error: %s", error)
        return jsonify({"error": "The database is unavailable. Please try again later."}), 500

    if request.method == "GET":
        row = property_queries.get_property_by_id(connection, id)
        if row is None:
            connection.close()
            return jsonify({"error": "That property does not exist."}), 404
        reference = property_queries.get_reference_data(connection)
        connection.close()
        payload = _reference_payload(reference)
        payload["property"] = _serialize_property(row)
        return jsonify(payload)

    try:
        existing = property_queries.get_property_by_id(connection, id)
        if existing is None:
            connection.close()
            return jsonify({"error": "That property does not exist."}), 404

        valid_ids = property_queries.get_valid_ids(connection)
        errors, cleaned = property_validation.validate_property_payload(
            get_property_form_data(), valid_ids
        )
        if errors:
            connection.close()
            return jsonify({"errors": errors}), 400

        property_queries.update_property(connection, id, cleaned)
    except mysql.connector.Error as error:
        app.logger.error("Database error while updating property %s: %s", id, error)
        return jsonify({"error": "Could not update the property. Please try again later."}), 500
    finally:
        connection.close()

    return redirect(url_for("property_detail", id=id), code=303)


# ===== DELETE - remove a property (POST only - never on GET) =====
@app.route("/properties/delete/<int:id>", methods=["POST"])
def properties_delete(id):
    try:
        connection = get_connection()
        deleted = property_queries.delete_property(connection, id)
        connection.close()
    except mysql.connector.Error as error:
        app.logger.error("Database error while deleting property %s: %s", id, error)
        return jsonify({"error": "Could not delete the property. Please try again later."}), 500

    if deleted == 0:
        return jsonify({"error": "That property does not exist."}), 404

    return redirect(url_for("properties_list"), code=303)


# =====================================================================
# PHASE 3 - REAL ESTATE FRONTEND
# =====================================================================
#
# HTML pages for the property system. Every one of these is a thin
# controller, exactly like the JSON API above and the legacy product
# routes at the top of this file: it calls straight into
# property_queries.py / property_validation.py for the actual database
# work and the business rules, so there is exactly one implementation of
# property CRUD in the whole app - this section only renders it.
#
# These live at their own URLs (/dashboard, /properties/manage,
# /properties/view/<id>, /properties/new, /properties/<id>/edit,
# /properties/<id>/delete) instead of reusing the JSON routes' paths,
# because those routes are tested to always answer in JSON (see
# tests/test_properties.py - e.g. GET /properties/<id> is asserted to be
# "served as application/json, never text/html"). A create/update/delete
# made from the UI has to land the browser back on an HTML page, not a
# raw JSON response, so it needed its own paths rather than content
# negotiation on the existing ones.

_EMPTY_PROPERTY_FORM = {
    "title": "", "description": "", "property_type_id": "", "location_id": "",
    "agent_id": "", "listing_type": "", "price": "", "area_sqm": "",
    "bedrooms": "", "bathrooms": "", "status": "Available",
}


def _property_reference_or_empty():
    """Reference data for the create/edit selects. Never raises - an
    unreachable database just means empty dropdowns and a flashed error,
    the same "still show the page" rule the rest of the app follows."""
    try:
        connection = get_connection()
        reference = property_queries.get_reference_data(connection)
        connection.close()
        return reference
    except mysql.connector.Error as error:
        app.logger.error("Database error while loading reference data: %s", error)
        flash("Could not load property types, locations or agents. Please try again later.", "error")
        return {"property_types": [], "locations": [], "agents": []}


def _render_property_form(template, form_action, submit_label, property_data):
    """Shared GET-render for the create and edit pages: the reference
    data for the selects, plus whatever the caller already has for the
    fields themselves (empty defaults, a prefilled property, or a
    rejected submission the user should see again with what they typed)."""
    reference = _property_reference_or_empty()
    return render_template(
        template,
        form_action=form_action,
        submit_label=submit_label,
        property=property_data,
        property_types=reference["property_types"],
        locations=reference["locations"],
        agents=reference["agents"],
        listing_types=property_validation.LISTING_TYPES,
        statuses=property_validation.STATUSES,
    )


# ===== Real Estate Dashboard =====
@app.route("/dashboard")
def dashboard():
    try:
        connection = get_connection()
        stats = property_queries.get_property_stats(connection)
        connection.close()
    except mysql.connector.Error as error:
        app.logger.error("Database error while loading the dashboard: %s", error)
        flash("Could not load the dashboard statistics. Please try again later.", "error")
        stats = {"total": 0, "available": 0, "reserved": 0, "sold": 0, "rented": 0,
                 "total_value": 0.0, "average_price": 0.0}

    return render_template("dashboard.html", stats=stats)


# ===== Property Management - list, search and filter =====
@app.route("/properties/manage")
def properties_manage():
    properties = []
    try:
        connection = get_connection()
        properties = property_queries.get_all_properties(connection, _property_filters_from_query_string())
        reference = property_queries.get_reference_data(connection)
        connection.close()
    except mysql.connector.Error as error:
        app.logger.error("Database error while listing properties: %s", error)
        flash("Could not load the properties. Please try again later.", "error")
        reference = {"property_types": [], "locations": [], "agents": []}

    return render_template(
        "properties/index.html",
        properties=properties,
        property_types=reference["property_types"],
        listing_types=property_validation.LISTING_TYPES,
        statuses=property_validation.STATUSES,
        filters=request.args,
    )


# ===== Property Details =====
@app.route("/properties/view/<int:id>")
def property_view(id):
    try:
        connection = get_connection()
        row = property_queries.get_property_by_id(connection, id)
        connection.close()
    except mysql.connector.Error as error:
        app.logger.error("Database error while loading property %s: %s", id, error)
        flash("Could not load this property. Please try again later.", "error")
        return redirect(url_for("properties_manage"))

    if row is None:
        flash("That property does not exist!", "error")
        return redirect(url_for("properties_manage"))

    return render_template("properties/detail.html", property=row)


# ===== Create Property =====
@app.route("/properties/new", methods=["GET", "POST"])
def properties_new():
    if request.method == "POST":
        data = get_property_form_data()

        try:
            connection = get_connection()
        except mysql.connector.Error as error:
            app.logger.error("Database error: %s", error)
            flash("The database is unavailable. Please try again later.", "error")
            return _render_property_form("properties/add.html", url_for("properties_new"),
                                          "Create property", data)

        try:
            valid_ids = property_queries.get_valid_ids(connection)
            errors, cleaned = property_validation.validate_property_payload(data, valid_ids)
            if errors:
                for error in errors:
                    flash(error, "error")
                return _render_property_form("properties/add.html", url_for("properties_new"),
                                              "Create property", data)

            new_id = property_queries.create_property(connection, cleaned)
        except mysql.connector.Error as error:
            app.logger.error("Database error while creating a property: %s", error)
            flash("Could not save the property. Please try again later.", "error")
            return _render_property_form("properties/add.html", url_for("properties_new"),
                                          "Create property", data)
        finally:
            connection.close()

        flash('"' + cleaned["title"] + '" has been added!', "success")
        return redirect(url_for("property_view", id=new_id))

    return _render_property_form("properties/add.html", url_for("properties_new"),
                                  "Create property", _EMPTY_PROPERTY_FORM)


# ===== Edit Property =====
@app.route("/properties/<int:id>/edit", methods=["GET", "POST"])
def properties_edit_page(id):
    try:
        connection = get_connection()
    except mysql.connector.Error as error:
        app.logger.error("Database error: %s", error)
        flash("The database is unavailable. Please try again later.", "error")
        return redirect(url_for("properties_manage"))

    existing = property_queries.get_property_by_id(connection, id)
    if existing is None:
        connection.close()
        flash("That property does not exist!", "error")
        return redirect(url_for("properties_manage"))

    if request.method == "POST":
        data = get_property_form_data()
        try:
            valid_ids = property_queries.get_valid_ids(connection)
            errors, cleaned = property_validation.validate_property_payload(data, valid_ids)
            if errors:
                for error in errors:
                    flash(error, "error")
                return _render_property_form("properties/edit.html",
                                              url_for("properties_edit_page", id=id),
                                              "Save changes", data)

            property_queries.update_property(connection, id, cleaned)
        except mysql.connector.Error as error:
            app.logger.error("Database error while updating property %s: %s", id, error)
            flash("Could not update the property. Please try again later.", "error")
            return _render_property_form("properties/edit.html",
                                          url_for("properties_edit_page", id=id),
                                          "Save changes", data)
        finally:
            connection.close()

        flash('"' + cleaned["title"] + '" has been updated!', "success")
        return redirect(url_for("property_view", id=id))

    connection.close()
    return _render_property_form("properties/edit.html", url_for("properties_edit_page", id=id),
                                  "Save changes", existing)


# ===== Delete Property (POST only - never on GET) =====
@app.route("/properties/<int:id>/delete", methods=["POST"])
def properties_delete_page(id):
    try:
        connection = get_connection()
        row = property_queries.get_property_by_id(connection, id)
        deleted = property_queries.delete_property(connection, id) if row else 0
        connection.close()
    except mysql.connector.Error as error:
        app.logger.error("Database error while deleting property %s: %s", id, error)
        flash("Could not delete the property. Please try again later.", "error")
        return redirect(url_for("properties_manage"))

    if deleted == 0:
        flash("That property does not exist!", "error")
    else:
        flash('"' + row["title"] + '" has been deleted!', "success")

    return redirect(url_for("properties_manage"))


if __name__ == "__main__":
    app.run(debug=True)
