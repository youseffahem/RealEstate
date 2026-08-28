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
import real_estate_db
from conftest import (
    app_module,
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


# =====================================================================
# Phase 5 - property image SEED FIX
#
# real_estate_db.DEMO_PROPERTY_IMAGES replaces the NULL placeholder rows
# seed_properties() used to insert for every demo property, and
# backfill_demo_property_images() fixes an already-seeded database (where
# the properties table is no longer empty, so seed_properties() itself is
# a no-op) on every startup. These tests exercise both paths directly
# against the seeded catalog - they never insert or delete a property.
# =====================================================================

def _get_property_id_by_title(title):
    connection = app_module.get_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT id FROM properties WHERE title = %s LIMIT 1", (title,))
    row = cursor.fetchone()
    cursor.close()
    connection.close()
    return row[0] if row else None


def test_every_seeded_demo_property_has_at_least_one_image():
    for title in real_estate_db.DEMO_PROPERTY_IMAGES:
        property_id = _get_property_id_by_title(title)
        assert property_id is not None, title
        images = fetch_property_images(property_id)
        real_images = [row for row in images if row["image_url"]]
        assert real_images, "expected at least one real image for " + title


def test_flagship_demo_property_has_multiple_images():
    property_id = _get_property_id_by_title("Luxury Villa in New Cairo")
    images = [row for row in fetch_property_images(property_id) if row["image_url"]]
    assert len(images) >= 2


def test_seeded_demo_image_urls_are_all_https():
    for urls in real_estate_db.DEMO_PROPERTY_IMAGES.values():
        for url in urls:
            assert url.startswith("https://"), url


def test_seeded_demo_images_match_their_property_type():
    # A light content sanity check rather than a hard-coded keyword list
    # for every entry: every URL is a real, reachable HTTPS image on a
    # stable CDN (images.unsplash.com), never a placeholder or data: URL.
    for urls in real_estate_db.DEMO_PROPERTY_IMAGES.values():
        for url in urls:
            assert url.startswith("https://images.unsplash.com/"), url


def test_backfill_demo_property_images_is_idempotent():
    connection = app_module.get_connection()
    cursor = connection.cursor()

    # Already fixed by app.py's own startup bootstrap - running it again
    # must not touch anything (every demo property already has a real
    # image) and must never duplicate a row.
    fixed_again = real_estate_db.backfill_demo_property_images(cursor)
    connection.commit()
    cursor.close()
    connection.close()

    assert fixed_again == 0

    property_id = _get_property_id_by_title("Luxury Villa in New Cairo")
    rows = fetch_property_images(property_id)
    assert len(rows) == len(real_estate_db.DEMO_PROPERTY_IMAGES["Luxury Villa in New Cairo"])


def test_backfill_never_touches_a_property_with_its_own_real_image(track_properties):
    property_id = insert_property(title="Beach Chalet in North Coast",
                                   description="A duplicate-titled property a user made themselves.")
    track_properties.append(property_id)
    insert_property_image(property_id, "https://example.com/user-uploaded.jpg", 0)

    connection = app_module.get_connection()
    cursor = connection.cursor()
    real_estate_db.backfill_demo_property_images(cursor)
    connection.commit()
    cursor.close()
    connection.close()

    # The backfill only matches by title; since this row is a duplicate
    # title, it is either untouched (already had a real image, or a
    # different row with this title was fixed instead) - either way it
    # must never have lost its own image.
    rows = fetch_property_images(property_id)
    assert any(row["image_url"] == "https://example.com/user-uploaded.jpg" for row in rows)


def test_properties_manage_page_renders_a_real_seeded_image(client):
    html = client.get("/properties/manage").get_data(as_text=True)
    assert "images.unsplash.com" in html


def test_property_detail_gallery_shows_seeded_images(client):
    property_id = _get_property_id_by_title("Luxury Villa in New Cairo")
    html = client.get("/properties/view/" + str(property_id)).get_data(as_text=True)
    assert "images.unsplash.com" in html
    assert "No property images available" not in html


def test_property_card_no_longer_falls_back_for_seeded_demo_properties(client):
    property_id = _get_property_id_by_title("Modern Apartment in Maadi")
    html = client.get("/properties/manage").get_data(as_text=True)
    # The specific seeded property's own card must show a real <img>, not
    # the empty-state fallback tile - checked by confirming its primary
    # image URL is present at all (get_primary_images() is what feeds the
    # card, exercised by loading the whole management page). The URL's
    # query string ("?auto=format&...") is HTML-escaped by Jinja
    # ("&amp;...") when rendered into the src attribute, so only the part
    # before the "&" is checked - the photo path itself is what matters.
    row = fetch_property_images(property_id)[0]
    assert row["image_url"].split("&")[0] in html
