"""Real Estate property queries for the TANTAWY backend (Phase 2).

This module owns every SQL statement that reads or writes the `properties`
table, plus the small reference lookups (property_types, locations, agents)
used to populate dropdowns and to validate foreign keys.

It mirrors the style already used by real_estate_db.py: every function
receives an *open* mysql.connector connection - it never opens or closes
one itself - so the caller (a Flask route in app.py, a script, or a test)
stays in control of the connection's lifetime.

Every statement below uses %s placeholders. User-supplied values are always
sent to MySQL as bound parameters, never concatenated into the SQL text.
"""

# Every property read (list or single) joins the same three lookup tables,
# so the display fields (type name, location, agent contact) are always
# available in one query instead of N+1 follow-up queries.
PROPERTY_DETAIL_QUERY = """
    SELECT
        p.id, p.title, p.description,
        p.property_type_id, pt.name AS property_type,
        p.location_id, l.name AS location_name, l.city AS location_city,
        p.agent_id, a.name AS agent_name, a.email AS agent_email, a.phone AS agent_phone,
        p.listing_type, p.price, p.area_sqm, p.bedrooms, p.bathrooms, p.status,
        p.created_at, p.updated_at
    FROM properties p
    JOIN property_types pt ON pt.id = p.property_type_id
    JOIN locations l ON l.id = p.location_id
    LEFT JOIN agents a ON a.id = p.agent_id
"""

# Every editable property field, in the order every INSERT/UPDATE below uses.
_EDITABLE_FIELDS = (
    "title", "description", "property_type_id", "location_id", "agent_id",
    "listing_type", "price", "area_sqm", "bedrooms", "bathrooms", "status",
)


def _values(data):
    """Pull the editable fields out of a cleaned payload, in a fixed order."""
    return tuple(data[field] for field in _EDITABLE_FIELDS)


def get_all_properties(connection, filters=None):
    """Every property, joined for display, optionally narrowed by `filters`.

    Supported filters (all optional, all bound as parameters):
    status, listing_type, property_type_id, location_id, min_price,
    max_price, min_area, max_area, q (matches title or description).
    """
    filters = filters or {}
    clauses = []
    params = []

    if filters.get("status"):
        clauses.append("p.status = %s")
        params.append(filters["status"])
    if filters.get("listing_type"):
        clauses.append("p.listing_type = %s")
        params.append(filters["listing_type"])
    if filters.get("property_type_id") is not None:
        clauses.append("p.property_type_id = %s")
        params.append(filters["property_type_id"])
    if filters.get("location_id") is not None:
        clauses.append("p.location_id = %s")
        params.append(filters["location_id"])
    if filters.get("min_price") is not None:
        clauses.append("p.price >= %s")
        params.append(filters["min_price"])
    if filters.get("max_price") is not None:
        clauses.append("p.price <= %s")
        params.append(filters["max_price"])
    if filters.get("min_area") is not None:
        clauses.append("p.area_sqm >= %s")
        params.append(filters["min_area"])
    if filters.get("max_area") is not None:
        clauses.append("p.area_sqm <= %s")
        params.append(filters["max_area"])
    if filters.get("q"):
        # Phase 3 search covers title, description and location (both the
        # location's own name and its city), matching what the property
        # UI's search box promises. l is already joined in above.
        clauses.append("(p.title LIKE %s OR p.description LIKE %s OR l.name LIKE %s OR l.city LIKE %s)")
        like = "%" + filters["q"] + "%"
        params.extend([like, like, like, like])

    sql = PROPERTY_DETAIL_QUERY
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY p.id DESC"

    cursor = connection.cursor(dictionary=True)
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    cursor.close()
    return rows


def get_property_by_id(connection, property_id):
    """One property, joined with its type/location/agent, or None."""
    cursor = connection.cursor(dictionary=True)
    cursor.execute(PROPERTY_DETAIL_QUERY + " WHERE p.id = %s", (property_id,))
    row = cursor.fetchone()
    cursor.close()
    return row


def create_property(connection, data):
    """Insert a new property from a cleaned payload. Returns the new id."""
    cursor = connection.cursor()
    cursor.execute(
        """
        INSERT INTO properties
            (title, description, property_type_id, location_id, agent_id,
             listing_type, price, area_sqm, bedrooms, bathrooms, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        _values(data),
    )
    connection.commit()
    new_id = cursor.lastrowid
    cursor.close()
    return new_id


def update_property(connection, property_id, data):
    """Update every editable field of a property. Returns the row count
    (0 means the id did not exist)."""
    cursor = connection.cursor()
    cursor.execute(
        """
        UPDATE properties
        SET title = %s, description = %s, property_type_id = %s,
            location_id = %s, agent_id = %s, listing_type = %s, price = %s,
            area_sqm = %s, bedrooms = %s, bathrooms = %s, status = %s
        WHERE id = %s
        """,
        _values(data) + (property_id,),
    )
    connection.commit()
    updated = cursor.rowcount
    cursor.close()
    return updated


def delete_property(connection, property_id):
    """Delete a property. property_images and inquiries cascade in MySQL
    (ON DELETE CASCADE - see real_estate_db.py). Returns the row count."""
    cursor = connection.cursor()
    cursor.execute("DELETE FROM properties WHERE id = %s", (property_id,))
    connection.commit()
    deleted = cursor.rowcount
    cursor.close()
    return deleted


def get_reference_data(connection):
    """Property types, locations and agents - used to populate dropdowns
    and to validate the foreign keys on a property."""
    cursor = connection.cursor(dictionary=True)
    cursor.execute("SELECT id, name FROM property_types ORDER BY name")
    property_types = cursor.fetchall()
    cursor.execute("SELECT id, name, city FROM locations ORDER BY city, name")
    locations = cursor.fetchall()
    cursor.execute("SELECT id, name, email, phone FROM agents ORDER BY name")
    agents = cursor.fetchall()
    cursor.close()
    return {
        "property_types": property_types,
        "locations": locations,
        "agents": agents,
    }


def get_valid_ids(connection):
    """The ids a property is currently allowed to reference, as sets -
    used by the validation layer to check foreign keys itself instead of
    only finding out from a database error after the fact."""
    reference = get_reference_data(connection)
    return {
        "property_type_ids": {row["id"] for row in reference["property_types"]},
        "location_ids": {row["id"] for row in reference["locations"]},
        "agent_ids": {row["id"] for row in reference["agents"]},
    }


def get_property_stats(connection):
    """Dashboard numbers, computed straight from MySQL - nothing hard coded.

    Safe to call on an empty table: COUNT/SUM/AVG degrade to 0 instead of
    raising, the same rule already used by app.get_stats() for products.
    """
    stats = {
        "total": 0, "available": 0, "reserved": 0, "sold": 0, "rented": 0,
        "total_value": 0.0, "average_price": 0.0,
    }

    cursor = connection.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(status = 'Available') AS available,
            SUM(status = 'Reserved') AS reserved,
            SUM(status = 'Sold') AS sold,
            SUM(status = 'Rented') AS rented,
            SUM(price) AS total_value,
            AVG(price) AS average_price
        FROM properties
        """
    )
    row = cursor.fetchone() or {}
    cursor.close()

    stats["total"] = int(row.get("total") or 0)
    stats["available"] = int(row.get("available") or 0)
    stats["reserved"] = int(row.get("reserved") or 0)
    stats["sold"] = int(row.get("sold") or 0)
    stats["rented"] = int(row.get("rented") or 0)
    # SUM/AVG are NULL while the table is empty.
    stats["total_value"] = float(row.get("total_value") or 0)
    stats["average_price"] = float(row.get("average_price") or 0)
    return stats
