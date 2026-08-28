import datetime
import decimal
import os
import uuid

import mysql.connector
from dotenv import load_dotenv
from flask import Flask, flash, jsonify, redirect, render_template, request, send_from_directory, url_for
from werkzeug.utils import secure_filename

import agent_queries
import agent_validation
import analytics_queries
import inquiry_queries
import inquiry_validation
import property_queries
import property_validation
import real_estate_db

# Load the settings from the .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")

# --- File uploads ---
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "uploads")
ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- Database settings (read from .env, never written in the code) ---
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "3306"))
DB_USER = os.environ.get("DB_USER", "root")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_NAME = os.environ.get("DB_NAME", "product_crud")


def get_connection():
    """Open a new connection to the application's MySQL database."""
    return mysql.connector.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
    )


def init_db():
    """Create the database and the Real Estate schema if missing."""
    # First connect without a database, so we can create it if it is missing.
    connection = mysql.connector.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD
    )
    cursor = connection.cursor()
    # The name comes from .env (not from a user), so it is safe to insert here.
    cursor.execute("CREATE DATABASE IF NOT EXISTS `" + DB_NAME + "`")
    cursor.close()
    connection.close()

    # Now connect to that database.
    connection = get_connection()
    cursor = connection.cursor()
    # One-time cleanup migration: the legacy Product CRUD exercise this app
    # started from is gone, and so is its `products` table. IF EXISTS makes
    # this a no-op on every run after the first.
    cursor.execute("DROP TABLE IF EXISTS products")
    connection.commit()
    cursor.close()

    # Real Estate schema: property_types, locations, agents, properties,
    # property_images, inquiries. See real_estate_db.py.
    re_summary = real_estate_db.init_real_estate(connection)
    connection.close()

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


@app.template_filter("money")
def money(value):
    """Format a price the way the dashboard shows it, e.g. 8420.5 -> 8,420.50"""
    try:
        return "{:,.2f}".format(float(value))
    except (TypeError, ValueError):
        return "0.00"


# ===== Application entry point - straight to the Real Estate Dashboard =====
@app.route("/")
def index():
    return redirect(url_for("dashboard"))


# ===== Handle unknown pages / invalid ids =====
@app.errorhandler(404)
def page_not_found(error):
    if _wants_json():
        return jsonify({"error": "That page does not exist."}), 404
    flash("That page does not exist!", "error")
    return redirect(url_for("dashboard"))


# ===== Handle a wrong method, e.g. opening /delete/1 in the address bar =====
@app.errorhandler(405)
def method_not_allowed(error):
    if _wants_json():
        return jsonify({"error": "That method is not allowed on this URL."}), 405
    # Delete is POST only, so reaching it any other way lands back on the
    # relevant page inside our own design instead of on the default error page.
    flash("That action has to be done from the page itself!", "error")
    if request.path.startswith("/inquiries"):
        # Phase 6 requirement: GET on an Inquiries POST-only route (delete)
        # must answer with the real HTTP 405, not just a flash-and-redirect
        # - see tests/test_inquiries.py "POST-only delete". Still lands the
        # visitor back on the Inquiries page inside our own design, exactly
        # like every other 405 here - only the status code differs.
        response = redirect(url_for("inquiries_list"))
        response.status_code = 405
        return response
    if request.path.startswith("/agents"):
        # Phase 8 QA fix: GET on the Agents POST-only route (delete) fell
        # through to the fallback below - a real HTTP 302 back to the
        # unrelated dashboard instead of a proper 405 back on the Agents
        # page. Bring it in line with Properties (JSON 405 via
        # _wants_json()) and Inquiries above: same page, real status code.
        response = redirect(url_for("agents_list"))
        response.status_code = 405
        return response
    return redirect(url_for("dashboard"))


# =====================================================================
# REAL ESTATE BACKEND - JSON API
# =====================================================================
#
# The routes below are the backend of the REAL ESTATE Management
# System: full CRUD for `properties`, plus the reference data (property
# types, locations, agents) and dashboard statistics the UI needs.
#
# This started as a small JSON API alongside the (now removed) legacy
# Product templates, kept at its own paths so it can keep answering in
# pure JSON while the HTML pages in the section below answer in HTML -
# see tests/test_properties.py, which asserts every one of these routes
# is served as application/json, never text/html.


def _wants_json():
    """True for the /properties JSON API, so its own error responses are
    JSON instead of the flash-and-redirect used by the HTML pages.
    Non-/properties URLs (typos, old bookmarks, etc.) keep the existing
    behaviour untouched."""
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
# controller, exactly like the JSON API above: it calls straight into
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


def _save_uploaded_file(file_obj):
    """Save an uploaded image file to static/uploads/ with a UUID filename.
    Returns the URL path to serve it, or None if the file is invalid."""
    if not file_obj or not file_obj.filename:
        return None
    original = secure_filename(file_obj.filename)
    if not original:
        return None
    ext = original.rsplit(".", 1)[-1].lower() if "." in original else ""
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        return None
    unique_name = uuid.uuid4().hex + "." + ext
    file_obj.save(os.path.join(UPLOAD_FOLDER, unique_name))
    return "/uploads/" + unique_name


def get_image_urls_from_form():
    """Every image URL box submitted from the create/edit property form -
    one <input name="image_urls"> per gallery row (see
    templates/properties/_property_form.html).
    Also processes any uploaded files from <input type="file" name="image_files">."""
    urls = list(request.form.getlist("image_urls"))
    # Process uploaded files and append their URLs
    uploaded_files = request.files.getlist("image_files")
    for f in uploaded_files:
        saved_url = _save_uploaded_file(f)
        if saved_url:
            urls.append(saved_url)
    return urls


def _render_property_form(template, form_action, submit_label, property_data, image_urls=None):
    """Shared GET-render for the create and edit pages: the reference
    data for the selects, plus whatever the caller already has for the
    fields themselves (empty defaults, a prefilled property, or a
    rejected submission the user should see again with what they typed).
    `image_urls` is the gallery URLs to prefill - the property's existing
    images on a normal GET, or exactly what the user just typed when a
    submission is being redisplayed after a validation error."""
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
        property_images=image_urls or [],
        max_images=property_validation.MAX_IMAGES_PER_PROPERTY,
    )


# =====================================================================
# PHASE 7 - DASHBOARD 2.0 & ANALYTICS
# =====================================================================
#
# The route below stays a thin controller, exactly like every other page
# in the app: every number, aggregate and JOIN lives in analytics_queries.py
# (and, where a number is already computed there, in property_queries.py /
# agent_queries.py / inquiry_queries.py) - this only calls into that layer
# and renders it. See analytics_queries.py's module docstring for the
# get_*/build_* split.

_EMPTY_DASHBOARD_OVERVIEW = {
    "total": 0, "available": 0, "reserved": 0, "sold": 0, "rented": 0,
    "total_value": 0.0, "average_price": 0.0,
    "total_agents": 0, "agents_with_properties": 0, "unassigned_properties": 0,
    "total_inquiries": 0, "new_inquiries": 0, "contacted_inquiries": 0,
    "closed_inquiries": 0, "inquiries_today": 0, "closure_rate": 0.0,
}


def _empty_dashboard_context():
    """Fallback data for every dashboard template variable - used only
    when the database itself is unreachable, the same "still show the
    page" rule the rest of the app follows (see
    _property_reference_or_empty())."""
    return {
        "overview": _EMPTY_DASHBOARD_OVERVIEW,
        "status_chart": analytics_queries.build_property_status_chart(_EMPTY_DASHBOARD_OVERVIEW),
        "inquiry_status_chart": analytics_queries.build_inquiry_status_chart(_EMPTY_DASHBOARD_OVERVIEW),
        "type_chart": [],
        "listing_chart": [],
        "location_chart": [],
        "agent_performance": [],
        "recent_properties": [],
        "recent_inquiries": [],
    }


# ===== Real Estate Dashboard =====
@app.route("/dashboard")
def dashboard():
    try:
        connection = get_connection()
        overview = analytics_queries.get_dashboard_overview(connection)
        type_stats = analytics_queries.get_property_type_stats(connection)
        listing_stats = analytics_queries.get_listing_type_stats(connection)
        location_stats = analytics_queries.get_location_stats(connection)
        agent_performance = analytics_queries.get_agent_performance(connection)
        recent_properties = analytics_queries.get_recent_properties(connection)
        recent_inquiries = analytics_queries.get_recent_inquiries(connection)
        connection.close()
    except mysql.connector.Error as error:
        app.logger.error("Database error while loading the dashboard: %s", error)
        flash("Could not load the dashboard statistics. Please try again later.", "error")
        return render_template("dashboard.html", **_empty_dashboard_context())

    return render_template(
        "dashboard.html",
        overview=overview,
        status_chart=analytics_queries.build_property_status_chart(overview),
        inquiry_status_chart=analytics_queries.build_inquiry_status_chart(overview),
        type_chart=analytics_queries.build_property_type_chart(type_stats),
        listing_chart=analytics_queries.build_listing_type_chart(listing_stats),
        location_chart=analytics_queries.build_location_chart(location_stats),
        agent_performance=agent_performance,
        recent_properties=recent_properties,
        recent_inquiries=recent_inquiries,
    )


# ===== Property Management - list, search and filter =====
@app.route("/properties/manage")
def properties_manage():
    properties = []
    try:
        connection = get_connection()
        properties = property_queries.get_all_properties(connection, _property_filters_from_query_string())
        primary_images = property_queries.get_primary_images(
            connection, [row["id"] for row in properties]
        )
        for row in properties:
            row["primary_image"] = primary_images.get(row["id"])
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
        images = property_queries.get_property_images(connection, id) if row else []
        # Phase 6: the real, database-backed "N inquiries" count shown next
        # to the "Inquire about this property" action - never hard coded.
        inquiry_count = inquiry_queries.get_property_inquiry_count(connection, id) if row else 0
        connection.close()
    except mysql.connector.Error as error:
        app.logger.error("Database error while loading property %s: %s", id, error)
        flash("Could not load this property. Please try again later.", "error")
        return redirect(url_for("properties_manage"))

    if row is None:
        flash("That property does not exist!", "error")
        return redirect(url_for("properties_manage"))

    return render_template("properties/detail.html", property=row, images=images,
                            inquiry_count=inquiry_count)


# ===== Create Property =====
@app.route("/properties/new", methods=["GET", "POST"])
def properties_new():
    if request.method == "POST":
        data = get_property_form_data()
        image_urls = get_image_urls_from_form()

        try:
            connection = get_connection()
        except mysql.connector.Error as error:
            app.logger.error("Database error: %s", error)
            flash("The database is unavailable. Please try again later.", "error")
            return _render_property_form("properties/add.html", url_for("properties_new"),
                                          "Create property", data, image_urls=image_urls)

        try:
            valid_ids = property_queries.get_valid_ids(connection)
            errors, cleaned = property_validation.validate_property_payload(data, valid_ids)
            image_errors, cleaned_image_urls = property_validation.validate_image_urls(image_urls)
            errors.extend(image_errors)
            if errors:
                for error in errors:
                    flash(error, "error")
                return _render_property_form("properties/add.html", url_for("properties_new"),
                                              "Create property", data, image_urls=image_urls)

            new_id = property_queries.create_property(connection, cleaned)
            property_queries.set_property_images(connection, new_id, cleaned_image_urls)
        except mysql.connector.Error as error:
            app.logger.error("Database error while creating a property: %s", error)
            flash("Could not save the property. Please try again later.", "error")
            return _render_property_form("properties/add.html", url_for("properties_new"),
                                          "Create property", data, image_urls=image_urls)
        finally:
            connection.close()

        flash('"' + cleaned["title"] + '" has been added!', "success")
        return redirect(url_for("property_view", id=new_id))

    return _render_property_form("properties/add.html", url_for("properties_new"),
                                  "Create property", _EMPTY_PROPERTY_FORM)


# ===== Serve uploaded files =====
@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


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
        image_urls = get_image_urls_from_form()
        try:
            valid_ids = property_queries.get_valid_ids(connection)
            errors, cleaned = property_validation.validate_property_payload(data, valid_ids)
            image_errors, cleaned_image_urls = property_validation.validate_image_urls(image_urls)
            errors.extend(image_errors)
            if errors:
                for error in errors:
                    flash(error, "error")
                return _render_property_form("properties/edit.html",
                                              url_for("properties_edit_page", id=id),
                                              "Save changes", data, image_urls=image_urls)

            property_queries.update_property(connection, id, cleaned)
            property_queries.set_property_images(connection, id, cleaned_image_urls)
        except mysql.connector.Error as error:
            app.logger.error("Database error while updating property %s: %s", id, error)
            flash("Could not update the property. Please try again later.", "error")
            return _render_property_form("properties/edit.html",
                                          url_for("properties_edit_page", id=id),
                                          "Save changes", data, image_urls=image_urls)
        finally:
            connection.close()

        flash('"' + cleaned["title"] + '" has been updated!', "success")
        return redirect(url_for("property_view", id=id))

    existing_images = [row["image_url"] for row in property_queries.get_property_images(connection, id)]
    connection.close()
    return _render_property_form("properties/edit.html", url_for("properties_edit_page", id=id),
                                  "Save changes", existing, image_urls=existing_images)


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


# =====================================================================
# PHASE 5 - AGENTS MANAGEMENT
# =====================================================================
#
# HTML pages for the Agents system, following the exact same thin-
# controller pattern as the Phase 3 property pages above: every route
# calls straight into agent_queries.py / agent_validation.py for the
# actual database work and validation rules, so there is exactly one
# implementation of agent CRUD in the whole app.
#
# properties.agent_id is ON DELETE SET NULL (see real_estate_db.py), so
# deleting an agent here never deletes a property - it only clears that
# property's agent_id, and the property keeps working normally.

_EMPTY_AGENT_FORM = {"name": "", "email": "", "phone": "", "photo_url": ""}


def get_agent_form_data():
    """Read the agent fields sent by the form."""
    return {
        "name": request.form.get("name", ""),
        "email": request.form.get("email", ""),
        "phone": request.form.get("phone", ""),
    }


def _agent_filters_from_query_string():
    """?q=... -> the filters dict agent_queries.get_all_agents()
    understands. Missing is simply left out - search is best-effort, it
    never 500s."""
    filters = {}
    if request.args.get("q"):
        filters["q"] = request.args["q"]
    return filters


def _render_agent_form(template, form_action, submit_label, agent_data):
    """Shared GET-render for the create and edit pages, mirroring
    _render_property_form()'s role for properties."""
    return render_template(
        template,
        form_action=form_action,
        submit_label=submit_label,
        agent=agent_data,
    )


# ===== Agents - list, search and live statistics =====
@app.route("/agents")
def agents_list():
    agents = []
    stats = {"total_agents": 0, "agents_with_properties": 0, "unassigned_properties": 0}
    try:
        connection = get_connection()
        agents = agent_queries.get_all_agents(connection, _agent_filters_from_query_string())
        stats = agent_queries.get_agent_overview_stats(connection)
        connection.close()
    except mysql.connector.Error as error:
        app.logger.error("Database error while listing agents: %s", error)
        flash("Could not load the agents. Please try again later.", "error")

    return render_template("agents/index.html", agents=agents, stats=stats, filters=request.args)


# ===== Agent Details =====
@app.route("/agents/<int:id>")
def agent_detail(id):
    try:
        connection = get_connection()
        agent = agent_queries.get_agent_by_id(connection, id)
        properties = agent_queries.get_agent_properties(connection, id) if agent else []
        # Phase 6: every inquiry sent about one of this agent's assigned
        # properties, via a proper JOIN (inquiry_queries.get_agent_inquiries).
        inquiries = inquiry_queries.get_agent_inquiries(connection, id) if agent else []
        connection.close()
    except mysql.connector.Error as error:
        app.logger.error("Database error while loading agent %s: %s", id, error)
        flash("Could not load this agent. Please try again later.", "error")
        return redirect(url_for("agents_list"))

    if agent is None:
        flash("That agent does not exist!", "error")
        return redirect(url_for("agents_list"))

    return render_template("agents/detail.html", agent=agent, properties=properties, inquiries=inquiries)


# ===== Create Agent =====
@app.route("/agents/add", methods=["GET", "POST"])
def agents_add():
    if request.method == "POST":
        data = get_agent_form_data()

        # Handle agent photo upload
        photo_file = request.files.get("photo")
        photo_url = _save_uploaded_file(photo_file) if photo_file else None

        try:
            connection = get_connection()
        except mysql.connector.Error as error:
            app.logger.error("Database error: %s", error)
            flash("The database is unavailable. Please try again later.", "error")
            return _render_agent_form("agents/add.html", url_for("agents_add"), "Create agent", data)

        try:
            existing_emails = agent_queries.get_all_agent_emails(connection)
            errors, cleaned = agent_validation.validate_agent_payload(data, existing_emails)
            if errors:
                for error in errors:
                    flash(error, "error")
                return _render_agent_form("agents/add.html", url_for("agents_add"), "Create agent", data)

            cleaned["photo_url"] = photo_url
            new_id = agent_queries.create_agent(connection, cleaned)
        except mysql.connector.Error as error:
            app.logger.error("Database error while creating an agent: %s", error)
            flash("Could not save the agent. Please try again later.", "error")
            return _render_agent_form("agents/add.html", url_for("agents_add"), "Create agent", data)
        finally:
            connection.close()

        flash('"' + cleaned["name"] + '" has been added!', "success")
        return redirect(url_for("agent_detail", id=new_id))

    return _render_agent_form("agents/add.html", url_for("agents_add"), "Create agent", _EMPTY_AGENT_FORM)


# ===== Edit Agent =====
@app.route("/agents/edit/<int:id>", methods=["GET", "POST"])
def agents_edit(id):
    try:
        connection = get_connection()
    except mysql.connector.Error as error:
        app.logger.error("Database error: %s", error)
        flash("The database is unavailable. Please try again later.", "error")
        return redirect(url_for("agents_list"))

    existing = agent_queries.get_agent_by_id(connection, id)
    if existing is None:
        connection.close()
        flash("That agent does not exist!", "error")
        return redirect(url_for("agents_list"))

    if request.method == "POST":
        data = get_agent_form_data()

        # Handle agent photo upload
        photo_file = request.files.get("photo")
        photo_url = _save_uploaded_file(photo_file) if photo_file else None

        try:
            existing_emails = agent_queries.get_all_agent_emails(connection, exclude_id=id)
            errors, cleaned = agent_validation.validate_agent_payload(data, existing_emails)
            if errors:
                for error in errors:
                    flash(error, "error")
                data["photo_url"] = existing.get("photo_url", "")
                return _render_agent_form("agents/edit.html", url_for("agents_edit", id=id),
                                           "Save changes", data)

            # Keep existing photo if no new one uploaded
            cleaned["photo_url"] = photo_url if photo_url else existing.get("photo_url")
            agent_queries.update_agent(connection, id, cleaned)
        except mysql.connector.Error as error:
            app.logger.error("Database error while updating agent %s: %s", id, error)
            flash("Could not update the agent. Please try again later.", "error")
            data["photo_url"] = existing.get("photo_url", "")
            return _render_agent_form("agents/edit.html", url_for("agents_edit", id=id),
                                       "Save changes", data)
        finally:
            connection.close()

        flash('"' + cleaned["name"] + '" has been updated!', "success")
        return redirect(url_for("agent_detail", id=id))

    connection.close()
    return _render_agent_form("agents/edit.html", url_for("agents_edit", id=id), "Save changes", existing)


# ===== Delete Agent (POST only - never on GET) =====
# properties.agent_id is ON DELETE SET NULL, so deleting an agent here
# never deletes a property - see real_estate_db.py and agent_queries.py.
@app.route("/agents/delete/<int:id>", methods=["POST"])
def agents_delete(id):
    try:
        connection = get_connection()
        agent = agent_queries.get_agent_by_id(connection, id)
        deleted = agent_queries.delete_agent(connection, id) if agent else 0
        connection.close()
    except mysql.connector.Error as error:
        app.logger.error("Database error while deleting agent %s: %s", id, error)
        flash("Could not delete the agent. Please try again later.", "error")
        return redirect(url_for("agents_list"))

    if deleted == 0:
        flash("That agent does not exist!", "error")
    else:
        flash('"' + agent["name"] + '" has been deleted. Any assigned properties remain, now unassigned.', "success")

    return redirect(url_for("agents_list"))


# =====================================================================
# PHASE 6 - INQUIRIES / LEADS MANAGEMENT
# =====================================================================
#
# HTML pages for the Inquiries system, the same thin-controller pattern as
# the Phase 3 property pages and the Phase 5 agent pages above: every
# route calls straight into inquiry_queries.py / inquiry_validation.py for
# the actual database work and validation rules, so there is exactly one
# implementation of inquiry CRUD in the whole app.
#
# The business flow this backs: a customer viewing a property sends an
# inquiry (always starting as "New"); an agent works it from the
# Inquiries page, moving it New -> Contacted -> Closed. inquiries.property_id
# is ON DELETE CASCADE (see real_estate_db.py), so deleting a property also
# removes its inquiries - deleting an inquiry itself never touches the
# property, its agent or its images.

_EMPTY_INQUIRY_FORM = {
    "name": "", "email": "", "phone": "", "message": "", "property_id": "", "status": "New",
}


def get_inquiry_form_data():
    """Read the inquiry fields sent by the form. A customer's Create form
    never renders a status control, so "status" is simply absent from
    request.form on that page - inquiry_validation defaults it to "New"."""
    return {
        "name": request.form.get("name", ""),
        "email": request.form.get("email", ""),
        "phone": request.form.get("phone", ""),
        "message": request.form.get("message", ""),
        "property_id": request.form.get("property_id", ""),
        "status": request.form.get("status", ""),
    }


def _inquiry_filters_from_query_string():
    """?status=...&property_id=...&agent_id=...&q=... -> the filters dict
    inquiry_queries.get_all_inquiries() understands. Anything missing or
    malformed is simply left out - filtering is best-effort, it never 500s."""
    args = request.args
    filters = {}

    if args.get("status"):
        filters["status"] = args["status"]
    if args.get("q"):
        filters["q"] = args["q"]

    for key in ("property_id", "agent_id"):
        raw = args.get(key)
        if raw:
            try:
                filters[key] = int(raw)
            except ValueError:
                pass

    return filters


def _inquiry_reference_or_empty():
    """The property options and agents used by the Inquiries filters and
    the create/edit form's Property select. Never raises - an unreachable
    database just means empty dropdowns and a flashed error, the same
    "still show the page" rule the rest of the app follows."""
    try:
        connection = get_connection()
        properties = inquiry_queries.get_property_options(connection)
        agents = property_queries.get_reference_data(connection)["agents"]
        connection.close()
        return {"properties": properties, "agents": agents}
    except mysql.connector.Error as error:
        app.logger.error("Database error while loading reference data: %s", error)
        flash("Could not load properties or agents. Please try again later.", "error")
        return {"properties": [], "agents": []}


def _render_inquiry_form(template, form_action, submit_label, inquiry_data, show_status=False):
    """Shared GET-render for the create and edit pages, mirroring
    _render_property_form()'s and _render_agent_form()'s role for their
    own forms. `show_status` is False on the customer-facing Create page
    (the customer never chooses a status - Section 6) and True on the
    agent-facing Edit page."""
    reference = _inquiry_reference_or_empty()
    return render_template(
        template,
        form_action=form_action,
        submit_label=submit_label,
        inquiry=inquiry_data,
        properties=reference["properties"],
        statuses=inquiry_validation.STATUSES,
        show_status=show_status,
    )


# ===== Inquiries - list, search, filter and live statistics =====
@app.route("/inquiries")
def inquiries_list():
    inquiries = []
    stats = {"total": 0, "new": 0, "contacted": 0, "closed": 0, "today": 0}
    reference = {"properties": [], "agents": []}
    try:
        connection = get_connection()
        inquiries = inquiry_queries.get_all_inquiries(connection, _inquiry_filters_from_query_string())
        stats = inquiry_queries.get_inquiry_stats(connection)
        reference["properties"] = inquiry_queries.get_property_options(connection)
        reference["agents"] = property_queries.get_reference_data(connection)["agents"]
        connection.close()
    except mysql.connector.Error as error:
        app.logger.error("Database error while listing inquiries: %s", error)
        flash("Could not load the inquiries. Please try again later.", "error")

    return render_template(
        "inquiries/index.html",
        inquiries=inquiries,
        stats=stats,
        properties=reference["properties"],
        agents=reference["agents"],
        statuses=inquiry_validation.STATUSES,
        filters=request.args,
    )


# ===== Inquiry Details =====
@app.route("/inquiries/<int:id>")
def inquiry_detail(id):
    try:
        connection = get_connection()
        row = inquiry_queries.get_inquiry_by_id(connection, id)
        connection.close()
    except mysql.connector.Error as error:
        app.logger.error("Database error while loading inquiry %s: %s", id, error)
        flash("Could not load this inquiry. Please try again later.", "error")
        return redirect(url_for("inquiries_list"))

    if row is None:
        flash("That inquiry does not exist!", "error")
        return redirect(url_for("inquiries_list"))

    return render_template("inquiries/detail.html", inquiry=row)


# ===== Create Inquiry (customer-facing) =====
# Section 7: reached from a property's "Inquire about this property"
# action as /inquiries/add?property_id=<id>, which preselects that
# property in the form below - the customer still has to submit it.
@app.route("/inquiries/add", methods=["GET", "POST"])
def inquiries_add():
    if request.method == "POST":
        data = get_inquiry_form_data()

        try:
            connection = get_connection()
        except mysql.connector.Error as error:
            app.logger.error("Database error: %s", error)
            flash("The database is unavailable. Please try again later.", "error")
            return _render_inquiry_form("inquiries/add.html", url_for("inquiries_add"),
                                         "Send inquiry", data)

        try:
            valid_property_ids = inquiry_queries.get_valid_property_ids(connection)
            errors, cleaned = inquiry_validation.validate_inquiry_payload(data, valid_property_ids)
            if errors:
                for error in errors:
                    flash(error, "error")
                return _render_inquiry_form("inquiries/add.html", url_for("inquiries_add"),
                                             "Send inquiry", data)

            # Section 6: the customer must NOT choose the status. The Create
            # form never renders that control, but this route is the real
            # guarantee - it forces "New" even if a status were forged onto
            # a raw POST, instead of trusting the template alone.
            cleaned["status"] = "New"
            new_id = inquiry_queries.create_inquiry(connection, cleaned)
        except mysql.connector.Error as error:
            app.logger.error("Database error while creating an inquiry: %s", error)
            flash("Could not send the inquiry. Please try again later.", "error")
            return _render_inquiry_form("inquiries/add.html", url_for("inquiries_add"),
                                         "Send inquiry", data)
        finally:
            connection.close()

        flash("Your inquiry has been sent! An agent will be in touch soon.", "success")
        return redirect(url_for("inquiry_detail", id=new_id))

    # GET - an empty form, with the property preselected when the visitor
    # arrived from that property's own "Inquire about this property" link.
    prefilled = dict(_EMPTY_INQUIRY_FORM)
    prefilled["property_id"] = request.args.get("property_id", "")
    return _render_inquiry_form("inquiries/add.html", url_for("inquiries_add"), "Send inquiry", prefilled)


# ===== Edit Inquiry (agent-facing: edit details, manage status) =====
@app.route("/inquiries/edit/<int:id>", methods=["GET", "POST"])
def inquiries_edit(id):
    try:
        connection = get_connection()
    except mysql.connector.Error as error:
        app.logger.error("Database error: %s", error)
        flash("The database is unavailable. Please try again later.", "error")
        return redirect(url_for("inquiries_list"))

    existing = inquiry_queries.get_inquiry_by_id(connection, id)
    if existing is None:
        connection.close()
        flash("That inquiry does not exist!", "error")
        return redirect(url_for("inquiries_list"))

    if request.method == "POST":
        data = get_inquiry_form_data()
        try:
            valid_property_ids = inquiry_queries.get_valid_property_ids(connection)
            errors, cleaned = inquiry_validation.validate_inquiry_payload(data, valid_property_ids)
            if not errors:
                # Section 11: the ENUM itself controls which values are
                # possible; this controls which move from the inquiry's
                # *current* status is allowed (never backward).
                transition_error = inquiry_validation.validate_status_transition(
                    existing["status"], cleaned["status"]
                )
                if transition_error:
                    errors.append(transition_error)

            if errors:
                for error in errors:
                    flash(error, "error")
                return _render_inquiry_form("inquiries/edit.html", url_for("inquiries_edit", id=id),
                                             "Save changes", data, show_status=True)

            inquiry_queries.update_inquiry(connection, id, cleaned)
        except mysql.connector.Error as error:
            app.logger.error("Database error while updating inquiry %s: %s", id, error)
            flash("Could not update the inquiry. Please try again later.", "error")
            return _render_inquiry_form("inquiries/edit.html", url_for("inquiries_edit", id=id),
                                         "Save changes", data, show_status=True)
        finally:
            connection.close()

        flash("The inquiry has been updated!", "success")
        return redirect(url_for("inquiry_detail", id=id))

    connection.close()
    return _render_inquiry_form("inquiries/edit.html", url_for("inquiries_edit", id=id),
                                 "Save changes", existing, show_status=True)


# ===== Delete Inquiry (POST only - never on GET; see method_not_allowed) =====
# inquiries has no dependents of its own, so deleting one only ever removes
# that single row - the property, its agent and its images are untouched.
@app.route("/inquiries/delete/<int:id>", methods=["POST"])
def inquiries_delete(id):
    try:
        connection = get_connection()
        row = inquiry_queries.get_inquiry_by_id(connection, id)
        deleted = inquiry_queries.delete_inquiry(connection, id) if row else 0
        connection.close()
    except mysql.connector.Error as error:
        app.logger.error("Database error while deleting inquiry %s: %s", id, error)
        flash("Could not delete the inquiry. Please try again later.", "error")
        return redirect(url_for("inquiries_list"))

    if deleted == 0:
        flash("That inquiry does not exist!", "error")
    else:
        flash('The inquiry from "' + row["name"] + '" has been deleted!', "success")

    return redirect(url_for("inquiries_list"))


if __name__ == "__main__":
    # Phase 8 QA fix: debug=True was hardcoded, which would ship Werkzeug's
    # interactive debugger (raw stack traces, and - reachable on the
    # network - an unauthenticated code-execution console) to anyone who
    # ever ran this outside pure local development. Opt-in only, and off
    # by default, matching "never expose stack traces/internals" from the
    # security audit. `flask run --debug` remains the usual way to develop
    # locally with auto-reload; this only changes the `python app.py` path.
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
