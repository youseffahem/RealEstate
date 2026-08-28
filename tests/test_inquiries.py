"""Phase 6 tests for Inquiries / Leads Management.

These exercise the Inquiries HTML pages end to end through the Flask test
client (list/search/filters/stats, details, create, update, delete), the
pure validation functions directly, and the database-level guarantees:
deleting a property cascades to its inquiries (ON DELETE CASCADE), while
deleting an inquiry never touches its property, that property's agent, or
its images.

Every test that creates an inquiry or a property registers its id with
track_inquiries / track_properties so the seeded catalog and its counts
(test_real_estate_schema.py) are restored afterwards.

Run with:  python -m pytest -v
"""

import re

import app as app_module
import inquiry_queries
import inquiry_validation
from conftest import (
    count_inquiries,
    fetch_agent_row,
    fetch_inquiry_row,
    fetch_property_row,
    insert_agent,
    insert_inquiry,
    insert_property,
)


def _inquiry_payload(default_property_id, **overrides):
    payload = {
        "name": "Layla Kamal",
        "email": "layla.kamal.test@example.com",
        "phone": "010-7777-2222",
        "message": "Is this property still available for viewing this week?",
        "property_id": str(default_property_id),
    }
    payload.update(overrides)
    return payload


def _create_ui(client, track_inquiries, default_property_id, **overrides):
    """POST a valid inquiry payload through the Create Inquiry UI page and
    return (response, new_id) - new_id is None if the submission was
    rejected (re-rendered form, not a redirect). `overrides` can itself
    include `property_id` to submit an id different from
    `default_property_id` (e.g. to test an id that does not exist)."""
    payload = _inquiry_payload(default_property_id, **overrides)
    response = client.post("/inquiries/add", data=payload)
    if response.status_code in (302, 303):
        new_id = int(response.headers["Location"].rstrip("/").rsplit("/", 1)[-1])
        track_inquiries.append(new_id)
        return response, new_id
    return response, None


# =====================================================================
# Inquiry list
# =====================================================================

def test_inquiries_list_page_loads(client):
    response = client.get("/inquiries")
    assert response.status_code == 200
    assert "Inquiries" in response.get_data(as_text=True)


def test_inquiries_list_shows_a_seeded_inquiry(client):
    html = client.get("/inquiries").get_data(as_text=True)
    assert "Sara Ibrahim" in html


def test_inquiries_search_by_name_finds_a_match(client, track_inquiries, track_properties):
    property_id = insert_property(title="Searchable Inquiry Property")
    track_properties.append(property_id)
    inquiry_id = insert_inquiry(property_id, name="Findable Customer Name")
    track_inquiries.append(inquiry_id)

    html = client.get("/inquiries?q=Findable+Customer+Name").get_data(as_text=True)
    assert "Findable Customer Name" in html


def test_inquiries_search_by_email_finds_a_match(client, track_inquiries, track_properties):
    property_id = insert_property(title="Email Search Property")
    track_properties.append(property_id)
    inquiry_id = insert_inquiry(property_id, name="Email Match Customer", email="unique.search@example.com")
    track_inquiries.append(inquiry_id)

    html = client.get("/inquiries?q=unique.search").get_data(as_text=True)
    assert "Email Match Customer" in html


def test_inquiries_search_by_phone_finds_a_match(client, track_inquiries, track_properties):
    property_id = insert_property(title="Phone Search Property")
    track_properties.append(property_id)
    inquiry_id = insert_inquiry(property_id, name="Phone Match Customer", phone="019-6666-5555")
    track_inquiries.append(inquiry_id)

    html = client.get("/inquiries?q=019-6666-5555").get_data(as_text=True)
    assert "Phone Match Customer" in html


def test_inquiries_search_by_property_title_finds_a_match(client, track_inquiries, track_properties):
    property_id = insert_property(title="Very Unique Searchable Villa")
    track_properties.append(property_id)
    inquiry_id = insert_inquiry(property_id, name="Property Title Search Customer")
    track_inquiries.append(inquiry_id)

    html = client.get("/inquiries?q=Very+Unique+Searchable+Villa").get_data(as_text=True)
    assert "Property Title Search Customer" in html


def test_inquiries_search_by_message_finds_a_match(client, track_inquiries, track_properties):
    property_id = insert_property(title="Message Search Property")
    track_properties.append(property_id)
    inquiry_id = insert_inquiry(property_id, name="Message Match Customer",
                                 message="A very distinctive phrase xyzzyplugh appears here.")
    track_inquiries.append(inquiry_id)

    html = client.get("/inquiries?q=xyzzyplugh").get_data(as_text=True)
    assert "Message Match Customer" in html


def test_inquiries_search_with_no_match_shows_empty_state(client):
    html = client.get("/inquiries?q=NoSuchInquiryAnywhere123").get_data(as_text=True)
    assert "No matching inquiries found" in html


def test_inquiries_status_filter(client, track_inquiries, track_properties):
    property_id = insert_property(title="Status Filter Property")
    track_properties.append(property_id)
    inquiry_id = insert_inquiry(property_id, name="Contacted Filter Customer", status="Contacted")
    track_inquiries.append(inquiry_id)

    html = client.get("/inquiries?status=Contacted").get_data(as_text=True)
    assert "Contacted Filter Customer" in html

    html_new_only = client.get("/inquiries?status=New").get_data(as_text=True)
    # A Contacted-only customer must not appear under the New filter.
    assert "Contacted Filter Customer" not in html_new_only


def test_inquiries_property_filter(client, track_inquiries, track_properties):
    property_a = insert_property(title="Filter Property A")
    property_b = insert_property(title="Filter Property B")
    track_properties.append(property_a)
    track_properties.append(property_b)
    inquiry_a = insert_inquiry(property_a, name="Property A Customer")
    inquiry_b = insert_inquiry(property_b, name="Property B Customer")
    track_inquiries.append(inquiry_a)
    track_inquiries.append(inquiry_b)

    html = client.get("/inquiries?property_id=" + str(property_a)).get_data(as_text=True)
    assert "Property A Customer" in html
    assert "Property B Customer" not in html


def test_inquiries_agent_filter(client, track_inquiries, track_properties, track_agents):
    agent_id = insert_agent(name="Filter Test Agent", email="filter.test.agent@example.com")
    track_agents.append(agent_id)
    property_id = insert_property(title="Agent Filter Property", agent_id=agent_id)
    track_properties.append(property_id)
    inquiry_id = insert_inquiry(property_id, name="Agent Filtered Customer")
    track_inquiries.append(inquiry_id)

    html = client.get("/inquiries?agent_id=" + str(agent_id)).get_data(as_text=True)
    assert "Agent Filtered Customer" in html


# =====================================================================
# Statistics (real, database-computed)
# =====================================================================

def test_inquiries_statistics_are_present(client):
    html = client.get("/inquiries").get_data(as_text=True)
    assert "Total inquiries" in html
    assert ">New<" in html
    assert "Contacted" in html
    assert "Closed" in html


def test_inquiries_statistics_reflect_a_new_inquiry(client, track_inquiries, track_properties):
    property_id = insert_property(title="Stats Property")
    track_properties.append(property_id)

    before_total = _inquiry_stats(client)["total"]

    inquiry_id = insert_inquiry(property_id, name="Stats Counted Customer")
    track_inquiries.append(inquiry_id)

    after_total = _inquiry_stats(client)["total"]
    assert after_total == before_total + 1


# =====================================================================
# Inquiry details
# =====================================================================

def test_inquiry_detail_page_loads(client, track_inquiries, track_properties):
    property_id = insert_property(title="Detail View Property")
    track_properties.append(property_id)
    inquiry_id = insert_inquiry(property_id, name="Detail View Customer")
    track_inquiries.append(inquiry_id)

    response = client.get("/inquiries/" + str(inquiry_id))
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Detail View Customer" in html
    assert "Detail View Property" in html


def test_inquiry_detail_shows_assigned_agent(client, track_inquiries, track_properties, track_agents):
    agent_id = insert_agent(name="Detail Agent Name", email="detail.agent.name@example.com")
    track_agents.append(agent_id)
    property_id = insert_property(title="Agent Linked Property", agent_id=agent_id)
    track_properties.append(property_id)
    inquiry_id = insert_inquiry(property_id, name="Agent Linked Customer")
    track_inquiries.append(inquiry_id)

    html = client.get("/inquiries/" + str(inquiry_id)).get_data(as_text=True)
    assert "Detail Agent Name" in html


def test_inquiry_detail_shows_no_agent_assigned(client, track_inquiries, track_properties):
    property_id = insert_property(title="Unassigned Agent Property", agent_id=None)
    track_properties.append(property_id)
    inquiry_id = insert_inquiry(property_id, name="No Agent Customer")
    track_inquiries.append(inquiry_id)

    html = client.get("/inquiries/" + str(inquiry_id)).get_data(as_text=True)
    assert "No agent assigned" in html


def test_missing_inquiry_detail_redirects_with_flash(client):
    response = client.get("/inquiries/999999")
    assert response.status_code == 302
    followed = client.get("/inquiries/999999", follow_redirects=True)
    assert "does not exist" in followed.get_data(as_text=True)


def test_invalid_inquiry_id_is_not_found(client):
    # <int:id> refuses this at the routing level (same as /properties/<id>
    # and /agents/<id>) - the app's global 404 handler then flashes and
    # redirects for an HTML page instead of showing the raw Werkzeug page.
    response = client.get("/inquiries/not-a-number")
    assert response.status_code in (302, 404)


# =====================================================================
# Create Inquiry
# =====================================================================

def test_create_inquiry_succeeds_and_redirects(client, track_inquiries, track_properties):
    property_id = insert_property(title="Create Flow Property")
    track_properties.append(property_id)

    response, new_id = _create_ui(client, track_inquiries, property_id, name="Brand New Inquirer")
    assert response.status_code in (302, 303)
    assert new_id is not None
    row = fetch_inquiry_row(new_id)
    assert row["name"] == "Brand New Inquirer"
    assert row["property_id"] == property_id


def test_create_inquiry_defaults_to_new_status(client, track_inquiries, track_properties):
    property_id = insert_property(title="Default Status Property")
    track_properties.append(property_id)

    _, new_id = _create_ui(client, track_inquiries, property_id)
    assert fetch_inquiry_row(new_id)["status"] == "New"


def test_create_inquiry_missing_name_is_rejected(client, track_inquiries, track_properties):
    property_id = insert_property(title="Missing Name Property")
    track_properties.append(property_id)

    response, new_id = _create_ui(client, track_inquiries, property_id, name="")
    assert response.status_code == 200
    assert new_id is None
    assert "Name is required" in response.get_data(as_text=True)


def test_create_inquiry_missing_email_is_rejected(client, track_inquiries, track_properties):
    property_id = insert_property(title="Missing Email Property")
    track_properties.append(property_id)

    response, new_id = _create_ui(client, track_inquiries, property_id, email="")
    assert response.status_code == 200
    assert new_id is None
    assert "Email is required" in response.get_data(as_text=True)


def test_create_inquiry_invalid_email_is_rejected(client, track_inquiries, track_properties):
    property_id = insert_property(title="Invalid Email Property")
    track_properties.append(property_id)

    response, new_id = _create_ui(client, track_inquiries, property_id, email="not-an-email")
    assert response.status_code == 200
    assert new_id is None
    assert "valid email" in response.get_data(as_text=True).lower()


def test_create_inquiry_missing_phone_is_rejected(client, track_inquiries, track_properties):
    property_id = insert_property(title="Missing Phone Property")
    track_properties.append(property_id)

    response, new_id = _create_ui(client, track_inquiries, property_id, phone="")
    assert response.status_code == 200
    assert new_id is None
    assert "phone is required" in response.get_data(as_text=True).lower()


def test_create_inquiry_missing_message_is_rejected(client, track_inquiries, track_properties):
    property_id = insert_property(title="Missing Message Property")
    track_properties.append(property_id)

    response, new_id = _create_ui(client, track_inquiries, property_id, message="")
    assert response.status_code == 200
    assert new_id is None
    assert "message is required" in response.get_data(as_text=True).lower()


def test_create_inquiry_missing_property_is_rejected(client, track_inquiries):
    response, new_id = _create_ui(client, track_inquiries, "")
    assert response.status_code == 200
    assert new_id is None
    assert "property is required" in response.get_data(as_text=True).lower()


def test_create_inquiry_invalid_property_id_is_rejected(client, track_inquiries, track_properties):
    property_id = insert_property(title="Placeholder For Payload")
    track_properties.append(property_id)

    response, new_id = _create_ui(client, track_inquiries, property_id, property_id="999999")
    assert response.status_code == 200
    assert new_id is None
    assert "does not exist" in response.get_data(as_text=True).lower()


def test_create_inquiry_oversized_name_is_rejected(client, track_inquiries, track_properties):
    property_id = insert_property(title="Oversized Name Property")
    track_properties.append(property_id)

    response, new_id = _create_ui(client, track_inquiries, property_id, name="A" * 200)
    assert response.status_code == 200
    assert new_id is None


def test_create_inquiry_customer_cannot_set_status(client, track_inquiries, track_properties):
    """The Create form never renders a status field - but even a raw POST
    that forges one must still land as "New". The inquiries_add route
    forces this itself after validation, so a customer can never choose
    the status (Section 6) regardless of what a forged request sends."""
    property_id = insert_property(title="Forged Status Property")
    track_properties.append(property_id)

    payload = _inquiry_payload(property_id, status="Closed")
    response = client.post("/inquiries/add", data=payload)
    assert response.status_code in (302, 303)
    new_id = int(response.headers["Location"].rstrip("/").rsplit("/", 1)[-1])
    track_inquiries.append(new_id)
    assert fetch_inquiry_row(new_id)["status"] == "New"


def test_property_to_inquiry_flow_preselects_the_property(client, track_properties):
    property_id = insert_property(title="Preselect Flow Property")
    track_properties.append(property_id)

    html = client.get("/inquiries/add?property_id=" + str(property_id)).get_data(as_text=True)
    assert re.search(r'value="' + str(property_id) + r'"\s+selected', html) is not None


def test_property_detail_has_inquire_link_with_property_preselected(client, track_properties):
    property_id = insert_property(title="Inquire Link Property")
    track_properties.append(property_id)

    html = client.get("/properties/view/" + str(property_id)).get_data(as_text=True)
    assert "/inquiries/add?property_id=" + str(property_id) in html
    assert "Inquire about this property" in html


def test_property_detail_shows_real_inquiry_count(client, track_inquiries, track_properties):
    property_id = insert_property(title="Inquiry Count Property")
    track_properties.append(property_id)

    html_before = client.get("/properties/view/" + str(property_id)).get_data(as_text=True)
    assert "0 inquiries" in html_before

    inquiry_id = insert_inquiry(property_id, name="Counted Inquiry Customer")
    track_inquiries.append(inquiry_id)

    html_after = client.get("/properties/view/" + str(property_id)).get_data(as_text=True)
    assert "1 inquiry" in html_after


# =====================================================================
# Update Inquiry + status workflow
# =====================================================================

def test_edit_page_prefills_existing_values(client, track_inquiries, track_properties):
    property_id = insert_property(title="Prefill Inquiry Property")
    track_properties.append(property_id)
    inquiry_id = insert_inquiry(property_id, name="Prefill Inquiry Customer", email="prefill.inquiry@example.com")
    track_inquiries.append(inquiry_id)

    html = client.get("/inquiries/edit/" + str(inquiry_id)).get_data(as_text=True)
    assert "Prefill Inquiry Customer" in html
    assert "prefill.inquiry@example.com" in html


def test_update_inquiry_succeeds(client, track_inquiries, track_properties):
    property_id = insert_property(title="Update Inquiry Property")
    track_properties.append(property_id)
    inquiry_id = insert_inquiry(property_id, name="Old Inquiry Name")
    track_inquiries.append(inquiry_id)

    response = client.post("/inquiries/edit/" + str(inquiry_id),
                            data=_inquiry_payload(property_id, name="New Inquiry Name"))
    assert response.status_code in (302, 303)
    assert fetch_inquiry_row(inquiry_id)["name"] == "New Inquiry Name"


def test_update_inquiry_status_new_to_contacted(client, track_inquiries, track_properties):
    property_id = insert_property(title="Transition Property 1")
    track_properties.append(property_id)
    inquiry_id = insert_inquiry(property_id, status="New")
    track_inquiries.append(inquiry_id)

    response = client.post("/inquiries/edit/" + str(inquiry_id),
                            data=_inquiry_payload(property_id, status="Contacted"))
    assert response.status_code in (302, 303)
    assert fetch_inquiry_row(inquiry_id)["status"] == "Contacted"


def test_update_inquiry_status_contacted_to_closed(client, track_inquiries, track_properties):
    property_id = insert_property(title="Transition Property 2")
    track_properties.append(property_id)
    inquiry_id = insert_inquiry(property_id, status="Contacted")
    track_inquiries.append(inquiry_id)

    response = client.post("/inquiries/edit/" + str(inquiry_id),
                            data=_inquiry_payload(property_id, status="Closed"))
    assert response.status_code in (302, 303)
    assert fetch_inquiry_row(inquiry_id)["status"] == "Closed"


def test_update_inquiry_status_cannot_move_backward(client, track_inquiries, track_properties):
    property_id = insert_property(title="Backward Transition Property")
    track_properties.append(property_id)
    inquiry_id = insert_inquiry(property_id, status="Closed")
    track_inquiries.append(inquiry_id)

    response = client.post("/inquiries/edit/" + str(inquiry_id),
                            data=_inquiry_payload(property_id, status="New"))
    assert response.status_code == 200
    assert "cannot move backward" in response.get_data(as_text=True).lower()
    assert fetch_inquiry_row(inquiry_id)["status"] == "Closed"


def test_update_inquiry_invalid_status_is_rejected(client, track_inquiries, track_properties):
    property_id = insert_property(title="Invalid Status Property")
    track_properties.append(property_id)
    inquiry_id = insert_inquiry(property_id, status="New")
    track_inquiries.append(inquiry_id)

    response = client.post("/inquiries/edit/" + str(inquiry_id),
                            data=_inquiry_payload(property_id, status="Cancelled"))
    assert response.status_code == 200
    assert "status must be one of" in response.get_data(as_text=True).lower()
    assert fetch_inquiry_row(inquiry_id)["status"] == "New"


def test_update_missing_inquiry_redirects(client, track_properties):
    property_id = insert_property(title="Missing Inquiry Edit Property")
    track_properties.append(property_id)
    response = client.post("/inquiries/edit/999999", data=_inquiry_payload(property_id))
    assert response.status_code == 302


def test_inquiries_statistics_reflect_status_change(client, track_inquiries, track_properties):
    property_id = insert_property(title="Stats Transition Property")
    track_properties.append(property_id)
    inquiry_id = insert_inquiry(property_id, status="New")
    track_inquiries.append(inquiry_id)

    connection_stats_before = _inquiry_stats(client)
    client.post("/inquiries/edit/" + str(inquiry_id),
                data=_inquiry_payload(property_id, status="Contacted"))
    connection_stats_after = _inquiry_stats(client)

    assert connection_stats_after["new"] == connection_stats_before["new"] - 1
    assert connection_stats_after["contacted"] == connection_stats_before["contacted"] + 1


def _inquiry_stats(client):
    connection = app_module.get_connection()
    stats = inquiry_queries.get_inquiry_stats(connection)
    connection.close()
    return stats


# =====================================================================
# Delete Inquiry
# =====================================================================

def test_delete_inquiry_succeeds(client, track_properties):
    property_id = insert_property(title="Delete Inquiry Property")
    track_properties.append(property_id)
    inquiry_id = insert_inquiry(property_id, name="Deletable Inquiry")

    response = client.post("/inquiries/delete/" + str(inquiry_id))
    assert response.status_code == 302
    assert fetch_inquiry_row(inquiry_id) is None


def test_delete_missing_inquiry_is_handled_gracefully(client):
    response = client.post("/inquiries/delete/999999")
    assert response.status_code == 302
    followed = client.get("/inquiries", follow_redirects=True)
    assert followed.status_code == 200


def test_deleting_an_inquiry_does_not_delete_its_property(client, track_properties):
    property_id = insert_property(title="Survives Inquiry Deletion")
    track_properties.append(property_id)
    inquiry_id = insert_inquiry(property_id, name="Deleted Inquiry Only")

    client.post("/inquiries/delete/" + str(inquiry_id))

    row = fetch_property_row(property_id)
    assert row is not None, "the property must still exist after its inquiry is deleted"
    assert row["title"] == "Survives Inquiry Deletion"


def test_deleting_an_inquiry_does_not_delete_the_agent(client, track_properties, track_agents):
    agent_id = insert_agent(name="Survives Inquiry Deletion Agent", email="survives.inquiry.agent@example.com")
    track_agents.append(agent_id)
    property_id = insert_property(title="Agent Kept Property", agent_id=agent_id)
    track_properties.append(property_id)
    inquiry_id = insert_inquiry(property_id, name="Agent Preserving Inquiry")

    client.post("/inquiries/delete/" + str(inquiry_id))

    assert fetch_agent_row(agent_id) is not None


def test_get_on_inquiries_delete_route_is_rejected(client, track_properties):
    property_id = insert_property(title="Get Delete Rejected Property")
    track_properties.append(property_id)
    inquiry_id = insert_inquiry(property_id)

    response = client.get("/inquiries/delete/" + str(inquiry_id))
    assert response.status_code == 405
    assert fetch_inquiry_row(inquiry_id) is not None


# =====================================================================
# Property deletion -> inquiry cascade (Section 13 regression)
# =====================================================================

def test_deleting_a_property_cascades_to_its_inquiries(client):
    property_id = insert_property(title="Cascade Source Property")
    inquiry_id = insert_inquiry(property_id, name="Cascaded Away Customer")

    client.post("/properties/" + str(property_id) + "/delete")

    assert fetch_property_row(property_id) is None
    assert fetch_inquiry_row(inquiry_id) is None


# =====================================================================
# Agent -> inquiry flow (Section 8/22)
# =====================================================================

def test_agent_detail_shows_recent_inquiries(client, track_inquiries, track_properties, track_agents):
    agent_id = insert_agent(name="Recent Inquiries Agent", email="recent.inquiries.agent@example.com")
    track_agents.append(agent_id)
    property_id = insert_property(title="Recent Inquiries Property", agent_id=agent_id)
    track_properties.append(property_id)
    inquiry_id = insert_inquiry(property_id, name="Recent Inquiry Customer")
    track_inquiries.append(inquiry_id)

    html = client.get("/agents/" + str(agent_id)).get_data(as_text=True)
    assert "Recent inquiries" in html
    assert "Recent Inquiry Customer" in html


def test_agent_detail_shows_empty_state_with_no_inquiries(client, track_agents):
    agent_id = insert_agent(name="No Inquiries Agent", email="no.inquiries.agent@example.com")
    track_agents.append(agent_id)

    html = client.get("/agents/" + str(agent_id)).get_data(as_text=True)
    assert "No inquiries yet for this agent's properties" in html


# =====================================================================
# Security: SQL injection / XSS
# =====================================================================

def test_inquiries_search_with_sql_injection_does_not_error(client):
    response = client.get("/inquiries", query_string={"q": "'; DROP TABLE inquiries; --"})
    assert response.status_code == 200
    # The inquiries table must still be usable afterwards.
    assert count_inquiries() >= 0


def test_create_inquiry_with_sql_injection_in_name_is_stored_safely(client, track_inquiries, track_properties):
    property_id = insert_property(title="SQL Injection Inquiry Property")
    track_properties.append(property_id)

    payload_name = "Robert'); DROP TABLE inquiries; --"
    response, new_id = _create_ui(client, track_inquiries, property_id, name=payload_name)
    assert response.status_code in (302, 303)
    assert fetch_inquiry_row(new_id)["name"] == payload_name


def test_create_inquiry_with_xss_in_message_is_not_executed(client, track_inquiries, track_properties):
    property_id = insert_property(title="XSS Inquiry Property")
    track_properties.append(property_id)

    payload_message = "<script>alert('xss')</script>"
    response, new_id = _create_ui(client, track_inquiries, property_id, message=payload_message)
    assert response.status_code in (302, 303)

    html = client.get("/inquiries/" + str(new_id)).get_data(as_text=True)
    assert "<script>alert('xss')</script>" not in html
    assert "&lt;script&gt;" in html


def test_inquiries_search_with_xss_payload_is_escaped(client):
    html = client.get("/inquiries", query_string={"q": "<script>alert(1)</script>"}).get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html


def test_create_inquiry_with_dangerous_scheme_in_message_is_rejected(client, track_inquiries, track_properties):
    property_id = insert_property(title="Dangerous Scheme Property")
    track_properties.append(property_id)

    response, new_id = _create_ui(client, track_inquiries, property_id,
                                   message="javascript:alert(document.cookie)")
    assert response.status_code == 200
    assert new_id is None


def test_invalid_property_id_via_sql_injection_is_rejected_by_the_route(client):
    # <int:id> refuses this outright at the routing level - it never
    # reaches SQL, the same guarantee test_properties.py asserts for
    # /properties/delete/<id>.
    response = client.post("/inquiries/delete/1%20OR%201=1")
    assert response.status_code in (302, 404, 405)


# =====================================================================
# Pure validation functions
# =====================================================================

def test_validate_inquiry_payload_accepts_a_valid_submission():
    errors, cleaned = inquiry_validation.validate_inquiry_payload(
        {"name": "Valid Customer", "email": "valid.customer@example.com", "phone": "010-1111-2222",
         "message": "A perfectly reasonable message.", "property_id": "1"},
        valid_property_ids={1, 2, 3},
    )
    assert errors == []
    assert cleaned["status"] == "New"


def test_validate_inquiry_payload_rejects_unknown_property_id():
    errors, cleaned = inquiry_validation.validate_inquiry_payload(
        {"name": "Test", "email": "test@example.com", "phone": "010-1111-2222",
         "message": "Message", "property_id": "999"},
        valid_property_ids={1, 2, 3},
    )
    assert errors
    assert cleaned is None


def test_validate_inquiry_payload_rejects_missing_fields():
    errors, cleaned = inquiry_validation.validate_inquiry_payload(
        {"name": "", "email": "", "phone": "", "message": "", "property_id": ""},
        valid_property_ids=set(),
    )
    assert len(errors) == 5
    assert cleaned is None


def test_validate_status_transition_allows_forward_moves():
    assert inquiry_validation.validate_status_transition("New", "Contacted") is None
    assert inquiry_validation.validate_status_transition("New", "Closed") is None
    assert inquiry_validation.validate_status_transition("Contacted", "Closed") is None
    assert inquiry_validation.validate_status_transition("New", "New") is None


def test_validate_status_transition_rejects_backward_moves():
    assert inquiry_validation.validate_status_transition("Closed", "New") is not None
    assert inquiry_validation.validate_status_transition("Contacted", "New") is not None


def test_validate_status_transition_rejects_unknown_status():
    assert inquiry_validation.validate_status_transition("New", "Cancelled") is not None


# =====================================================================
# Existing pages still work alongside Inquiries
# =====================================================================

def test_dashboard_still_works(client):
    assert client.get("/dashboard").status_code == 200


def test_properties_manage_still_works(client):
    assert client.get("/properties/manage").status_code == 200


def test_agents_list_still_works(client):
    assert client.get("/agents").status_code == 200


def test_inquiries_nav_link_present_on_dashboard(client):
    html = client.get("/dashboard").get_data(as_text=True)
    assert 'href="/inquiries"' in html
    assert ">Inquiries<" in html


def test_real_estate_brand_still_links_to_dashboard(client):
    html = client.get("/inquiries").get_data(as_text=True)
    assert 'href="/dashboard"' in html
    assert "REAL ESTATE" in html
