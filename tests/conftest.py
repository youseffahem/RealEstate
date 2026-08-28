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
