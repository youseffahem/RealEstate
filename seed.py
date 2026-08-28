"""Top up the catalog with the demo products, without touching anything else.

`python app.py` and `flask run` already seed automatically, but only while the
products table is completely empty - so they never fight with products you
created yourself.

Run this script when you want the demo catalog in a database that already has
rows in it:

    python seed.py

It inserts only the demo products whose name is not in the table yet, so
running it twice changes nothing and no existing product is ever modified or
deleted.
"""

import mysql.connector

from app import DEMO_PRODUCTS, get_connection, init_db


def main():
    # Make sure the database and the table exist before we insert into them.
    init_db()

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("SELECT name FROM products")
    existing = {row[0] for row in cursor.fetchall()}

    missing = [item for item in DEMO_PRODUCTS if item[0] not in existing]

    if not missing:
        print("Nothing to do - all " + str(len(DEMO_PRODUCTS)) +
              " demo products are already in the catalog.")
    else:
        cursor.executemany(
            "INSERT INTO products (name, price, description) VALUES (%s, %s, %s)",
            missing,
        )
        connection.commit()
        print("Added " + str(cursor.rowcount) + " demo product(s):")
        for name, price, _ in missing:
            print("  - " + name + "  ($" + "{:,.2f}".format(price) + ")")

    cursor.execute("SELECT COUNT(*) FROM products")
    print("Catalog now holds " + str(cursor.fetchone()[0]) + " products.")

    cursor.close()
    connection.close()


if __name__ == "__main__":
    try:
        main()
    except mysql.connector.Error as error:
        print("Could not seed the database: " + str(error))
