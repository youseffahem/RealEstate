"""Dashboard analytics queries for the Phase 7 Real Estate Analytics
Dashboard.

This module owns every SQL statement written specifically for Dashboard
2.0 - the numbers, aggregates and joins that do not already live in
property_queries.py / agent_queries.py / inquiry_queries.py. Where a number
the dashboard needs is already computed by one of those modules (e.g. the
property status counts, the agent totals, the inquiry counts), this module
calls into it instead of running a second, competing query for the same
data - see get_dashboard_overview() below.

It mirrors the style already used by the other *_queries.py modules: every
query function receives an *open* mysql.connector connection - it never
opens or closes one itself - so the caller (a Flask route in app.py, or a
test) stays in control of the connection's lifetime. Every statement uses
%s placeholders for any value that is not a small, internally-trusted
constant (see _limit_clause() below for the one exception, and why it is
still safe).

Two kinds of functions live here:

- "get_*" functions run a query against MySQL and return plain rows.
- "build_*" functions are pure Python - they never touch the database.
  They reshape rows a "get_*" function (or get_dashboard_overview) already
  fetched into the {label, count, percent, color, ...} shape the dashboard
  charts render, so a page load never runs the same aggregate query twice
  just to get it into a slightly different shape.
"""

import agent_queries
import inquiry_queries
import property_queries

# How many rows the "Recent Properties" / "Recent Inquiries" panels and the
# "Top Locations" chart show - enough to be useful, small enough to stay a
# quick glance rather than another full list page.
DEFAULT_RECENT_LIMIT = 5
DEFAULT_LOCATION_LIMIT = 8

# Colours for the chart segments, reusing the exact colours the existing
# badge-status-*/badge-listing-* CSS classes already use (see style.css) -
# so a status reads the same colour whether it is a pill on a card or a
# slice of a dashboard chart. Values are CSS custom properties where one
# already exists; the two that don't (the amber "Reserved"/"Contacted"
# colour) reuse the exact literal style.css already uses for those pills.
STATUS_COLORS = {
    "Available": "var(--success)",
    "Reserved": "#fbbf24",
    "Sold": "var(--error)",
    "Rented": "var(--neon-purple)",
}

LISTING_TYPE_COLORS = {
    "For Sale": "var(--neon-cyan)",
    "For Rent": "var(--accent-hover)",
}

INQUIRY_STATUS_COLORS = {
    "New": "var(--neon-cyan)",
    "Contacted": "#fbbf24",
    "Closed": "var(--success)",
}


def _limit_clause(limit):
    """A LIMIT clause built from a trusted, internal integer - never a
    value taken from request.args or any other user input (every caller
    below passes a hard-coded default or an explicit int). int() also
    guarantees the text that reaches SQL can only ever be digits, the same
    reasoning real_estate_db.py already relies on for the CREATE DATABASE
    statement built from the trusted DB_NAME setting."""
    return " LIMIT " + str(int(limit))


# =====================================================================
# QUERIES
# =====================================================================

def get_dashboard_overview(connection):
    """Every top-level Dashboard 2.0 statistic (Section 2), built from the
    three aggregate queries the Properties/Agents/Inquiries pages already
    run - property_queries.get_property_stats(),
    agent_queries.get_agent_overview_stats() and
    inquiry_queries.get_inquiry_stats(). Nothing here re-implements one of
    those counts with a second query; it only combines the three results
    and adds one metric that is pure arithmetic on numbers already
    fetched - the inquiry closure rate."""
    property_stats = property_queries.get_property_stats(connection)
    agent_stats = agent_queries.get_agent_overview_stats(connection)
    inquiry_stats = inquiry_queries.get_inquiry_stats(connection)

    overview = dict(property_stats)
    overview["total_agents"] = agent_stats["total_agents"]
    overview["agents_with_properties"] = agent_stats["agents_with_properties"]
    overview["unassigned_properties"] = agent_stats["unassigned_properties"]
    overview["total_inquiries"] = inquiry_stats["total"]
    overview["new_inquiries"] = inquiry_stats["new"]
    overview["contacted_inquiries"] = inquiry_stats["contacted"]
    overview["closed_inquiries"] = inquiry_stats["closed"]
    overview["inquiries_today"] = inquiry_stats["today"]

    # Section 4: explicitly an *inquiry* closure rate (closed / total
    # inquiries) - never a sales conversion rate, which the database has
    # no way to compute (nothing links an inquiry to a completed sale).
    if inquiry_stats["total"] > 0:
        overview["closure_rate"] = round(inquiry_stats["closed"] / inquiry_stats["total"] * 100, 1)
    else:
        overview["closure_rate"] = 0.0

    return overview


def get_property_type_stats(connection):
    """Every property type with its property count (Section 3). A LEFT
    JOIN, so a type with zero properties still appears as a real 0 instead
    of silently vanishing from the chart - a trainer should be able to see
    "we have no Land listings right now" just as easily as "we have 5"."""
    cursor = connection.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT pt.name AS label, COUNT(p.id) AS count
        FROM property_types pt
        LEFT JOIN properties p ON p.property_type_id = pt.id
        GROUP BY pt.id, pt.name
        ORDER BY count DESC, pt.name
        """
    )
    rows = cursor.fetchall()
    cursor.close()
    for row in rows:
        row["count"] = int(row["count"] or 0)
    return rows


def get_listing_type_stats(connection):
    """For Sale vs For Rent counts (Section 3). listing_type is a NOT NULL
    ENUM, so every property has exactly one of the two values - a plain
    GROUP BY is enough, no LEFT JOIN needed."""
    cursor = connection.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT listing_type AS label, COUNT(*) AS count
        FROM properties
        GROUP BY listing_type
        ORDER BY listing_type
        """
    )
    rows = cursor.fetchall()
    cursor.close()
    for row in rows:
        row["count"] = int(row["count"] or 0)
    return rows


def get_location_stats(connection, limit=DEFAULT_LOCATION_LIMIT):
    """The locations with the highest number of properties (Section 3) - an
    inner JOIN, since a location with zero properties is not meaningful in
    a "top locations" ranking. Ordered by count desc and capped to `limit`
    rows at the database, so this never pulls every location just to keep
    the top few."""
    cursor = connection.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT l.name AS label, l.city AS city, COUNT(p.id) AS count
        FROM locations l
        JOIN properties p ON p.location_id = l.id
        GROUP BY l.id, l.name, l.city
        ORDER BY count DESC, l.name
        """
        + _limit_clause(limit)
    )
    rows = cursor.fetchall()
    cursor.close()
    for row in rows:
        row["count"] = int(row["count"] or 0)
    return rows


def get_agent_performance(connection):
    """Every agent's real workload and pipeline (Section 5), in one query:
    assigned/available/sold/rented property counts, and how many
    inquiries their properties have received.

    This deliberately joins two derived tables instead of one flat
    properties + inquiries JOIN: an agent with several properties, each
    carrying several inquiries, would otherwise fan out (each property row
    repeated once per inquiry), silently inflating SUM(status = '...')
    past the real count. Grouping properties and inquiries separately
    first, then joining those two already-aggregated results onto
    `agents`, keeps every count correct in a single round trip - not a
    query per agent.

    Sorted by inquiry count then assigned properties, so the busiest
    agents surface first - both are real, queried numbers, never an
    invented score."""
    cursor = connection.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT
            a.id, a.name, a.email,
            COALESCE(pc.assigned, 0) AS assigned,
            COALESCE(pc.available, 0) AS available,
            COALESCE(pc.sold, 0) AS sold,
            COALESCE(pc.rented, 0) AS rented,
            COALESCE(ic.inquiry_count, 0) AS inquiry_count
        FROM agents a
        LEFT JOIN (
            SELECT agent_id,
                   COUNT(*) AS assigned,
                   SUM(status = 'Available') AS available,
                   SUM(status = 'Sold') AS sold,
                   SUM(status = 'Rented') AS rented
            FROM properties
            WHERE agent_id IS NOT NULL
            GROUP BY agent_id
        ) pc ON pc.agent_id = a.id
        LEFT JOIN (
            SELECT p.agent_id, COUNT(i.id) AS inquiry_count
            FROM properties p
            JOIN inquiries i ON i.property_id = p.id
            WHERE p.agent_id IS NOT NULL
            GROUP BY p.agent_id
        ) ic ON ic.agent_id = a.id
        ORDER BY inquiry_count DESC, assigned DESC, a.name
        """
    )
    rows = cursor.fetchall()
    cursor.close()
    for row in rows:
        for field in ("assigned", "available", "sold", "rented", "inquiry_count"):
            row[field] = int(row[field] or 0)
    return rows


def get_recent_properties(connection, limit=DEFAULT_RECENT_LIMIT):
    """The most recently created properties, joined for display (Section
    6) - reuses property_queries.PROPERTY_DETAIL_QUERY, the exact same
    type/location/agent JOIN every other property read in the app already
    uses, instead of a second implementation of it."""
    cursor = connection.cursor(dictionary=True)
    cursor.execute(
        property_queries.PROPERTY_DETAIL_QUERY
        + " ORDER BY p.created_at DESC, p.id DESC"
        + _limit_clause(limit)
    )
    rows = cursor.fetchall()
    cursor.close()
    return rows


def get_recent_inquiries(connection, limit=DEFAULT_RECENT_LIMIT):
    """The most recently received inquiries, joined for display (Section
    6) - reuses inquiry_queries.INQUIRY_BASE_QUERY the same way."""
    cursor = connection.cursor(dictionary=True)
    cursor.execute(
        inquiry_queries.INQUIRY_BASE_QUERY
        + " ORDER BY i.created_at DESC, i.id DESC"
        + _limit_clause(limit)
    )
    rows = cursor.fetchall()
    cursor.close()
    return rows


# =====================================================================
# CHART SHAPING - pure Python, no query. See the module docstring.
# =====================================================================

def _with_bar_widths(rows, min_width=4):
    """Add 'bar_pct' (0-100) to each row - this row's count as a
    percentage of the largest count in the list, for a horizontal bar
    chart. A non-zero row is floored at `min_width` so a small-but-real
    value still renders a visible sliver instead of an invisible bar."""
    top = max((row["count"] for row in rows), default=0)
    result = []
    for row in rows:
        entry = dict(row)
        if top > 0 and row["count"] > 0:
            entry["bar_pct"] = max(min_width, round(row["count"] / top * 100, 1))
        else:
            entry["bar_pct"] = 0
        result.append(entry)
    return result


def _with_share(rows):
    """Add 'percent' (this row's share of the total, 0-100) and the
    cumulative 'start_percent'/'end_percent' each row occupies - what a
    CSS conic-gradient donut or a stacked split-bar needs to lay out its
    segments back to back. The last segment's end is forced to exactly
    100 so rounding never leaves a visible gap at the seam."""
    total = sum(row["count"] for row in rows)
    cumulative = 0.0
    result = []
    for row in rows:
        share = (row["count"] / total * 100) if total else 0.0
        entry = dict(row)
        entry["percent"] = round(share, 1)
        entry["start_percent"] = round(cumulative, 4)
        cumulative += share
        entry["end_percent"] = round(cumulative, 4)
        result.append(entry)
    if result and total:
        result[-1]["end_percent"] = 100.0
    return result


def build_property_status_chart(overview):
    """Properties by Status (Section 7, chart 1) - reuses the
    available/reserved/sold/rented counts get_dashboard_overview() already
    fetched, instead of running a second aggregate query for numbers the
    Dashboard already has."""
    rows = [
        {"label": "Available", "count": overview.get("available", 0)},
        {"label": "Reserved", "count": overview.get("reserved", 0)},
        {"label": "Sold", "count": overview.get("sold", 0)},
        {"label": "Rented", "count": overview.get("rented", 0)},
    ]
    rows = _with_share(rows)
    for row in rows:
        row["color"] = STATUS_COLORS[row["label"]]
    return rows


def build_inquiry_status_chart(overview):
    """Inquiries by Status (Section 7, chart 3) - reuses the
    new/contacted/closed counts get_dashboard_overview() already fetched."""
    rows = [
        {"label": "New", "count": overview.get("new_inquiries", 0)},
        {"label": "Contacted", "count": overview.get("contacted_inquiries", 0)},
        {"label": "Closed", "count": overview.get("closed_inquiries", 0)},
    ]
    rows = _with_share(rows)
    for row in rows:
        row["color"] = INQUIRY_STATUS_COLORS[row["label"]]
    return rows


def build_listing_type_chart(listing_stats):
    """For Sale vs For Rent, as a two-segment split bar with a percent
    share for each - built from get_listing_type_stats()'s rows."""
    rows = _with_share(listing_stats)
    for row in rows:
        row["color"] = LISTING_TYPE_COLORS.get(row["label"], "var(--accent-hover)")
    return rows


def build_property_type_chart(type_stats):
    """Properties by Type (Section 7, chart 2), as bar widths relative to
    the largest type - built from get_property_type_stats()'s rows."""
    return _with_bar_widths(type_stats)


def build_location_chart(location_stats):
    """Top Locations, as bar widths relative to the largest location -
    built from get_location_stats()'s rows."""
    return _with_bar_widths(location_stats)
