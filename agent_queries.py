"""Real Estate agent queries for the Phase 5 Agents Management backend.

This module owns every SQL statement that reads or writes the `agents`
table, plus the aggregate queries that turn `properties.agent_id` into the
per-agent statistics the Agents pages show (assigned/available/sold/rented
counts, agents-with-properties, unassigned properties).

It mirrors the style already used by property_queries.py: every function
receives an *open* mysql.connector connection - it never opens or closes
one itself - so the caller (a Flask route in app.py, a script, or a test)
stays in control of the connection's lifetime.

Every statement below uses %s placeholders. User-supplied values are always
sent to MySQL as bound parameters, never concatenated into the SQL text.
"""

import property_queries

# Every agent read (list or single) is a LEFT JOIN against properties,
# aggregated per agent, so the assignment counts are always available in
# one query instead of N+1 follow-up queries per agent.
_AGENT_BASE_QUERY = """
    SELECT
        a.id, a.name, a.email, a.phone, a.gender, a.photo_url, a.created_at,
        COUNT(p.id) AS property_count,
        SUM(p.status = 'Available') AS available_count,
        SUM(p.status = 'Reserved') AS reserved_count,
        SUM(p.status = 'Sold') AS sold_count,
        SUM(p.status = 'Rented') AS rented_count
    FROM agents a
    LEFT JOIN properties p ON p.agent_id = a.id
"""

_COUNT_FIELDS = (
    "property_count", "available_count", "reserved_count", "sold_count", "rented_count",
)


def _normalize_counts(row):
    """COUNT/SUM come back as Decimal/None for an agent with no properties -
    normalise every count field to a plain int, the same rule already used
    by property_queries.get_property_stats()."""
    for field in _COUNT_FIELDS:
        row[field] = int(row.get(field) or 0)
    return row


def get_all_agents(connection, filters=None):
    """Every agent, with their property counts, optionally narrowed by a
    `q` search filter matching name, email or phone."""
    filters = filters or {}
    clauses = []
    params = []

    if filters.get("q"):
        clauses.append("(a.name LIKE %s OR a.email LIKE %s OR a.phone LIKE %s)")
        like = "%" + filters["q"] + "%"
        params.extend([like, like, like])

    sql = _AGENT_BASE_QUERY
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " GROUP BY a.id, a.name, a.email, a.phone, a.gender, a.photo_url, a.created_at ORDER BY a.name"

    cursor = connection.cursor(dictionary=True)
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    cursor.close()
    return [_normalize_counts(row) for row in rows]


def get_agent_by_id(connection, agent_id):
    """One agent, with their property counts, or None."""
    sql = (
        _AGENT_BASE_QUERY
        + " WHERE a.id = %s GROUP BY a.id, a.name, a.email, a.phone, a.gender, a.photo_url, a.created_at"
    )
    cursor = connection.cursor(dictionary=True)
    cursor.execute(sql, (agent_id,))
    row = cursor.fetchone()
    cursor.close()
    return _normalize_counts(row) if row else None


def get_agent_properties(connection, agent_id):
    """Every property assigned to this agent, joined for display - the same
    shape property_queries.get_all_properties() returns everywhere else, so
    there is exactly one query that reads a property for display."""
    return property_queries.get_all_properties(connection, {"agent_id": agent_id})


def get_all_agent_emails(connection, exclude_id=None):
    """Every agent email already in use, lower-cased, as a set - used to
    check uniqueness before a create/update. `exclude_id` leaves the
    agent's own current email out, so saving an agent without changing
    their email is never rejected as "already used"."""
    cursor = connection.cursor()
    if exclude_id is not None:
        cursor.execute("SELECT email FROM agents WHERE id != %s", (exclude_id,))
    else:
        cursor.execute("SELECT email FROM agents")
    emails = {row[0].lower() for row in cursor.fetchall()}
    cursor.close()
    return emails


def create_agent(connection, data):
    """Insert a new agent from a cleaned payload. Returns the new id."""
    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO agents (name, email, phone, gender, photo_url) VALUES (%s, %s, %s, %s, %s)",
        (data["name"], data["email"], data["phone"], data["gender"], data.get("photo_url")),
    )
    connection.commit()
    new_id = cursor.lastrowid
    cursor.close()
    return new_id


def update_agent(connection, agent_id, data):
    """Update every editable field of an agent. Returns the row count
    (0 means the id did not exist)."""
    cursor = connection.cursor()
    cursor.execute(
        "UPDATE agents SET name = %s, email = %s, phone = %s, gender = %s, photo_url = %s WHERE id = %s",
        (data["name"], data["email"], data["phone"], data["gender"], data.get("photo_url"), agent_id),
    )
    connection.commit()
    updated = cursor.rowcount
    cursor.close()
    return updated


def group_agents_by_gender(agents):
    """Split a list of agent dicts (as returned by get_all_agents()) into
    (male_agents, female_agents), preserving their existing relative order.

    Pure and DB-free, so the Agents page grouping rule - Male agents
    displayed before Female agents, in their own section, with an empty
    gender group simply not shown at all - can be unit-tested directly,
    without needing to touch the database or the seeded agent catalog."""
    male_agents = [agent for agent in agents if agent.get("gender") == "Male"]
    female_agents = [agent for agent in agents if agent.get("gender") == "Female"]
    return male_agents, female_agents


def delete_agent(connection, agent_id):
    """Delete an agent. properties.agent_id is ON DELETE SET NULL (see
    real_estate_db.py), so MySQL itself clears agent_id on every property
    that referenced this agent instead of deleting them - a property never
    disappears because its agent was deleted. Returns the row count."""
    cursor = connection.cursor()
    cursor.execute("DELETE FROM agents WHERE id = %s", (agent_id,))
    connection.commit()
    deleted = cursor.rowcount
    cursor.close()
    return deleted


def get_agent_overview_stats(connection):
    """Live Agents-page numbers, computed straight from MySQL - nothing
    hard coded. Safe to call on an empty table: every count degrades to 0
    instead of raising, the same rule property_queries.get_property_stats()
    already follows."""
    cursor = connection.cursor(dictionary=True)

    cursor.execute("SELECT COUNT(*) AS total FROM agents")
    total_agents = int((cursor.fetchone() or {}).get("total") or 0)

    cursor.execute("SELECT COUNT(DISTINCT agent_id) AS total FROM properties WHERE agent_id IS NOT NULL")
    agents_with_properties = int((cursor.fetchone() or {}).get("total") or 0)

    cursor.execute("SELECT COUNT(*) AS total FROM properties WHERE agent_id IS NULL")
    unassigned_properties = int((cursor.fetchone() or {}).get("total") or 0)

    cursor.close()
    return {
        "total_agents": total_agents,
        "agents_with_properties": agents_with_properties,
        "unassigned_properties": unassigned_properties,
    }
