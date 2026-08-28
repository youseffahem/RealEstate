"""Full CRUD test suite for the TANTAWY product manager.

Covers the four operations the assignment asks for, plus validation,
error handling and the security properties (parameterised SQL, escaped
output, POST-only delete).

Run with:  python -m pytest -v
"""

from conftest import count_products, fetch_product, insert_product


# =====================================================================
# ROUTING - the four CRUD endpoints exist with the right methods
# =====================================================================

def test_index_route_is_get_only(db):
    rule = next(r for r in db.app.url_map.iter_rules() if r.rule == "/")
    assert rule.methods & {"GET"}
    assert "POST" not in rule.methods


def test_add_route_accepts_get_and_post(db):
    rule = next(r for r in db.app.url_map.iter_rules() if r.rule == "/add")
    assert {"GET", "POST"} <= rule.methods


def test_edit_route_accepts_get_and_post(db):
    rule = next(r for r in db.app.url_map.iter_rules() if r.rule == "/edit/<int:id>")
    assert {"GET", "POST"} <= rule.methods


def test_delete_route_is_post_only(db):
    rule = next(r for r in db.app.url_map.iter_rules() if r.rule == "/delete/<int:id>")
    assert "POST" in rule.methods
    assert "GET" not in rule.methods


# =====================================================================
# READ
# =====================================================================

def test_index_returns_200(client):
    assert client.get("/").status_code == 200


def test_index_lists_a_product_name(client):
    insert_product(name="Readable Widget")
    body = client.get("/").get_data(as_text=True)
    assert "Readable Widget" in body


def test_index_shows_formatted_price(client):
    insert_product(name="Priced Widget", price=8420.5)
    body = client.get("/").get_data(as_text=True)
    assert "8,420.50" in body


def test_index_shows_empty_state_when_no_products(client):
    body = client.get("/").get_data(as_text=True)
    assert "No products yet" in body


def test_index_hides_empty_state_when_products_exist(client):
    insert_product()
    body = client.get("/").get_data(as_text=True)
    assert "No products yet" not in body


def test_index_shows_product_count_badge(client):
    for i in range(3):
        insert_product(name="Widget " + str(i))
    body = client.get("/").get_data(as_text=True)
    assert 'data-count>3<' in body.replace(" ", "")


# =====================================================================
# STATISTICS - real aggregates, never hard coded
# =====================================================================

def test_stats_total_matches_row_count(client, db):
    for i in range(4):
        insert_product(name="Stat " + str(i), price=10)
    assert db.get_stats()["total"] == count_products() == 4


def test_stats_sum_and_average_are_computed(client, db):
    insert_product(name="A", price=100)
    insert_product(name="B", price=300)
    stats = db.get_stats()
    assert stats["total_value"] == 400.0
    assert stats["average_price"] == 200.0


def test_stats_are_zero_on_empty_table(client, db):
    stats = db.get_stats()
    assert stats["total"] == 0
    assert stats["total_value"] == 0.0
    assert stats["latest"] is None


def test_stats_latest_is_the_newest_row(client, db):
    insert_product(name="Older")
    insert_product(name="Newest")
    assert db.get_stats()["latest"] == "Newest"


def test_stats_update_after_a_create(client, db):
    before = db.get_stats()["total"]
    client.post("/add", data={"name": "Fresh", "price": "5.00", "description": "d"})
    assert db.get_stats()["total"] == before + 1


# =====================================================================
# CREATE
# =====================================================================

def test_add_page_returns_200_with_a_form(client):
    body = client.get("/add").get_data(as_text=True)
    assert 'id="product-form"' in body
    assert 'name="name"' in body


def test_create_inserts_the_row(client):
    client.post("/add", data={
        "name": "Created Widget", "price": "19.99", "description": "Brand new."})
    assert count_products() == 1


def test_create_persists_the_exact_values(client):
    client.post("/add", data={
        "name": "Exact Widget", "price": "42.50", "description": "Exactly this."})
    row = fetch_product(1) or _first_row()
    assert row["name"] == "Exact Widget"
    assert float(row["price"]) == 42.50
    assert row["description"] == "Exactly this."


def test_create_redirects_to_the_catalog(client):
    response = client.post("/add", data={
        "name": "Redirect Widget", "price": "1.00", "description": "d"})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_create_flashes_success_with_the_product_name(client):
    response = client.post("/add", data={
        "name": "Flash Widget", "price": "1.00", "description": "d"},
        follow_redirects=True)
    body = response.get_data(as_text=True)
    assert "Flash Widget" in body and "has been added" in body


def test_create_strips_surrounding_whitespace(client):
    client.post("/add", data={
        "name": "  Trimmed  ", "price": " 3.00 ", "description": "  spaced  "})
    assert _first_row()["name"] == "Trimmed"


# =====================================================================
# UPDATE
# =====================================================================

def test_edit_page_prefills_the_current_values(client):
    product_id = insert_product(name="Prefilled", price=12.00, description="Old text.")
    body = client.get("/edit/" + str(product_id)).get_data(as_text=True)
    assert 'value="Prefilled"' in body
    assert "Old text." in body


def test_update_changes_the_row(client):
    product_id = insert_product(name="Before", price=1.00, description="old")
    client.post("/edit/" + str(product_id), data={
        "name": "After", "price": "2.50", "description": "new"})
    row = fetch_product(product_id)
    assert row["name"] == "After"
    assert float(row["price"]) == 2.50
    assert row["description"] == "new"


def test_update_redirects_to_the_catalog(client):
    product_id = insert_product()
    response = client.post("/edit/" + str(product_id), data={
        "name": "X", "price": "1.00", "description": "d"})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_update_flashes_success(client):
    product_id = insert_product()
    body = client.post("/edit/" + str(product_id), data={
        "name": "Updated Widget", "price": "1.00", "description": "d"},
        follow_redirects=True).get_data(as_text=True)
    assert "has been updated" in body


def test_update_does_not_create_a_second_row(client):
    product_id = insert_product()
    client.post("/edit/" + str(product_id), data={
        "name": "Still One", "price": "1.00", "description": "d"})
    assert count_products() == 1


def test_edit_get_on_missing_id_redirects_with_a_message(client):
    body = client.get("/edit/999999", follow_redirects=True).get_data(as_text=True)
    assert "does not exist" in body


def test_edit_post_on_missing_id_redirects_with_a_message(client):
    body = client.post("/edit/999999", data={
        "name": "Ghost", "price": "1.00", "description": "d"},
        follow_redirects=True).get_data(as_text=True)
    assert "does not exist" in body


# =====================================================================
# DELETE
# =====================================================================

def test_delete_removes_the_row(client):
    product_id = insert_product()
    client.post("/delete/" + str(product_id))
    assert fetch_product(product_id) is None
    assert count_products() == 0


def test_delete_redirects_to_the_catalog(client):
    product_id = insert_product()
    response = client.post("/delete/" + str(product_id))
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_delete_flashes_success(client):
    product_id = insert_product()
    body = client.post("/delete/" + str(product_id),
                       follow_redirects=True).get_data(as_text=True)
    assert "has been deleted" in body


def test_delete_on_missing_id_reports_it(client):
    body = client.post("/delete/999999", follow_redirects=True).get_data(as_text=True)
    assert "does not exist" in body


def test_delete_leaves_other_products_alone(client):
    keep = insert_product(name="Keep me")
    remove = insert_product(name="Remove me")
    client.post("/delete/" + str(remove))
    assert fetch_product(keep) is not None
    assert count_products() == 1


def test_delete_is_not_reachable_by_get(client):
    product_id = insert_product()
    response = client.get("/delete/" + str(product_id))
    # The 405 handler keeps the user inside the app instead of showing
    # the default Werkzeug error page.
    assert response.status_code == 302
    assert fetch_product(product_id) is not None


def test_get_delete_lands_back_on_the_catalog_with_a_message(client):
    product_id = insert_product()
    body = client.get("/delete/" + str(product_id),
                      follow_redirects=True).get_data(as_text=True)
    assert "from the page itself" in body


# =====================================================================
# VALIDATION
# =====================================================================

def test_missing_name_is_rejected(client):
    body = client.post("/add", data={
        "name": "", "price": "1.00", "description": "d"}).get_data(as_text=True)
    assert "Name is required" in body
    assert count_products() == 0


def test_missing_price_is_rejected(client):
    body = client.post("/add", data={
        "name": "N", "price": "", "description": "d"}).get_data(as_text=True)
    assert "Price is required" in body
    assert count_products() == 0


def test_missing_description_is_rejected(client):
    body = client.post("/add", data={
        "name": "N", "price": "1.00", "description": ""}).get_data(as_text=True)
    assert "Description is required" in body
    assert count_products() == 0


def test_whitespace_only_name_is_rejected(client):
    body = client.post("/add", data={
        "name": "     ", "price": "1.00", "description": "d"}).get_data(as_text=True)
    assert "Name is required" in body


def test_non_numeric_price_is_rejected(client):
    body = client.post("/add", data={
        "name": "N", "price": "abc", "description": "d"}).get_data(as_text=True)
    assert "Price must be a number" in body
    assert count_products() == 0


def test_negative_price_is_rejected(client):
    body = client.post("/add", data={
        "name": "N", "price": "-5", "description": "d"}).get_data(as_text=True)
    assert "cannot be negative" in body
    assert count_products() == 0


def test_nan_price_is_rejected(client):
    body = client.post("/add", data={
        "name": "N", "price": "nan", "description": "d"}).get_data(as_text=True)
    assert "must be a real number" in body
    assert count_products() == 0


def test_infinity_price_is_rejected(client):
    body = client.post("/add", data={
        "name": "N", "price": "inf", "description": "d"}).get_data(as_text=True)
    assert "must be a real number" in body
    assert count_products() == 0


def test_huge_exponent_price_is_rejected(client):
    body = client.post("/add", data={
        "name": "N", "price": "1e400", "description": "d"}).get_data(as_text=True)
    assert "must be a real number" in body
    assert count_products() == 0


def test_price_beyond_the_column_maximum_is_rejected(client):
    body = client.post("/add", data={
        "name": "N", "price": "999999999999", "description": "d"}).get_data(as_text=True)
    assert "less than 100,000,000" in body
    assert count_products() == 0


def test_price_at_the_column_maximum_is_accepted(client):
    client.post("/add", data={
        "name": "Max", "price": "99999999.99", "description": "d"})
    assert count_products() == 1


def test_zero_price_is_accepted(client):
    client.post("/add", data={"name": "Free", "price": "0", "description": "d"})
    assert count_products() == 1


def test_over_long_name_is_rejected(client):
    body = client.post("/add", data={
        "name": "x" * 121, "price": "1.00", "description": "d"}).get_data(as_text=True)
    assert "120 characters" in body
    assert count_products() == 0


def test_validation_failure_keeps_what_the_user_typed(client):
    body = client.post("/add", data={
        "name": "Kept Name", "price": "abc", "description": "Kept description."
    }).get_data(as_text=True)
    assert 'value="Kept Name"' in body
    assert "Kept description." in body


def test_update_validation_failure_does_not_change_the_row(client):
    product_id = insert_product(name="Unchanged", price=7.00)
    client.post("/edit/" + str(product_id), data={
        "name": "New", "price": "-1", "description": "d"})
    assert fetch_product(product_id)["name"] == "Unchanged"


# =====================================================================
# SECURITY
# =====================================================================

def test_sql_injection_in_name_is_stored_as_text(client):
    payload = "Robert'); DROP TABLE products;--"
    client.post("/add", data={
        "name": payload, "price": "1.00", "description": "d"})
    # The table is still there and the payload was stored, not executed.
    assert count_products() == 1
    assert _first_row()["name"] == payload


def test_sql_injection_in_description_is_stored_as_text(client):
    payload = "' OR '1'='1"
    client.post("/add", data={
        "name": "N", "price": "1.00", "description": payload})
    assert _first_row()["description"] == payload


def test_sql_injection_via_delete_does_not_wipe_the_table(client):
    insert_product(name="Survivor")
    # The <int:id> converter refuses this outright.
    client.post("/delete/1%20OR%201=1")
    assert count_products() == 1


def test_xss_in_name_is_escaped_in_the_catalog(client):
    insert_product(name="<script>alert(1)</script>")
    body = client.get("/").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body


def test_xss_in_description_is_escaped_in_the_catalog(client):
    insert_product(name="N", description="<img src=x onerror=alert(1)>")
    body = client.get("/").get_data(as_text=True)
    assert "<img src=x onerror=alert(1)>" not in body


def test_xss_in_a_flash_message_is_escaped(client):
    body = client.post("/add", data={
        "name": "<b>bold</b>", "price": "1.00", "description": "d"},
        follow_redirects=True).get_data(as_text=True)
    assert "<b>bold</b>" not in body
    assert "&lt;b&gt;bold&lt;/b&gt;" in body


# =====================================================================
# ERROR HANDLING
# =====================================================================

def test_unknown_url_redirects_to_the_catalog(client):
    response = client.get("/no-such-page")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_unknown_url_shows_a_message(client):
    body = client.get("/no-such-page", follow_redirects=True).get_data(as_text=True)
    assert "does not exist" in body


def test_non_numeric_product_id_does_not_crash(client):
    response = client.get("/edit/not-a-number", follow_redirects=True)
    assert response.status_code == 200


# =====================================================================
# HELPERS AND FILTERS
# =====================================================================

def test_money_filter_formats_thousands(db):
    assert db.money(8420.5) == "8,420.50"


def test_money_filter_survives_bad_input(db):
    assert db.money(None) == "0.00"
    assert db.money("not a number") == "0.00"


def test_validate_accepts_a_good_product(db):
    assert db.validate({"name": "N", "price": "1.00", "description": "d"}) is None


def test_seed_does_not_duplicate_on_a_populated_table(client, db):
    insert_product(name="Already here")
    connection = db.get_connection()
    cursor = connection.cursor()
    inserted = db.seed_products(cursor)
    connection.commit()
    cursor.close()
    connection.close()
    assert inserted == 0
    assert count_products() == 1


def test_seed_fills_an_empty_table(client, db):
    connection = db.get_connection()
    cursor = connection.cursor()
    inserted = db.seed_products(cursor)
    connection.commit()
    cursor.close()
    connection.close()
    assert inserted == len(db.DEMO_PRODUCTS)


# ---------------------------------------------------------------------

def _first_row():
    """The single row in the table - used where the auto-increment id is
    not predictable across runs."""
    import conftest
    connection = conftest.app_module.get_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute("SELECT id, name, price, description FROM products LIMIT 1")
    row = cursor.fetchone()
    cursor.close()
    connection.close()
    return row
