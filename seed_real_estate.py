"""Top up the Real Estate database with the demo data, without touching
anything else.

`python app.py` and `flask run` already create the real estate schema and
seed it automatically - but only while it is missing or empty, so they
never fight with data created through the app. Run this script any time
you want to make sure a database has the full demo set (for example after
someone deleted a property type by hand):

    python seed_real_estate.py

property_types, locations and agents are topped up by their unique key
(name, (name, city) and email), so running this twice never creates a
duplicate. The demo properties (with their placeholder images and demo
inquiries) are only inserted while the properties table is completely
empty - the same rule the app itself uses - so an existing property is
never touched by this script.

This script does not touch the legacy `products` table; see seed.py for
that.
"""

import mysql.connector

import real_estate_db
from app import get_connection, init_db


def main():
    # Make sure the database and every table (old and new) exist first.
    init_db()

    connection = get_connection()
    summary = real_estate_db.init_real_estate(connection)
    connection.close()

    print("Property types added: " + str(summary["property_types"]))
    print("Locations added:      " + str(summary["locations"]))
    print("Agents added:         " + str(summary["agents"]))
    if summary["properties"]:
        print("Properties added:     " + str(summary["properties"]) +
              " (with " + str(summary["property_images"]) + " image slots and " +
              str(summary["inquiries"]) + " demo inquiries)")
    else:
        print("Properties added:     0 (table already has properties in it)")

    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT COUNT(*) FROM properties")
    total = cursor.fetchone()[0]
    cursor.close()
    connection.close()
    print("Database now holds " + str(total) + " properties.")


if __name__ == "__main__":
    try:
        main()
    except mysql.connector.Error as error:
        print("Could not seed the real estate database: " + str(error))
