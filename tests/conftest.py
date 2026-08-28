"""Test setup.

The tests run against their own MySQL database (`<DB_NAME>_test`) so nothing
they create or delete can ever touch the real catalog. The environment has to
be pointed at it *before* app.py is imported, because app.py reads the
settings and prepares the database at import time.
"""

import os
import sys

import pytest
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

load_dotenv(os.path.join(ROOT, ".env"))
os.environ["DB_NAME"] = os.environ.get("DB_NAME", "product_crud") + "_test"

import app as app_module  # noqa: E402  (must come after the env is set)


@pytest.fixture()
def client():
    """A Flask test client against an empty products table."""
    app_module.app.config["TESTING"] = True
    clear_products()
    with app_module.app.test_client() as test_client:
        yield test_client


@pytest.fixture()
def db():
    """Direct access to the test database, for asserting what really landed."""
    return app_module


def clear_products():
    connection = app_module.get_connection()
    cursor = connection.cursor()
    cursor.execute("DELETE FROM products")
    connection.commit()
    cursor.close()
    connection.close()


def insert_product(name="Test Product", price=10.00, description="A test product."):
    """Insert one row directly and return its id."""
    connection = app_module.get_connection()
    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO products (name, price, description) VALUES (%s, %s, %s)",
        (name, price, description),
    )
    connection.commit()
    new_id = cursor.lastrowid
    cursor.close()
    connection.close()
    return new_id


def fetch_product(product_id):
    connection = app_module.get_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute(
        "SELECT id, name, price, description FROM products WHERE id = %s",
        (product_id,),
    )
    row = cursor.fetchone()
    cursor.close()
    connection.close()
    return row


def count_products():
    connection = app_module.get_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT COUNT(*) FROM products")
    total = cursor.fetchone()[0]
    cursor.close()
    connection.close()
    return total


# =====================================================================
# Real Estate (Phase 2) helpers
#
# Unlike clear_products() above, these never wipe a whole table: the
# property CRUD tests run against the same test database as the Phase 1
# schema tests (tests/test_real_estate_schema.py), which asserts specific
# seeded counts (8 property types, 10-15 properties, ...). Every helper
# below only reads the seeded reference data, or inserts/deletes exactly
# the one row a test itself created - see the `track_properties` fixture.
# =====================================================================

def get_property_type_id():
    """The id of one already-seeded property type - read only."""
    connection = app_module.get_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT id FROM property_types ORDER BY id LIMIT 1")
    property_type_id = cursor.fetchone()[0]
    cursor.close()
    connection.close()
    return property_type_id


def get_location_id():
    """The id of one already-seeded location - read only."""
    connection = app_module.get_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT id FROM locations ORDER BY id LIMIT 1")
    location_id = cursor.fetchone()[0]
    cursor.close()
    connection.close()
    return location_id


def get_agent_id():
    """The id of one already-seeded agent - read only."""
    connection = app_module.get_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT id FROM agents ORDER BY id LIMIT 1")
    agent_id = cursor.fetchone()[0]
    cursor.close()
    connection.close()
    return agent_id


@pytest.fixture()
def property_ids():
    """Ids of one already-seeded property type, location and agent - a
    ready-made set of valid foreign keys for building a property payload."""
    return {
        "property_type_id": get_property_type_id(),
        "location_id": get_location_id(),
        "agent_id": get_agent_id(),
    }


def insert_property(title="Test Property", property_type_id=None, location_id=None,
                     agent_id=None, listing_type="For Sale", price=100000.00,
                     area_sqm=100.00, bedrooms=2, bathrooms=1, status="Available",
                     description="A test property."):
    """Insert one property row directly (bypassing the API) and return its
    id, so a test can set up state before exercising a route against it."""
    if property_type_id is None:
        property_type_id = get_property_type_id()
    if location_id is None:
        location_id = get_location_id()

    connection = app_module.get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
        INSERT INTO properties
            (title, description, property_type_id, location_id, agent_id,
             listing_type, price, area_sqm, bedrooms, bathrooms, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (title, description, property_type_id, location_id, agent_id,
         listing_type, price, area_sqm, bedrooms, bathrooms, status),
    )
    connection.commit()
    new_id = cursor.lastrowid
    cursor.close()
    connection.close()
    return new_id


def fetch_property_row(property_id):
    """The raw row (not the joined display query) for a property, or None."""
    connection = app_module.get_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute("SELECT * FROM properties WHERE id = %s", (property_id,))
    row = cursor.fetchone()
    cursor.close()
    connection.close()
    return row


def delete_property_row(property_id):
    connection = app_module.get_connection()
    cursor = connection.cursor()
    cursor.execute("DELETE FROM properties WHERE id = %s", (property_id,))
    connection.commit()
    cursor.close()
    connection.close()


def count_properties():
    connection = app_module.get_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT COUNT(*) FROM properties")
    total = cursor.fetchone()[0]
    cursor.close()
    connection.close()
    return total


@pytest.fixture()
def track_properties():
    """Any property id a test creates (directly or through the API) is
    deleted again at teardown, so the Phase 1 seeded catalog - and the
    counts test_real_estate_schema.py asserts - is never permanently
    changed by running the CRUD tests. Usage: track_properties.append(id).
    Deleting an id twice (e.g. a test that already deletes it itself) is a
    harmless no-op."""
    created = []
    yield created
    for property_id in created:
        delete_property_row(property_id)
