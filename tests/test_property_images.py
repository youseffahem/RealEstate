"""Phase 4 backend tests for the property gallery / image URLs.

These exercise the create/edit property pages (which own the image URL
manager) and the property detail/management pages (which display the
gallery), end to end through the Flask test client - plus the pure
validation function directly. The Phase 2/3 tests in test_properties.py
are untouched and still pass independently.

Every test that creates a property registers its id with `track_properties`
so the seeded catalog and its counts are restored afterwards.

Run with:  python -m pytest -v
"""

from werkzeug.datastructures import MultiDict

import property_validation
from conftest import (
    fetch_property_images,
    insert_property,
    insert_property_image,
)


def _create_ui(client, track_properties, property_ids, image_urls=None, **overrides):
    """POST a valid property payload through the Create Property UI page
    and return the response. `image_urls` becomes the repeated
    image_urls form field, exactly like the multi-row form does."""
    payload = {
        "title": "Gallery Test Property",
        "description": "Created through the properties UI.",
        "property_type_id": str(property_ids["property_type_id"]),
        "location_id": str(property_ids["location_id"]),
        "agent_id": "",
        "listing_type": "For Sale",
        "price": "750000.00",
        "area_sqm": "120.00",
        "bedrooms": "3",
        "bathrooms": "2",
        "status": "Available",
    }
    payload.update(overrides)
    data = MultiDict(payload)
    for url in (image_urls or []):
        data.add("image_urls", url)

    response = client.post("/properties/new", data=data)
    if response.status_code in (302, 303):
        new_id = int(response.headers["Location"].rstrip("/").rsplit("/", 1)[-1])
        track_properties.append(new_id)
        return response, new_id
    return response, None


# =====================================================================
# 1./2./3. Gallery display: none / one / multiple images
# =====================================================================

def test_property_without_images_shows_empty_state(client, track_properties, property_ids):
    property_id = insert_property(title="No Images Property")
    track_properties.append(property_id)

    response = client.get("/properties/view/" + str(property_id))
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "No property images available" in html


def test_property_with_one_image_renders_it(client, track_properties, property_ids):
    property_id = insert_property(title="One Image Property")
    track_properties.append(property_id)
    insert_property_image(property_id, "https://example.com/solo.jpg", 0)

    response = client.get("/properties/view/" + str(property_id))
    html = response.get_data(as_text=True)
    assert "https://example.com/solo.jpg" in html
    assert "No property images available" not in html


def test_property_with_multiple_images_renders_all_thumbnails(client, track_properties, property_ids):
    property_id = insert_property(title="Multi Image Property")
    track_properties.append(property_id)
    insert_property_image(property_id, "https://example.com/a.jpg", 0)
    insert_property_image(property_id, "https://example.com/b.jpg", 1)
    insert_property_image(property_id, "https://example.com/c.jpg", 2)

    html = client.get("/properties/view/" + str(property_id)).get_data(as_text=True)
    assert "https://example.com/a.jpg" in html
    assert "https://example.com/b.jpg" in html
    assert "https://example.com/c.jpg" in html


def test_property_images_seeded_with_no_url_are_not_rendered(client, track_properties, property_ids):
    # Mirrors the placeholder rows real_estate_db.py seeds for demo
    # properties (image_url NULL) - they must never show up as a "photo".
    property_id = insert_property(title="Placeholder Row Property")
    track_properties.append(property_id)
    insert_property_image(property_id, None, 0)

    html = client.get("/properties/view/" + str(property_id)).get_data(as_text=True)
    assert "No property images available" in html


# =====================================================================
# 6./7. Property card shows its primary image (Property Management grid)
# =====================================================================

def test_property_card_shows_primary_image_when_present(client, track_properties, property_ids):
    property_id = insert_property(title="Card Image Property")
    track_properties.append(property_id)
    insert_property_image(property_id, "https://example.com/card.jpg", 0)

    html = client.get("/properties/manage").get_data(as_text=True)
    assert "https://example.com/card.jpg" in html


def test_property_card_falls_back_cleanly_with_no_broken_image(client, track_properties, property_ids):
    property_id = insert_property(title="No Card Image Property")
    track_properties.append(property_id)

    html = client.get("/properties/manage").get_data(as_text=True)
    assert "property-card-media is-empty" in html


# =====================================================================
# 4./5. Add / remove image URLs through the create & edit pages
# =====================================================================

def test_create_property_with_image_urls_stores_them_in_order(client, track_properties, property_ids):
    response, new_id = _create_ui(
        client, track_properties, property_ids,
        image_urls=["https://example.com/first.jpg", "https://example.com/second.jpg"],
    )
    assert response.status_code in (302, 303)
    rows = fetch_property_images(new_id)
    assert [r["image_url"] for r in rows] == [
        "https://example.com/first.jpg", "https://example.com/second.jpg",
    ]
    assert [r["sort_order"] for r in rows] == [0, 1]


def test_create_property_with_no_image_urls_stores_none(client, track_properties, property_ids):
    response, new_id = _create_ui(client, track_properties, property_ids, image_urls=[])
    assert response.status_code in (302, 303)
    assert fetch_property_images(new_id) == []


def test_edit_page_prefills_existing_image_urls(client, track_properties, property_ids):
    property_id = insert_property(title="Prefill Images Property")
    track_properties.append(property_id)
    insert_property_image(property_id, "https://example.com/existing.jpg", 0)

    html = client.get("/properties/" + str(property_id) + "/edit").get_data(as_text=True)
    assert "https://example.com/existing.jpg" in html


def test_removing_an_image_url_on_edit_deletes_it(client, track_properties, property_ids):
    _, new_id = _create_ui(
        client, track_properties, property_ids,
        image_urls=["https://example.com/keep.jpg", "https://example.com/drop.jpg"],
    )

    edit_payload = {
        "title": "Gallery Test Property",
        "description": "Created through the properties UI.",
        "property_type_id": str(property_ids["property_type_id"]),
        "location_id": str(property_ids["location_id"]),
        "agent_id": "",
        "listing_type": "For Sale",
        "price": "750000.00",
        "area_sqm": "120.00",
        "bedrooms": "3",
        "bathrooms": "2",
        "status": "Available",
        "image_urls": "https://example.com/keep.jpg",  # only one now
    }
    response = client.post("/properties/" + str(new_id) + "/edit", data=edit_payload)
    assert response.status_code in (302, 303)

    rows = fetch_property_images(new_id)
    assert [r["image_url"] for r in rows] == ["https://example.com/keep.jpg"]


# =====================================================================
# 8./9./10. URL validation - reasonable http(s), reject other schemes
# =====================================================================

def test_validate_image_urls_accepts_plain_https():
    errors, cleaned = property_validation.validate_image_urls(["https://example.com/a.jpg"])
    assert errors == []
    assert cleaned == ["https://example.com/a.jpg"]


def test_validate_image_urls_drops_blank_rows():
    errors, cleaned = property_validation.validate_image_urls(["", "   ", "https://example.com/a.jpg"])
    assert errors == []
    assert cleaned == ["https://example.com/a.jpg"]


def test_validate_image_urls_rejects_javascript_scheme():
    errors, cleaned = property_validation.validate_image_urls(["javascript:alert(1)"])
    assert errors
    assert cleaned == []


def test_validate_image_urls_rejects_data_scheme():
    errors, cleaned = property_validation.validate_image_urls(["data:image/png;base64,aGVsbG8="])
    assert errors
    assert cleaned == []


def test_validate_image_urls_rejects_vbscript_scheme():
    errors, cleaned = property_validation.validate_image_urls(["vbscript:msgbox(1)"])
    assert errors
    assert cleaned == []


def test_validate_image_urls_rejects_url_without_domain():
    errors, cleaned = property_validation.validate_image_urls(["http://"])
    assert errors
    assert cleaned == []


def test_validate_image_urls_rejects_too_many_images():
    urls = ["https://example.com/" + str(i) + ".jpg" for i in range(20)]
    errors, cleaned = property_validation.validate_image_urls(urls)
    assert errors
    assert "12" in " ".join(errors)


def test_create_property_rejects_javascript_url_end_to_end(client, track_properties, property_ids):
    response, new_id = _create_ui(
        client, track_properties, property_ids, image_urls=["javascript:alert(1)"],
    )
    assert response.status_code == 200  # re-rendered form, not a redirect
    assert new_id is None
    html = response.get_data(as_text=True)
    assert "http://" in html.lower() or "must start with" in html.lower()


def test_create_property_rejects_data_url_end_to_end(client, track_properties, property_ids):
    response, new_id = _create_ui(
        client, track_properties, property_ids, image_urls=["data:text/html,<script>alert(1)</script>"],
    )
    assert response.status_code == 200
    assert new_id is None


# =====================================================================
# 11. Property deletion cascades to its images (UI delete route)
# =====================================================================

def test_deleting_a_property_via_the_ui_removes_its_images(client, property_ids):
    property_id = insert_property(title="Cascade UI Property")
    insert_property_image(property_id, "https://example.com/cascade.jpg", 0)

    response = client.post("/properties/" + str(property_id) + "/delete")
    assert response.status_code == 302

    assert fetch_property_images(property_id) == []


# =====================================================================
# 12./13./14./15. Existing pages still work
# =====================================================================

def test_dashboard_still_works(client):
    assert client.get("/dashboard").status_code == 200


def test_properties_manage_still_works(client):
    assert client.get("/properties/manage").status_code == 200


def test_search_still_works(client, track_properties, property_ids):
    property_id = insert_property(title="Searchable Gallery Villa")
    track_properties.append(property_id)
    html = client.get("/properties/manage?q=Searchable+Gallery+Villa").get_data(as_text=True)
    assert "Searchable Gallery Villa" in html


def test_status_filter_still_works(client, track_properties, property_ids):
    property_id = insert_property(title="Filter Gallery Villa", status="Sold", listing_type="For Sale")
    track_properties.append(property_id)
    html = client.get("/properties/manage?status=Sold").get_data(as_text=True)
    assert "Filter Gallery Villa" in html


# =====================================================================
# REAL ESTATE brand -> /dashboard navigation
# =====================================================================

def test_brand_links_to_dashboard(client):
    html = client.get("/").get_data(as_text=True)
    assert '<a href="/dashboard" class="user-row brand-aura"' in html
    assert "REAL ESTATE" in html
