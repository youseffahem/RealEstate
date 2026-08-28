"""Architecture tests for the Real Estate schema.

These tests check the *database layer* only: tables, primary keys, foreign
keys, indexes, controlled ENUM values, seed data and idempotency. The HTTP
layer for properties/agents/locations/inquiries is covered by the other
test files (test_properties.py, test_agents.py, test_inquiries.py, ...).

Run with:  python -m pytest -v
"""

import real_estate_db
from conftest import app_module


def _query(sql, params=None):
    connection = app_module.get_connection()
    cursor = connection.cursor()
    cursor.execute(sql, params or ())
    rows = cursor.fetchall()
    cursor.close()
    connection.close()
    return rows


def _table_names():
    rows = _query("SHOW TABLES")
    return {row[0] for row in rows}


def _foreign_keys():
    rows = _query(
        """
        SELECT TABLE_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
        FROM information_schema.KEY_COLUMN_USAGE
        WHERE TABLE_SCHEMA = DATABASE() AND REFERENCED_TABLE_NAME IS NOT NULL
        """
    )
    return {(t, c, rt, rc) for t, c, rt, rc in rows}


# =====================================================================
# TABLES
# =====================================================================

def test_all_real_estate_tables_exist():
    tables = _table_names()
    for name in ("property_types", "locations", "agents", "properties",
                 "property_images", "inquiries"):
        assert name in tables


def test_legacy_products_table_is_removed():
    # The Product CRUD exercise this app started from has been fully
    # removed - init_db() drops the table if an old database still has it.
    assert "products" not in _table_names()


# =====================================================================
# PRIMARY / FOREIGN KEYS
# =====================================================================

def test_every_new_table_has_an_auto_increment_primary_key():
    for table in ("property_types", "locations", "agents", "properties",
                  "property_images", "inquiries"):
        rows = _query(
            """
            SELECT COLUMN_NAME, EXTRA FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_KEY = 'PRI'
            """,
            (table,),
        )
        assert len(rows) == 1, table
        assert rows[0][0] == "id"
        assert "auto_increment" in rows[0][1]


def test_expected_foreign_keys_exist():
    fks = _foreign_keys()
    assert ("properties", "property_type_id", "property_types", "id") in fks
    assert ("properties", "location_id", "locations", "id") in fks
    assert ("properties", "agent_id", "agents", "id") in fks
    assert ("property_images", "property_id", "properties", "id") in fks
    assert ("inquiries", "property_id", "properties", "id") in fks


# =====================================================================
# CONSTRAINTS / CONTROLLED VALUES
# =====================================================================

def test_property_types_name_is_unique():
    rows = _query(
        """
        SELECT COUNT(*) FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'property_types'
          AND INDEX_NAME = 'uq_property_types_name'
        """
    )
    assert rows[0][0] == 1


def test_agents_email_is_unique():
    rows = _query(
        """
        SELECT COUNT(*) FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'agents'
          AND INDEX_NAME = 'uq_agents_email'
        """
    )
    assert rows[0][0] == 1


def test_agents_gender_column_only_allows_male_or_female():
    rows = _query(
        """
        SELECT COLUMN_TYPE, IS_NULLABLE FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'agents'
          AND COLUMN_NAME = 'gender'
        """
    )
    assert len(rows) == 1, "agents.gender must exist"
    column_type, is_nullable = rows[0]
    assert "'Male'" in column_type
    assert "'Female'" in column_type
    assert is_nullable == "NO"


def test_every_seeded_agent_has_a_valid_gender():
    rows = _query("SELECT gender FROM agents")
    assert rows, "there should be at least one seeded agent"
    for (gender,) in rows:
        assert gender in ("Male", "Female")


def test_inserting_an_agent_with_an_invalid_gender_is_rejected_by_the_database():
    import mysql.connector

    connection = app_module.get_connection()
    cursor = connection.cursor()
    try:
        cursor.execute(
            "INSERT INTO agents (name, email, phone, gender) "
            "VALUES ('Invalid Gender Test', 'invalid.gender.test@example.com', '010-0000-0000', 'Other')"
        )
        connection.commit()
        raised = False
    except mysql.connector.Error:
        connection.rollback()
        raised = True
    finally:
        cursor.close()
        connection.close()

    assert raised, "an out-of-range gender should violate the agents.gender ENUM"


def test_listing_type_column_only_allows_for_sale_or_for_rent():
    rows = _query(
        """
        SELECT COLUMN_TYPE FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'properties'
          AND COLUMN_NAME = 'listing_type'
        """
    )
    column_type = rows[0][0]
    assert "'For Sale'" in column_type
    assert "'For Rent'" in column_type


def test_status_column_only_allows_the_four_controlled_values():
    rows = _query(
        """
        SELECT COLUMN_TYPE FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'properties'
          AND COLUMN_NAME = 'status'
        """
    )
    column_type = rows[0][0]
    for value in ("Available", "Reserved", "Sold", "Rented"):
        assert value in column_type


def test_price_column_is_decimal_not_float():
    rows = _query(
        """
        SELECT DATA_TYPE FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'properties'
          AND COLUMN_NAME = 'price'
        """
    )
    assert rows[0][0] == "decimal"


def test_negative_price_is_rejected_by_the_database():
    connection = app_module.get_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT id FROM property_types LIMIT 1")
    type_id = cursor.fetchone()[0]
    cursor.execute("SELECT id FROM locations LIMIT 1")
    location_id = cursor.fetchone()[0]

    import mysql.connector
    try:
        cursor.execute(
            """
            INSERT INTO properties (title, property_type_id, location_id, listing_type, price, area_sqm)
            VALUES ('Invalid Price Test', %s, %s, 'For Sale', -1, 100)
            """,
            (type_id, location_id),
        )
        connection.commit()
        raised = False
    except mysql.connector.Error:
        connection.rollback()
        raised = True
    finally:
        cursor.close()
        connection.close()

    assert raised, "a negative price should violate chk_properties_price"


# =====================================================================
# INDEXES
# =====================================================================

def test_properties_has_the_expected_search_indexes():
    rows = _query(
        """
        SELECT DISTINCT INDEX_NAME FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'properties'
        """
    )
    index_names = {row[0] for row in rows}
    for expected in ("idx_properties_status", "idx_properties_listing_type",
                      "idx_properties_price", "idx_properties_area_sqm"):
        assert expected in index_names


def test_locations_city_is_indexed():
    rows = _query(
        """
        SELECT COUNT(*) FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'locations'
          AND INDEX_NAME = 'idx_locations_city'
        """
    )
    assert rows[0][0] == 1


def test_inquiries_status_is_indexed():
    rows = _query(
        """
        SELECT COUNT(*) FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'inquiries'
          AND INDEX_NAME = 'idx_inquiries_status'
        """
    )
    assert rows[0][0] == 1


# =====================================================================
# SEED DATA / IDEMPOTENCY
# =====================================================================

def test_seed_data_exists_in_the_expected_ranges():
    assert _query("SELECT COUNT(*) FROM property_types")[0][0] == 8
    location_count = _query("SELECT COUNT(*) FROM locations")[0][0]
    assert 8 <= location_count <= 10
    agent_count = _query("SELECT COUNT(*) FROM agents")[0][0]
    assert 4 <= agent_count <= 6
    property_count = _query("SELECT COUNT(*) FROM properties")[0][0]
    assert 10 <= property_count <= 15


def test_property_types_have_no_duplicate_names():
    rows = _query("SELECT name, COUNT(*) FROM property_types GROUP BY name HAVING COUNT(*) > 1")
    assert rows == []


def test_agents_have_no_duplicate_emails():
    rows = _query("SELECT email, COUNT(*) FROM agents GROUP BY email HAVING COUNT(*) > 1")
    assert rows == []


def test_reseeding_is_idempotent_and_creates_no_duplicates():
    before = {
        table: _query(f"SELECT COUNT(*) FROM {table}")[0][0]
        for table in ("property_types", "locations", "agents", "properties",
                      "property_images", "inquiries")
    }

    connection = app_module.get_connection()
    summary = real_estate_db.init_real_estate(connection)
    connection.close()

    assert all(count == 0 for count in summary.values()), summary

    after = {
        table: _query(f"SELECT COUNT(*) FROM {table}")[0][0]
        for table in before
    }
    assert before == after


# =====================================================================
# RELATIONSHIPS
# =====================================================================

def test_every_property_resolves_to_a_type_and_a_location():
    rows = _query(
        """
        SELECT COUNT(*) FROM properties p
        JOIN property_types pt ON pt.id = p.property_type_id
        JOIN locations l ON l.id = p.location_id
        """
    )
    total = _query("SELECT COUNT(*) FROM properties")[0][0]
    assert rows[0][0] == total


def test_property_images_and_inquiries_link_back_to_real_properties():
    orphan_images = _query(
        "SELECT COUNT(*) FROM property_images pi LEFT JOIN properties p ON p.id = pi.property_id WHERE p.id IS NULL"
    )
    orphan_inquiries = _query(
        "SELECT COUNT(*) FROM inquiries i LEFT JOIN properties p ON p.id = i.property_id WHERE p.id IS NULL"
    )
    assert orphan_images[0][0] == 0
    assert orphan_inquiries[0][0] == 0


def test_deleting_a_property_cascades_to_its_images_and_inquiries():
    connection = app_module.get_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT id FROM property_types LIMIT 1")
    type_id = cursor.fetchone()[0]
    cursor.execute("SELECT id FROM locations LIMIT 1")
    location_id = cursor.fetchone()[0]

    cursor.execute(
        """
        INSERT INTO properties (title, property_type_id, location_id, listing_type, price, area_sqm)
        VALUES ('Cascade Test Property', %s, %s, 'For Sale', 100000, 50)
        """,
        (type_id, location_id),
    )
    new_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO property_images (property_id, image_url, sort_order) VALUES (%s, NULL, 0)",
        (new_id,),
    )
    cursor.execute(
        "INSERT INTO inquiries (property_id, name, email, message) VALUES (%s, 'T', 't@example.com', 'hi')",
        (new_id,),
    )
    connection.commit()

    cursor.execute("DELETE FROM properties WHERE id = %s", (new_id,))
    connection.commit()

    cursor.execute("SELECT COUNT(*) FROM property_images WHERE property_id = %s", (new_id,))
    remaining_images = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM inquiries WHERE property_id = %s", (new_id,))
    remaining_inquiries = cursor.fetchone()[0]
    cursor.close()
    connection.close()

    assert remaining_images == 0
    assert remaining_inquiries == 0
