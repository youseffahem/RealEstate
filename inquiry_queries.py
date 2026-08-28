"""Real Estate inquiry queries for the Phase 6 Inquiries / Leads Management
backend.

This module owns every SQL statement that reads or writes the `inquiries`
table, plus the small lookups (property options, per-property/per-agent
inquiry lists, live statistics) the Inquiries UI and the Property/Agent
integrations need.

It mirrors the style already used by property_queries.py and
agent_queries.py: every function receives an *open* mysql.connector
connection - it never opens or closes one itself - so the caller (a Flask
route in app.py, a script, or a test) stays in control of the connection's
lifetime.

Every statement below uses %s placeholders. User-supplied values are always
sent to MySQL as bound parameters, never concatenated into the SQL text.

There is exactly one read query (INQUIRY_BASE_QUERY, driven through
get_all_inquiries()'s `filters`), the same pattern property_queries.py and
agent_queries.py already use - get_property_inquiries() and
get_agent_inquiries() are thin wrappers around it instead of separate SQL,
so a property's or an agent's inquiries are never a second implementation
of the same JOIN.
"""

# Every inquiry read (list, single, or scoped to one property/agent) joins
# the property it was sent about (title/type/location/price/listing/status)
# and that property's agent (if any), so the Inquiries UI, the Property
# Details "Inquire" flow and the Agent Details "Recent Inquiries" section
# all read from one query instead of N+1 follow-up lookups.
INQUIRY_BASE_QUERY = """
    SELECT
        i.id, i.property_id, i.name, i.email, i.phone, i.message, i.status, i.created_at,
        p.title AS property_title, p.price AS property_price,
        p.listing_type AS property_listing_type, p.status AS property_status,
        pt.name AS property_type,
        l.name AS location_name, l.city AS location_city,
        p.agent_id, a.name AS agent_name, a.email AS agent_email, a.phone AS agent_phone
    FROM inquiries i
    JOIN properties p ON p.id = i.property_id
    JOIN property_types pt ON pt.id = p.property_type_id
    JOIN locations l ON l.id = p.location_id
    LEFT JOIN agents a ON a.id = p.agent_id
"""

# Every editable inquiry field, in the order every INSERT/UPDATE below uses.
_EDITABLE_FIELDS = ("property_id", "name", "email", "phone", "message", "status")


def _values(data):
    """Pull the editable fields out of a cleaned payload, in a fixed order."""
    return tuple(data[field] for field in _EDITABLE_FIELDS)


def get_all_inquiries(connection, filters=None):
    """Every inquiry, joined for display, optionally narrowed by `filters`.

    Supported filters (all optional, all bound as parameters):
    status, property_id, agent_id, q (matches customer name, email, phone,
    property title or message).
    """
    filters = filters or {}
    clauses = []
    params = []

    if filters.get("status"):
        clauses.append("i.status = %s")
        params.append(filters["status"])
    if filters.get("property_id") is not None:
        clauses.append("i.property_id = %s")
        params.append(filters["property_id"])
    if filters.get("agent_id") is not None:
        clauses.append("p.agent_id = %s")
        params.append(filters["agent_id"])
    if filters.get("q"):
        clauses.append(
            "(i.name LIKE %s OR i.email LIKE %s OR i.phone LIKE %s "
            "OR p.title LIKE %s OR i.message LIKE %s)"
        )
        like = "%" + filters["q"] + "%"
        params.extend([like, like, like, like, like])

    sql = INQUIRY_BASE_QUERY
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY i.created_at DESC, i.id DESC"

    cursor = connection.cursor(dictionary=True)
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    cursor.close()
    return rows


def get_inquiry_by_id(connection, inquiry_id):
    """One inquiry, joined with its property/agent, or None."""
    cursor = connection.cursor(dictionary=True)
    cursor.execute(INQUIRY_BASE_QUERY + " WHERE i.id = %s", (inquiry_id,))
    row = cursor.fetchone()
    cursor.close()
    return row


def get_property_inquiries(connection, property_id):
    """Every inquiry sent about one property, newest first."""
    return get_all_inquiries(connection, {"property_id": property_id})


def get_agent_inquiries(connection, agent_id):
    """Every inquiry sent about a property assigned to this agent, newest
    first - a proper JOIN through properties.agent_id, not a second query
    per property."""
    return get_all_inquiries(connection, {"agent_id": agent_id})


def create_inquiry(connection, data):
    """Insert a new inquiry from a cleaned payload. Returns the new id."""
    cursor = connection.cursor()
    cursor.execute(
        """
        INSERT INTO inquiries (property_id, name, email, phone, message, status)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        _values(data),
    )
    connection.commit()
    new_id = cursor.lastrowid
    cursor.close()
    return new_id


def update_inquiry(connection, inquiry_id, data):
    """Update every editable field of an inquiry (including its status).
    Returns the row count (0 means the id did not exist)."""
    cursor = connection.cursor()
    cursor.execute(
        """
        UPDATE inquiries
        SET property_id = %s, name = %s, email = %s, phone = %s, message = %s, status = %s
        WHERE id = %s
        """,
        _values(data) + (inquiry_id,),
    )
    connection.commit()
    updated = cursor.rowcount
    cursor.close()
    return updated


def delete_inquiry(connection, inquiry_id):
    """Delete one inquiry. This never touches the property, its agent or
    its images - only the `inquiries` row itself. Returns the row count."""
    cursor = connection.cursor()
    cursor.execute("DELETE FROM inquiries WHERE id = %s", (inquiry_id,))
    connection.commit()
    deleted = cursor.rowcount
    cursor.close()
    return deleted


def get_inquiry_stats(connection):
    """Live Inquiries-page numbers, computed straight from MySQL - nothing
    hard coded. Safe to call on an empty table: every count degrades to 0
    instead of raising, the same rule property_queries.get_property_stats()
    and agent_queries.get_agent_overview_stats() already follow."""
    cursor = connection.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(status = 'New') AS new_count,
            SUM(status = 'Contacted') AS contacted,
            SUM(status = 'Closed') AS closed,
            SUM(DATE(created_at) = CURDATE()) AS today
        FROM inquiries
        """
    )
    row = cursor.fetchone() or {}
    cursor.close()

    return {
        "total": int(row.get("total") or 0),
        "new": int(row.get("new_count") or 0),
        "contacted": int(row.get("contacted") or 0),
        "closed": int(row.get("closed") or 0),
        "today": int(row.get("today") or 0),
    }


def get_property_options(connection):
    """Every property as a plain {id, title} pair, ordered by title - used
    to populate the inquiry form's Property select and the Inquiries page's
    Property filter. Deliberately not property_queries.get_reference_data()
    (that returns property_types/locations/agents, not properties)."""
    cursor = connection.cursor(dictionary=True)
    cursor.execute("SELECT id, title FROM properties ORDER BY title")
    rows = cursor.fetchall()
    cursor.close()
    return rows


def get_valid_property_ids(connection):
    """Every property id that currently exists, as a set - used by the
    validation layer to check the Property field itself instead of only
    finding out from a database error after the fact."""
    cursor = connection.cursor()
    cursor.execute("SELECT id FROM properties")
    ids = {row[0] for row in cursor.fetchall()}
    cursor.close()
    return ids


def get_property_inquiry_count(connection, property_id):
    """How many inquiries a property has received - the "N inquiries"
    count shown on Property Details. A dedicated COUNT query, so viewing a
    property never has to pull every inquiry row just to size a list."""
    cursor = connection.cursor()
    cursor.execute("SELECT COUNT(*) FROM inquiries WHERE property_id = %s", (property_id,))
    count = cursor.fetchone()[0]
    cursor.close()
    return count
