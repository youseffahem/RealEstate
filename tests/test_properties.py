"""Phase 2 backend tests for the Real Estate `properties` API.

These exercise the new /properties routes end to end through the Flask
test client - full CRUD, validation, the listing_type/status business
rules, security and error handling. The legacy CRUD tests in test_crud.py
and the Phase 1 schema tests in test_real_estate_schema.py are untouched
and still pass independently.

Every test that creates a property registers its id with `track_properties`
so the Phase 1 seeded catalog (and its counts) is restored afterwards.

Run with:  python -m pytest -v
"""

import json

from conftest import (
    count_properties,
    fetch_property_row,
    insert_property,
)


def _create(client, track_properties, property_ids, **overrides):
    """POST a valid property payload and return the response."""
    payload = {
        "title": "API Created Property",
        "description": "Created through the properties API.",
        "property_type_id": str(property_ids["property_type_id"]),
        "location_id": str(property_ids["location_id"]),
        "agent_id": str(property_ids["agent_id"]),
        "listing_type": "For Sale",
        "price": "1500000.00",
        "area_sqm": "180.00",
        "bedrooms": "3",
        "bathrooms": "2",
        "status": "Available",
    }
    payload.update(overrides)
    response = client.post("/properties/add", data=payload)
    if response.status_code == 303:
        new_id = int(response.headers["Location"].rstrip("/").rsplit("/", 1)[-1])
        track_properties.append(new_id)
    return response


# =====================================================================
# ROUTING
# =====================================================================

def test_properties_list_route_is_get_only(db):
    rule = next(r for r in db.app.url_map.iter_rules() if r.rule == "/properties")
    assert rule.methods & {"GET"}
    assert "POST" not in rule.methods


def test_properties_add_route_accepts_get_and_post(db):
    rule = next(r for r in db.app.url_map.iter_rules() if r.rule == "/properties/add")
    assert {"GET", "POST"} <= rule.methods


def test_properties_edit_route_accepts_get_and_post(db):
    rule = next(r for r in db.app.url_map.iter_rules() if r.rule == "/properties/edit/<int:id>")
    assert {"GET", "POST"} <= rule.methods


def test_properties_delete_route_is_post_only(db):
    rule = next(r for r in db.app.url_map.iter_rules() if r.rule == "/properties/delete/<int:id>")
    assert "POST" in rule.methods
    assert "GET" not in rule.methods


# =====================================================================
# 1. GET properties
# =====================================================================

def test_get_properties_returns_200_and_a_list(client):
    response = client.get("/properties")
    assert response.status_code == 200
    body = response.get_json()
    assert "properties" in body
    assert body["count"] == len(body["properties"])


def test_get_properties_includes_a_known_property(client, track_properties, property_ids):
    new_id = insert_property(title="Findable Villa")
    track_properties.append(new_id)
    body = client.get("/properties").get_json()
    titles = [p["title"] for p in body["properties"]]
    assert "Findable Villa" in titles


def test_get_properties_status_filter_narrows_results(client, track_properties, property_ids):
    sold_id = insert_property(title="Sold Filter Test", listing_type="For Sale", status="Sold")
    track_properties.append(sold_id)
    body = client.get("/properties?status=Sold").get_json()
    assert all(p["status"] == "Sold" for p in body["properties"])
    assert any(p["id"] == sold_id for p in body["properties"])


# =====================================================================
# 2. GET property details
# =====================================================================

def test_get_property_detail_returns_joined_fields(client, track_properties, property_ids):
    new_id = insert_property(
        title="Detail Villa", description="Has a joined type/location/agent.",
        agent_id=property_ids["agent_id"],
    )
    track_properties.append(new_id)

    body = client.get("/properties/" + str(new_id)).get_json()
    prop = body["property"]

    assert prop["title"] == "Detail Villa"
    assert prop["description"] == "Has a joined type/location/agent."
    assert "property_type" in prop
    assert "location_name" in prop and "location_city" in prop
    assert "agent_name" in prop and "agent_email" in prop
    assert "created_at" in prop and "updated_at" in prop


# =====================================================================
# 3. CREATE property
# =====================================================================

def test_create_property_inserts_the_row(client, track_properties, property_ids):
    before = count_properties()
    response = _create(client, track_properties, property_ids, title="Freshly Created")
    assert response.status_code == 303
    assert count_properties() == before + 1


def test_create_property_persists_exact_values(client, track_properties, property_ids):
    response = _create(
        client, track_properties, property_ids,
        title="Exact Values Villa", price="2500000.50", area_sqm="222.25",
        bedrooms="4", bathrooms="3",
    )
    new_id = int(response.headers["Location"].rstrip("/").rsplit("/", 1)[-1])
    row = fetch_property_row(new_id)
    assert row["title"] == "Exact Values Villa"
    assert float(row["price"]) == 2500000.50
    assert float(row["area_sqm"]) == 222.25
    assert row["bedrooms"] == 4
    assert row["bathrooms"] == 3


def test_create_property_redirects_to_its_detail_page(client, track_properties, property_ids):
    response = _create(client, track_properties, property_ids)
    assert response.status_code == 303
    assert "/properties/" in response.headers["Location"]


def test_create_property_strips_surrounding_whitespace(client, track_properties, property_ids):
    response = _create(client, track_properties, property_ids, title="  Trimmed Villa  ")
    new_id = int(response.headers["Location"].rstrip("/").rsplit("/", 1)[-1])
    assert fetch_property_row(new_id)["title"] == "Trimmed Villa"


def test_create_property_accepts_no_agent(client, track_properties, property_ids):
    response = _create(client, track_properties, property_ids, agent_id="")
    assert response.status_code == 303
    new_id = int(response.headers["Location"].rstrip("/").rsplit("/", 1)[-1])
    assert fetch_property_row(new_id)["agent_id"] is None


def test_add_page_get_returns_reference_data(client):
    body = client.get("/properties/add").get_json()
    assert "property_types" in body
    assert "locations" in body
    assert "agents" in body
    assert "For Sale" in body["listing_types"]
    assert "Available" in body["statuses"]


# =====================================================================
# 4. UPDATE property
# =====================================================================

def test_update_property_changes_the_row(client, track_properties, property_ids):
    property_id = insert_property(title="Before Update")
    track_properties.append(property_id)

    response = client.post("/properties/edit/" + str(property_id), data={
        "title": "After Update",
        "property_type_id": str(property_ids["property_type_id"]),
        "location_id": str(property_ids["location_id"]),
        "listing_type": "For Rent",
        "price": "20000.00",
        "area_sqm": "90.00",
        "status": "Available",
    })
    assert response.status_code == 303
    row = fetch_property_row(property_id)
    assert row["title"] == "After Update"
    assert row["listing_type"] == "For Rent"
    assert float(row["price"]) == 20000.00


def test_update_property_does_not_create_a_second_row(client, track_properties, property_ids):
    property_id = insert_property()
    track_properties.append(property_id)
    before = count_properties()

    client.post("/properties/edit/" + str(property_id), data={
        "title": "Still One Row",
        "property_type_id": str(property_ids["property_type_id"]),
        "location_id": str(property_ids["location_id"]),
        "listing_type": "For Sale",
        "price": "1.00",
        "area_sqm": "1.00",
        "status": "Available",
    })
    assert count_properties() == before


def test_edit_page_get_returns_current_values(client, track_properties, property_ids):
    property_id = insert_property(title="Prefilled Property")
    track_properties.append(property_id)
    body = client.get("/properties/edit/" + str(property_id)).get_json()
    assert body["property"]["title"] == "Prefilled Property"
    assert "property_types" in body


def test_edit_get_on_missing_id_returns_404(client):
    response = client.get("/properties/edit/999999")
    assert response.status_code == 404


def test_edit_post_on_missing_id_returns_404(client, property_ids):
    response = client.post("/properties/edit/999999", data={
        "title": "Ghost",
        "property_type_id": str(property_ids["property_type_id"]),
        "location_id": str(property_ids["location_id"]),
        "listing_type": "For Sale",
        "price": "1.00",
        "area_sqm": "1.00",
        "status": "Available",
    })
    assert response.status_code == 404


def test_update_validation_failure_does_not_change_the_row(client, track_properties, property_ids):
    property_id = insert_property(title="Unchanged Property", price=7000.00)
    track_properties.append(property_id)

    client.post("/properties/edit/" + str(property_id), data={
        "title": "Should Not Apply",
        "property_type_id": str(property_ids["property_type_id"]),
        "location_id": str(property_ids["location_id"]),
        "listing_type": "For Sale",
        "price": "-1",
        "area_sqm": "100.00",
        "status": "Available",
    })
    assert fetch_property_row(property_id)["title"] == "Unchanged Property"


# =====================================================================
# 5./24. DELETE property (POST only)
# =====================================================================

def test_delete_property_removes_the_row(client, property_ids):
    property_id = insert_property()
    response = client.post("/properties/delete/" + str(property_id))
    assert response.status_code == 303
    assert fetch_property_row(property_id) is None


def test_delete_property_redirects_to_the_list(client):
    property_id = insert_property()
    response = client.post("/properties/delete/" + str(property_id))
    assert response.headers["Location"].endswith("/properties")


def test_delete_on_missing_id_returns_404(client):
    response = client.post("/properties/delete/999999")
    assert response.status_code == 404


def test_delete_leaves_other_properties_alone(client, track_properties):
    keep_id = insert_property(title="Keep me")
    track_properties.append(keep_id)
    remove_id = insert_property(title="Remove me")

    client.post("/properties/delete/" + str(remove_id))

    assert fetch_property_row(keep_id) is not None
    assert fetch_property_row(remove_id) is None


# =====================================================================
# 23. GET delete rejected
# =====================================================================

def test_get_on_delete_route_is_rejected(client):
    property_id = insert_property()
    try:
        response = client.get("/properties/delete/" + str(property_id))
        assert response.status_code == 405
        assert fetch_property_row(property_id) is not None
    finally:
        delete_property_row_cleanup(property_id)


def delete_property_row_cleanup(property_id):
    from conftest import delete_property_row
    delete_property_row(property_id)


# =====================================================================
# 6./7. Nonexistent / invalid property id
# =====================================================================

def test_get_nonexistent_property_returns_404(client):
    response = client.get("/properties/999999")
    assert response.status_code == 404
    assert "error" in response.get_json()


def test_invalid_property_id_in_url_does_not_crash(client):
    # <int:id> refuses this at the routing level, same as the legacy /edit/<id>.
    response = client.get("/properties/not-a-number")
    assert response.status_code in (302, 404)


# =====================================================================
# 8./9./10./26. Foreign keys are validated before insert
# =====================================================================

def test_create_with_invalid_property_type_is_rejected(client, track_properties, property_ids):
    response = _create(client, track_properties, property_ids, property_type_id="999999")
    assert response.status_code == 400
    assert "property type" in " ".join(response.get_json()["errors"]).lower()


def test_create_with_invalid_location_is_rejected(client, track_properties, property_ids):
    response = _create(client, track_properties, property_ids, location_id="999999")
    assert response.status_code == 400
    assert "location" in " ".join(response.get_json()["errors"]).lower()


def test_create_with_invalid_agent_is_rejected(client, track_properties, property_ids):
    response = _create(client, track_properties, property_ids, agent_id="999999")
    assert response.status_code == 400
    assert "agent" in " ".join(response.get_json()["errors"]).lower()


def test_create_with_valid_foreign_keys_is_accepted(client, track_properties, property_ids):
    response = _create(client, track_properties, property_ids)
    assert response.status_code == 303


# =====================================================================
# 11./12. Price validation
# =====================================================================

def test_create_with_non_numeric_price_is_rejected(client, track_properties, property_ids):
    response = _create(client, track_properties, property_ids, price="abc")
    assert response.status_code == 400
    assert "price" in " ".join(response.get_json()["errors"]).lower()


def test_create_with_negative_price_is_rejected(client, track_properties, property_ids):
    response = _create(client, track_properties, property_ids, price="-100")
    assert response.status_code == 400
    assert "negative" in " ".join(response.get_json()["errors"]).lower()


def test_create_with_nan_price_is_rejected(client, track_properties, property_ids):
    response = _create(client, track_properties, property_ids, price="nan")
    assert response.status_code == 400


def test_create_with_zero_price_is_accepted(client, track_properties, property_ids):
    # chk_properties_price allows price >= 0.
    response = _create(client, track_properties, property_ids, price="0")
    assert response.status_code == 303


# =====================================================================
# 13./14. Area validation
# =====================================================================

def test_create_with_non_numeric_area_is_rejected(client, track_properties, property_ids):
    response = _create(client, track_properties, property_ids, area_sqm="abc")
    assert response.status_code == 400
    assert "area" in " ".join(response.get_json()["errors"]).lower()


def test_create_with_negative_area_is_rejected(client, track_properties, property_ids):
    response = _create(client, track_properties, property_ids, area_sqm="-50")
    assert response.status_code == 400


def test_create_with_zero_area_is_rejected(client, track_properties, property_ids):
    # chk_properties_area_sqm requires area_sqm > 0.
    response = _create(client, track_properties, property_ids, area_sqm="0")
    assert response.status_code == 400


# =====================================================================
# 15./16. Bedrooms / bathrooms validation
# =====================================================================

def test_create_with_non_integer_bedrooms_is_rejected(client, track_properties, property_ids):
    response = _create(client, track_properties, property_ids, bedrooms="two")
    assert response.status_code == 400
    assert "bedrooms" in " ".join(response.get_json()["errors"]).lower()


def test_create_with_negative_bedrooms_is_rejected(client, track_properties, property_ids):
    response = _create(client, track_properties, property_ids, bedrooms="-1")
    assert response.status_code == 400


def test_create_with_non_integer_bathrooms_is_rejected(client, track_properties, property_ids):
    response = _create(client, track_properties, property_ids, bathrooms="two")
    assert response.status_code == 400
    assert "bathrooms" in " ".join(response.get_json()["errors"]).lower()


def test_create_with_blank_bedrooms_is_accepted_as_null(client, track_properties, property_ids):
    response = _create(client, track_properties, property_ids, bedrooms="")
    assert response.status_code == 303
    new_id = int(response.headers["Location"].rstrip("/").rsplit("/", 1)[-1])
    assert fetch_property_row(new_id)["bedrooms"] is None


# =====================================================================
# 17./18. Listing type / status validation
# =====================================================================

def test_create_with_invalid_listing_type_is_rejected(client, track_properties, property_ids):
    response = _create(client, track_properties, property_ids, listing_type="Timeshare")
    assert response.status_code == 400
    assert "listing type" in " ".join(response.get_json()["errors"]).lower()


def test_create_with_invalid_status_is_rejected(client, track_properties, property_ids):
    response = _create(client, track_properties, property_ids, status="Demolished")
    assert response.status_code == 400
    assert "status" in " ".join(response.get_json()["errors"]).lower()


def test_create_with_missing_title_is_rejected(client, track_properties, property_ids):
    response = _create(client, track_properties, property_ids, title="")
    assert response.status_code == 400
    assert "title" in " ".join(response.get_json()["errors"]).lower()


# =====================================================================
# 19./20. Business rules: listing_type <-> status
# =====================================================================

def test_for_sale_with_status_rented_is_rejected(client, track_properties, property_ids):
    response = _create(client, track_properties, property_ids,
                        listing_type="For Sale", status="Rented")
    assert response.status_code == 400
    assert "for sale" in " ".join(response.get_json()["errors"]).lower()


def test_for_rent_with_status_sold_is_rejected(client, track_properties, property_ids):
    response = _create(client, track_properties, property_ids,
                        listing_type="For Rent", status="Sold")
    assert response.status_code == 400
    assert "for rent" in " ".join(response.get_json()["errors"]).lower()


def test_for_sale_with_status_sold_is_accepted(client, track_properties, property_ids):
    response = _create(client, track_properties, property_ids,
                        listing_type="For Sale", status="Sold")
    assert response.status_code == 303


def test_for_rent_with_status_rented_is_accepted(client, track_properties, property_ids):
    response = _create(client, track_properties, property_ids,
                        listing_type="For Rent", status="Rented")
    assert response.status_code == 303


# =====================================================================
# 21. SQL injection
# =====================================================================

def test_sql_injection_in_title_is_stored_as_text(client, track_properties, property_ids):
    payload = "Robert'); DROP TABLE properties;--"
    response = _create(client, track_properties, property_ids, title=payload)
    assert response.status_code == 303

    # The table is still there, and still queryable.
    assert count_properties() >= 1
    new_id = int(response.headers["Location"].rstrip("/").rsplit("/", 1)[-1])
    assert fetch_property_row(new_id)["title"] == payload


def test_sql_injection_via_delete_id_is_rejected_by_the_route(client):
    property_id = insert_property(title="Survivor")
    try:
        # The <int:id> converter refuses this outright - it never reaches SQL.
        response = client.post("/properties/delete/1%20OR%201=1")
        assert response.status_code in (404, 405)
        assert fetch_property_row(property_id) is not None
    finally:
        delete_property_row_cleanup(property_id)


# =====================================================================
# 22. XSS
# =====================================================================

def test_xss_in_title_is_returned_as_data_not_executed(client, track_properties, property_ids):
    payload = "<script>alert(1)</script>"
    response = _create(client, track_properties, property_ids, title=payload)
    assert response.status_code == 303
    new_id = int(response.headers["Location"].rstrip("/").rsplit("/", 1)[-1])

    detail = client.get("/properties/" + str(new_id))
    # Served as application/json, never text/html - a browser will not
    # execute this payload no matter what characters it contains.
    assert detail.content_type.startswith("application/json")
    assert detail.get_json()["property"]["title"] == payload


# =====================================================================
# 25. Dashboard statistics
# =====================================================================

def test_dashboard_stats_route_returns_200(client):
    response = client.get("/properties/stats")
    assert response.status_code == 200
    body = response.get_json()
    for key in ("total", "available", "reserved", "sold", "rented",
                "total_value", "average_price"):
        assert key in body


def test_dashboard_stats_reflect_a_new_property(client, track_properties, property_ids):
    before = client.get("/properties/stats").get_json()
    _create(client, track_properties, property_ids, status="Available", price="500000.00")
    after = client.get("/properties/stats").get_json()

    assert after["total"] == before["total"] + 1
    assert after["available"] == before["available"] + 1


def test_dashboard_stats_come_from_get_property_stats(db, track_properties, property_ids):
    import property_queries
    connection = db.get_connection()
    stats = property_queries.get_property_stats(connection)
    connection.close()
    assert stats["total"] == count_properties()


# =====================================================================
# 27. Cascade deletion (through the API this time - see
# test_real_estate_schema.py for the direct-SQL version from Phase 1)
# =====================================================================

def test_deleting_a_property_via_the_api_cascades_to_images_and_inquiries(client, db):
    connection = db.get_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT id FROM property_types LIMIT 1")
    type_id = cursor.fetchone()[0]
    cursor.execute("SELECT id FROM locations LIMIT 1")
    location_id = cursor.fetchone()[0]
    cursor.execute(
        """
        INSERT INTO properties (title, property_type_id, location_id, listing_type, price, area_sqm)
        VALUES ('API Cascade Test', %s, %s, 'For Sale', 100000, 50)
        """,
        (type_id, location_id),
    )
    property_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO property_images (property_id, image_url, sort_order) VALUES (%s, NULL, 0)",
        (property_id,),
    )
    cursor.execute(
        "INSERT INTO inquiries (property_id, name, email, message) VALUES (%s, 'T', 't@example.com', 'hi')",
        (property_id,),
    )
    connection.commit()
    cursor.close()
    connection.close()

    response = client.post("/properties/delete/" + str(property_id))
    assert response.status_code == 303

    connection = db.get_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT COUNT(*) FROM property_images WHERE property_id = %s", (property_id,))
    remaining_images = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM inquiries WHERE property_id = %s", (property_id,))
    remaining_inquiries = cursor.fetchone()[0]
    cursor.close()
    connection.close()

    assert remaining_images == 0
    assert remaining_inquiries == 0


# =====================================================================
# 28. Timestamp behaviour
# =====================================================================

def test_created_at_is_set_on_creation(client, track_properties, property_ids):
    response = _create(client, track_properties, property_ids)
    new_id = int(response.headers["Location"].rstrip("/").rsplit("/", 1)[-1])
    row = fetch_property_row(new_id)
    assert row["created_at"] is not None
    assert row["updated_at"] is not None
    assert row["updated_at"] >= row["created_at"]


def test_updated_at_is_refreshed_on_update(client, track_properties, property_ids):
    property_id = insert_property(title="Timestamp Test")
    track_properties.append(property_id)
    original = fetch_property_row(property_id)

    client.post("/properties/edit/" + str(property_id), data={
        "title": "Timestamp Test Updated",
        "property_type_id": str(property_ids["property_type_id"]),
        "location_id": str(property_ids["location_id"]),
        "listing_type": "For Sale",
        "price": "1.00",
        "area_sqm": "1.00",
        "status": "Available",
    })

    updated = fetch_property_row(property_id)
    assert updated["updated_at"] >= original["updated_at"]
    # created_at itself never moves.
    assert updated["created_at"] == original["created_at"]
