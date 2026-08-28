"""Phase 7 tests for Dashboard 2.0 & Analytics.

These exercise analytics_queries.py directly against the real test MySQL
database (data correctness, chart shaping, agent performance, recent
activity), the /dashboard route end to end through the Flask test client,
and the full "create -> verify -> change -> verify -> delete -> verify
back to baseline" live-data cycle described in the Phase 7 spec (Section
15). Every test that creates a property, agent or inquiry registers its id
with track_properties / track_agents / track_inquiries so the seeded
catalog and its counts (test_real_estate_schema.py) are restored
afterwards - the same rule test_properties.py / test_agents.py /
test_inquiries.py already follow.

Run with:  python -m pytest -v
"""

import mysql.connector
import pytest

import agent_queries
import analytics_queries
import inquiry_queries
import property_queries
from conftest import (
    fetch_property_row,
    get_agent_id,
    get_location_id,
    get_property_type_id,
    insert_agent,
    insert_inquiry,
    insert_property,
)


# =====================================================================
# Dashboard page
# =====================================================================

def test_dashboard_page_loads(client):
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "Real Estate Dashboard" in response.get_data(as_text=True)


def test_dashboard_shows_every_required_section(client):
    html = client.get("/dashboard").get_data(as_text=True)
    for text in (
        "Total properties", "Available", "Reserved", "Sold", "Rented",
        "Total portfolio value", "Average property price",
        "Total agents", "Total inquiries", "New inquiries",
        "Contacted inquiries", "Closed inquiries",
        "Properties by Status", "Properties by Type",
        "Properties by Listing Type", "Top Locations",
        "Inquiry Analytics", "inquiry closure rate",
        "Agent Performance", "Recent Properties", "Recent Inquiries",
    ):
        assert text in html, "missing %r on the dashboard" % text


def test_dashboard_recent_property_links_to_property_details(client):
    html = client.get("/dashboard").get_data(as_text=True)
    # At least one seeded property is recent enough to appear.
    assert "/properties/view/" in html


def test_dashboard_agent_performance_links_to_agent_details(client):
    html = client.get("/dashboard").get_data(as_text=True)
    assert "/agents/" in html


def test_dashboard_survives_a_database_error(client, monkeypatch):
    """Section 13: never expose a raw database error - the page still
    renders, with a flashed message and safe zeroed-out statistics."""
    import app as app_module

    def broken_connection():
        raise mysql.connector.Error("boom")

    monkeypatch.setattr(app_module, "get_connection", broken_connection)
    response = client.get("/dashboard")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "boom" not in html
    assert "Could not load the dashboard statistics" in html


def test_dashboard_ignores_query_string_injection_attempts(client):
    """The route reads no query parameters at all, so a hostile query
    string can never reach SQL - this just proves the page still renders
    normally and nothing in the properties table is touched."""
    before = property_queries.get_property_stats(_conn())["total"]
    response = client.get("/dashboard?status=Available'; DROP TABLE properties;--")
    assert response.status_code == 200
    after = property_queries.get_property_stats(_conn())["total"]
    assert before == after


def _conn():
    """A fresh connection with autocommit on. Every real dashboard request
    opens (and quickly closes) its own brand-new connection, so it always
    sees the latest committed data. A test that keeps one connection open
    across several steps needs autocommit for the same reason - without
    it, MySQL's default REPEATABLE READ isolation would pin this
    connection's very first read to a snapshot from before a later step's
    insert/update on some *other* connection ever committed, and every
    read after that would keep seeing stale data for the rest of the
    transaction."""
    import app as app_module
    connection = app_module.get_connection()
    connection.autocommit = True
    return connection


# =====================================================================
# get_dashboard_overview() - data correctness (Section 14)
# =====================================================================

def test_overview_matches_property_queries_stats(db):
    connection = db.get_connection()
    overview = analytics_queries.get_dashboard_overview(connection)
    direct = property_queries.get_property_stats(connection)
    connection.close()

    for key in ("total", "available", "reserved", "sold", "rented", "total_value", "average_price"):
        assert overview[key] == direct[key]


def test_overview_total_matches_raw_sql_count(db):
    connection = db.get_connection()
    overview = analytics_queries.get_dashboard_overview(connection)
    cursor = connection.cursor()
    cursor.execute("SELECT COUNT(*) FROM properties")
    total = cursor.fetchone()[0]
    cursor.execute("SELECT SUM(price) FROM properties")
    total_value = float(cursor.fetchone()[0] or 0)
    cursor.execute("SELECT AVG(price) FROM properties")
    average_price = float(cursor.fetchone()[0] or 0)
    cursor.close()
    connection.close()

    assert overview["total"] == total
    assert abs(overview["total_value"] - total_value) < 0.01
    assert abs(overview["average_price"] - average_price) < 0.01


def test_overview_matches_agent_overview_stats(db):
    connection = db.get_connection()
    overview = analytics_queries.get_dashboard_overview(connection)
    direct = agent_queries.get_agent_overview_stats(connection)
    connection.close()

    assert overview["total_agents"] == direct["total_agents"]
    assert overview["agents_with_properties"] == direct["agents_with_properties"]
    assert overview["unassigned_properties"] == direct["unassigned_properties"]


def test_overview_matches_inquiry_stats(db):
    connection = db.get_connection()
    overview = analytics_queries.get_dashboard_overview(connection)
    direct = inquiry_queries.get_inquiry_stats(connection)
    connection.close()

    assert overview["total_inquiries"] == direct["total"]
    assert overview["new_inquiries"] == direct["new"]
    assert overview["contacted_inquiries"] == direct["contacted"]
    assert overview["closed_inquiries"] == direct["closed"]
    assert overview["inquiries_today"] == direct["today"]


def test_closure_rate_is_closed_over_total(db):
    connection = db.get_connection()
    overview = analytics_queries.get_dashboard_overview(connection)
    connection.close()

    if overview["total_inquiries"] == 0:
        assert overview["closure_rate"] == 0.0
    else:
        expected = round(overview["closed_inquiries"] / overview["total_inquiries"] * 100, 1)
        assert overview["closure_rate"] == expected


# =====================================================================
# Property analytics (Section 3)
# =====================================================================

def test_property_type_stats_include_every_seeded_type(db):
    connection = db.get_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT COUNT(*) FROM property_types")
    type_count = cursor.fetchone()[0]
    cursor.close()

    rows = analytics_queries.get_property_type_stats(connection)
    total = property_queries.get_property_stats(connection)["total"]
    connection.close()

    assert len(rows) == type_count
    assert sum(row["count"] for row in rows) == total


def test_property_type_stats_ordered_by_count_desc(db):
    connection = db.get_connection()
    rows = analytics_queries.get_property_type_stats(connection)
    connection.close()

    counts = [row["count"] for row in rows]
    assert counts == sorted(counts, reverse=True)


def test_listing_type_stats_sum_to_total(db):
    connection = db.get_connection()
    rows = analytics_queries.get_listing_type_stats(connection)
    total = property_queries.get_property_stats(connection)["total"]
    connection.close()

    labels = {row["label"] for row in rows}
    assert labels <= {"For Sale", "For Rent"}
    assert sum(row["count"] for row in rows) == total


def test_location_stats_ordered_desc_and_capped(db):
    connection = db.get_connection()
    rows = analytics_queries.get_location_stats(connection, limit=3)
    connection.close()

    assert len(rows) <= 3
    counts = [row["count"] for row in rows]
    assert counts == sorted(counts, reverse=True)
    assert all(row["count"] > 0 for row in rows)


def test_build_property_status_chart_percentages_sum_to_100(db):
    connection = db.get_connection()
    overview = analytics_queries.get_dashboard_overview(connection)
    connection.close()

    chart = analytics_queries.build_property_status_chart(overview)
    assert sum(row["count"] for row in chart) == overview["total"]
    if overview["total"]:
        assert chart[-1]["end_percent"] == 100.0
        assert abs(sum(row["percent"] for row in chart) - 100.0) < 1.0


def test_build_listing_type_chart_has_colors(db):
    connection = db.get_connection()
    rows = analytics_queries.get_listing_type_stats(connection)
    connection.close()

    chart = analytics_queries.build_listing_type_chart(rows)
    for row in chart:
        assert row["color"]


# =====================================================================
# Agent performance (Section 5)
# =====================================================================

def test_agent_performance_assigned_matches_properties_table(db):
    connection = db.get_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT COUNT(*) FROM properties WHERE agent_id IS NOT NULL")
    assigned_total = cursor.fetchone()[0]
    cursor.close()

    rows = analytics_queries.get_agent_performance(connection)
    connection.close()

    assert sum(row["assigned"] for row in rows) == assigned_total


def test_agent_performance_inquiry_count_matches_join(db):
    connection = db.get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT COUNT(*) FROM inquiries i
        JOIN properties p ON p.id = i.property_id
        WHERE p.agent_id IS NOT NULL
        """
    )
    expected = cursor.fetchone()[0]
    cursor.close()

    rows = analytics_queries.get_agent_performance(connection)
    connection.close()

    assert sum(row["inquiry_count"] for row in rows) == expected


def test_agent_performance_no_fan_out_double_counting(db, track_agents, track_properties, track_inquiries):
    """An agent with two properties, each with two inquiries, must still
    report assigned=2 and inquiry_count=4 - not 8 (the classic fan-out bug
    from a flat properties+inquiries JOIN)."""
    agent_id = insert_agent(name="Fan-out Test Agent", email="fanout.test.agent@example.com")
    track_agents.append(agent_id)

    property_type_id = get_property_type_id()
    location_id = get_location_id()
    property_ids = []
    for i in range(2):
        pid = insert_property(
            title="Fan-out Property %s" % i, property_type_id=property_type_id,
            location_id=location_id, agent_id=agent_id, status="Available",
        )
        track_properties.append(pid)
        property_ids.append(pid)
        for j in range(2):
            iid = insert_inquiry(pid, name="Fan-out Inquirer %s-%s" % (i, j),
                                  email="fanout.%s.%s@example.com" % (i, j))
            track_inquiries.append(iid)

    connection = _conn()
    rows = analytics_queries.get_agent_performance(connection)
    connection.close()

    row = next(r for r in rows if r["id"] == agent_id)
    assert row["assigned"] == 2
    assert row["available"] == 2
    assert row["inquiry_count"] == 4


def test_agent_performance_sorted_by_inquiry_count_then_assigned(db):
    connection = db.get_connection()
    rows = analytics_queries.get_agent_performance(connection)
    connection.close()

    pairs = [(row["inquiry_count"], row["assigned"]) for row in rows]
    assert pairs == sorted(pairs, reverse=True)


# =====================================================================
# Recent activity (Section 6)
# =====================================================================

def test_recent_properties_ordered_newest_first_and_limited(db, track_properties):
    property_type_id = get_property_type_id()
    location_id = get_location_id()
    ids = []
    for i in range(3):
        pid = insert_property(title="Recent Order Test %s" % i, property_type_id=property_type_id,
                               location_id=location_id)
        track_properties.append(pid)
        ids.append(pid)

    connection = _conn()
    rows = analytics_queries.get_recent_properties(connection, limit=2)
    connection.close()

    assert len(rows) == 2
    # The two most recently created properties come first (highest id).
    assert rows[0]["id"] == ids[-1]
    assert rows[1]["id"] == ids[-2]


def test_recent_inquiries_ordered_newest_first_and_limited(db, track_properties, track_inquiries):
    pid = insert_property(title="Recent Inquiries Host Property",
                           property_type_id=get_property_type_id(), location_id=get_location_id())
    track_properties.append(pid)

    ids = []
    for i in range(3):
        iid = insert_inquiry(pid, name="Recent Order Inquirer %s" % i,
                              email="recent.order.%s@example.com" % i)
        track_inquiries.append(iid)
        ids.append(iid)

    connection = _conn()
    rows = analytics_queries.get_recent_inquiries(connection, limit=2)
    connection.close()

    assert len(rows) == 2
    assert rows[0]["id"] == ids[-1]
    assert rows[1]["id"] == ids[-2]


def test_recent_queries_limit_only_ever_accepts_a_real_integer():
    """_limit_clause() is only ever built from int(limit) - passing
    anything that is not a plain integer must fail loudly instead of ever
    reaching SQL as text (Section 13: no interpolated user input)."""
    connection = _conn()
    with pytest.raises(ValueError):
        analytics_queries.get_recent_properties(connection, limit="5); DROP TABLE properties;--")
    connection.close()


# =====================================================================
# Section 15 - full live-data verification cycle
# =====================================================================

def test_live_dashboard_cycle_create_update_delete(db, track_properties, track_agents, track_inquiries):
    connection = _conn()

    # 1. Record dashboard statistics.
    baseline = analytics_queries.get_dashboard_overview(connection)
    baseline_agent_rows = {row["id"]: row for row in analytics_queries.get_agent_performance(connection)}

    # 2. Create a property (unassigned at first).
    property_type_id = get_property_type_id()
    location_id = get_location_id()
    new_price = 123456.78
    property_id = insert_property(
        title="Live Verification Property", property_type_id=property_type_id,
        location_id=location_id, agent_id=None, status="Available", price=new_price,
    )
    track_properties.append(property_id)

    # 3. Verify dashboard statistics update.
    after_create = analytics_queries.get_dashboard_overview(connection)
    assert after_create["total"] == baseline["total"] + 1
    assert after_create["available"] == baseline["available"] + 1
    assert abs(after_create["total_value"] - (baseline["total_value"] + new_price)) < 0.01

    # 4. Assign an agent.
    agent_id = get_agent_id()
    cursor = connection.cursor()
    cursor.execute("UPDATE properties SET agent_id = %s WHERE id = %s", (agent_id, property_id))
    connection.commit()
    cursor.close()

    # 5. Verify agent statistics update.
    after_assign_rows = {row["id"]: row for row in analytics_queries.get_agent_performance(connection)}
    baseline_assigned = baseline_agent_rows.get(agent_id, {"assigned": 0, "available": 0})["assigned"]
    baseline_available = baseline_agent_rows.get(agent_id, {"assigned": 0, "available": 0})["available"]
    assert after_assign_rows[agent_id]["assigned"] == baseline_assigned + 1
    assert after_assign_rows[agent_id]["available"] == baseline_available + 1

    # 6. Create an inquiry.
    inquiry_id = insert_inquiry(property_id, name="Live Verification Inquirer",
                                 email="live.verification@example.com", status="New")
    track_inquiries.append(inquiry_id)

    # 7. Verify inquiry statistics update.
    after_inquiry = analytics_queries.get_dashboard_overview(connection)
    assert after_inquiry["total_inquiries"] == baseline["total_inquiries"] + 1
    assert after_inquiry["new_inquiries"] == baseline["new_inquiries"] + 1
    after_inquiry_agent_rows = {row["id"]: row for row in analytics_queries.get_agent_performance(connection)}
    baseline_inquiry_count = baseline_agent_rows.get(agent_id, {"inquiry_count": 0})["inquiry_count"]
    assert after_inquiry_agent_rows[agent_id]["inquiry_count"] == baseline_inquiry_count + 1

    # 8. Change inquiry status (New -> Contacted).
    cursor = connection.cursor()
    cursor.execute("UPDATE inquiries SET status = 'Contacted' WHERE id = %s", (inquiry_id,))
    connection.commit()
    cursor.close()

    # 9. Verify the correct status count changes.
    after_status_change = analytics_queries.get_dashboard_overview(connection)
    assert after_status_change["new_inquiries"] == after_inquiry["new_inquiries"] - 1
    assert after_status_change["contacted_inquiries"] == after_inquiry["contacted_inquiries"] + 1
    assert after_status_change["total_inquiries"] == after_inquiry["total_inquiries"]

    # 10. Delete the inquiry.
    inquiry_queries.delete_inquiry(connection, inquiry_id)

    # 11. Delete the property.
    property_queries.delete_property(connection, property_id)

    # 12. Verify dashboard returns to the original values.
    final = analytics_queries.get_dashboard_overview(connection)
    assert final == baseline
    final_agent_rows = {row["id"]: row for row in analytics_queries.get_agent_performance(connection)}
    assert final_agent_rows.get(agent_id) == baseline_agent_rows.get(agent_id)
    assert fetch_property_row(property_id) is None

    connection.close()


# =====================================================================
# Performance - no N+1 query pattern (Section 10 / 20)
# =====================================================================

class _CountingCursor:
    """Wraps a real mysql.connector cursor and counts every execute()
    call, so a test can assert the dashboard runs a fixed, small number
    of queries - never one per row."""

    def __init__(self, real_cursor, counter):
        self._real_cursor = real_cursor
        self._counter = counter

    def execute(self, *args, **kwargs):
        self._counter[0] += 1
        return self._real_cursor.execute(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._real_cursor, name)


class _CountingConnection:
    """Wraps a real connection so every cursor() it hands out is a
    _CountingCursor sharing the same counter."""

    def __init__(self, real_connection, counter):
        self._real_connection = real_connection
        self._counter = counter

    def cursor(self, *args, **kwargs):
        return _CountingCursor(self._real_connection.cursor(*args, **kwargs), self._counter)

    def __getattr__(self, name):
        return getattr(self._real_connection, name)


def _run_full_dashboard_query_set(connection):
    analytics_queries.get_dashboard_overview(connection)
    analytics_queries.get_property_type_stats(connection)
    analytics_queries.get_listing_type_stats(connection)
    analytics_queries.get_location_stats(connection)
    analytics_queries.get_agent_performance(connection)
    analytics_queries.get_recent_properties(connection)
    analytics_queries.get_recent_inquiries(connection)


def test_dashboard_runs_a_fixed_number_of_queries(db):
    counter = [0]
    connection = _CountingConnection(_conn(), counter)
    _run_full_dashboard_query_set(connection)
    connection._real_connection.close()

    # get_dashboard_overview: 1 (property_queries.get_property_stats) +
    # 3 (agent_queries.get_agent_overview_stats) + 1 (inquiry_queries.
    # get_inquiry_stats) = 5, then + 1 (type) + 1 (listing) + 1 (location)
    # + 1 (agent performance) + 1 (recent properties) + 1 (recent
    # inquiries) = 11 - a fixed number, however many properties/agents/
    # inquiries exist (see the next test).
    assert counter[0] == 11


def test_dashboard_query_count_does_not_grow_with_more_rows(db, track_properties, track_agents, track_inquiries):
    property_type_id = get_property_type_id()
    location_id = get_location_id()
    for i in range(5):
        agent_id = insert_agent(name="Load Test Agent %s" % i, email="load.test.agent.%s@example.com" % i)
        track_agents.append(agent_id)
        pid = insert_property(title="Load Test Property %s" % i, property_type_id=property_type_id,
                               location_id=location_id, agent_id=agent_id)
        track_properties.append(pid)
        iid = insert_inquiry(pid, name="Load Test Inquirer %s" % i, email="load.test.inquirer.%s@example.com" % i)
        track_inquiries.append(iid)

    counter = [0]
    connection = _CountingConnection(_conn(), counter)
    _run_full_dashboard_query_set(connection)
    connection._real_connection.close()

    assert counter[0] == 11
