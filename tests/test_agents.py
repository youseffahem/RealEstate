"""Phase 5 tests for Agents Management.

These exercise the Agents HTML pages end to end through the Flask test
client (list/search/stats, details, create, update, delete), the pure
validation function directly, and the database-level guarantee that
deleting an agent never deletes a property (properties.agent_id is
ON DELETE SET NULL - see real_estate_db.py).

Every test that creates an agent or a property registers its id with
track_agents / track_properties so the seeded catalog and its counts
(test_real_estate_schema.py) are restored afterwards.

Run with:  python -m pytest -v
"""

import agent_validation
from conftest import (
    count_agents,
    delete_agent_row,
    fetch_agent_row,
    fetch_property_row,
    insert_agent,
    insert_property,
)


def _agent_payload(**overrides):
    payload = {
        "name": "Layla Mostafa",
        "email": "layla.mostafa.test@example.com",
        "phone": "010-5555-1234",
    }
    payload.update(overrides)
    return payload


def _create_ui(client, track_agents, **overrides):
    """POST a valid agent payload through the Create Agent UI page and
    return (response, new_id) - new_id is None if the submission was
    rejected (re-rendered form, not a redirect)."""
    payload = _agent_payload(**overrides)
    response = client.post("/agents/add", data=payload)
    if response.status_code in (302, 303):
        new_id = int(response.headers["Location"].rstrip("/").rsplit("/", 1)[-1])
        track_agents.append(new_id)
        return response, new_id
    return response, None


# =====================================================================
# Agent list
# =====================================================================

def test_agents_list_page_loads(client):
    response = client.get("/agents")
    assert response.status_code == 200
    assert "Agent Management" in response.get_data(as_text=True)


def test_agents_list_shows_a_seeded_agent(client):
    html = client.get("/agents").get_data(as_text=True)
    assert "@tantawyrealestate.com" in html


def test_agents_search_by_name_finds_a_match(client, track_agents):
    agent_id = insert_agent(name="Searchable Agent Name", email="searchable.agent@example.com")
    track_agents.append(agent_id)

    html = client.get("/agents?q=Searchable+Agent+Name").get_data(as_text=True)
    assert "Searchable Agent Name" in html


def test_agents_search_by_email_finds_a_match(client, track_agents):
    agent_id = insert_agent(name="Email Search Agent", email="unique.email.search@example.com")
    track_agents.append(agent_id)

    html = client.get("/agents?q=unique.email.search").get_data(as_text=True)
    assert "Email Search Agent" in html


def test_agents_search_by_phone_finds_a_match(client, track_agents):
    agent_id = insert_agent(name="Phone Search Agent", email="phone.search.agent@example.com",
                             phone="019-8888-7777")
    track_agents.append(agent_id)

    html = client.get("/agents?q=019-8888-7777").get_data(as_text=True)
    assert "Phone Search Agent" in html


def test_agents_search_with_no_match_shows_empty_state(client):
    html = client.get("/agents?q=NoSuchAgentAnywhere123").get_data(as_text=True)
    assert "No matching agents found" in html


# =====================================================================
# Agent property statistics (Section 7 - real aggregate queries)
# =====================================================================

def test_agents_overview_stats_are_present(client):
    html = client.get("/agents").get_data(as_text=True)
    assert "Total agents" in html
    assert "Agents with properties" in html
    assert "Unassigned properties" in html


def test_agent_card_shows_property_counts(client, track_agents, track_properties, property_ids):
    agent_id = insert_agent(name="Counted Agent", email="counted.agent@example.com")
    track_agents.append(agent_id)
    property_id = insert_property(title="Counted Agent Property", agent_id=agent_id, status="Available")
    track_properties.append(property_id)

    html = client.get("/agents").get_data(as_text=True)
    assert "Counted Agent" in html
    assert "1 Assigned" in html


# =====================================================================
# Agent details
# =====================================================================

def test_agent_detail_page_loads(client, track_agents):
    agent_id = insert_agent(name="Detail View Agent", email="detail.view.agent@example.com")
    track_agents.append(agent_id)

    response = client.get("/agents/" + str(agent_id))
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Detail View Agent" in html


def test_agent_detail_shows_created_date_and_total(client, track_agents):
    agent_id = insert_agent(name="Total Field Agent", email="total.field.agent@example.com")
    track_agents.append(agent_id)

    html = client.get("/agents/" + str(agent_id)).get_data(as_text=True)
    assert "Created" in html
    assert "Total assigned properties" in html


def test_missing_agent_detail_redirects_with_flash(client):
    response = client.get("/agents/999999")
    assert response.status_code == 302
    followed = client.get("/agents/999999", follow_redirects=True)
    assert "does not exist" in followed.get_data(as_text=True)


# =====================================================================
# Assigned properties on the detail page
# =====================================================================

def test_agent_detail_lists_assigned_properties(client, track_agents, track_properties, property_ids):
    agent_id = insert_agent(name="Assigned Properties Agent", email="assigned.props.agent@example.com")
    track_agents.append(agent_id)
    property_id = insert_property(title="Assigned To This Agent", agent_id=agent_id)
    track_properties.append(property_id)

    html = client.get("/agents/" + str(agent_id)).get_data(as_text=True)
    assert "Assigned To This Agent" in html


def test_agent_detail_shows_empty_state_with_no_properties(client, track_agents):
    agent_id = insert_agent(name="No Properties Agent", email="no.properties.agent@example.com")
    track_agents.append(agent_id)

    html = client.get("/agents/" + str(agent_id)).get_data(as_text=True)
    assert "No properties are currently assigned to this agent" in html


# =====================================================================
# Create Agent
# =====================================================================

def test_create_agent_succeeds_and_redirects(client, track_agents):
    response, new_id = _create_ui(client, track_agents, name="Brand New Agent",
                                   email="brand.new.agent@example.com")
    assert response.status_code in (302, 303)
    assert new_id is not None
    row = fetch_agent_row(new_id)
    assert row["name"] == "Brand New Agent"
    assert row["email"] == "brand.new.agent@example.com"


def test_create_agent_missing_name_is_rejected(client, track_agents):
    response, new_id = _create_ui(client, track_agents, name="")
    assert response.status_code == 200
    assert new_id is None
    assert "Name is required" in response.get_data(as_text=True)


def test_create_agent_missing_email_is_rejected(client, track_agents):
    response, new_id = _create_ui(client, track_agents, email="")
    assert response.status_code == 200
    assert new_id is None
    assert "Email is required" in response.get_data(as_text=True)


def test_create_agent_invalid_email_is_rejected(client, track_agents):
    response, new_id = _create_ui(client, track_agents, email="not-an-email")
    assert response.status_code == 200
    assert new_id is None
    assert "valid email" in response.get_data(as_text=True).lower()


def test_create_agent_duplicate_email_is_rejected(client, track_agents):
    existing_id = insert_agent(name="Existing Agent", email="already.used@example.com")
    track_agents.append(existing_id)

    response, new_id = _create_ui(client, track_agents, email="already.used@example.com")
    assert response.status_code == 200
    assert new_id is None
    assert "already used" in response.get_data(as_text=True).lower()


def test_create_agent_short_phone_is_rejected(client, track_agents):
    response, new_id = _create_ui(client, track_agents, phone="123")
    assert response.status_code == 200
    assert new_id is None
    assert "too short" in response.get_data(as_text=True).lower()


def test_create_agent_missing_phone_is_rejected(client, track_agents):
    response, new_id = _create_ui(client, track_agents, phone="")
    assert response.status_code == 200
    assert new_id is None
    assert "phone is required" in response.get_data(as_text=True).lower()


# =====================================================================
# Update Agent
# =====================================================================

def test_edit_page_prefills_existing_values(client, track_agents):
    agent_id = insert_agent(name="Prefill Agent", email="prefill.agent@example.com", phone="011-2222-3333")
    track_agents.append(agent_id)

    html = client.get("/agents/edit/" + str(agent_id)).get_data(as_text=True)
    assert "Prefill Agent" in html
    assert "prefill.agent@example.com" in html


def test_update_agent_succeeds(client, track_agents):
    agent_id = insert_agent(name="Old Name", email="update.agent@example.com")
    track_agents.append(agent_id)

    response = client.post("/agents/edit/" + str(agent_id), data=_agent_payload(
        name="New Name", email="update.agent@example.com", phone="012-3333-4444",
    ))
    assert response.status_code in (302, 303)
    row = fetch_agent_row(agent_id)
    assert row["name"] == "New Name"
    assert row["phone"] == "012-3333-4444"


def test_update_agent_keeping_own_email_is_allowed(client, track_agents):
    agent_id = insert_agent(name="Self Email Agent", email="self.email.agent@example.com")
    track_agents.append(agent_id)

    response = client.post("/agents/edit/" + str(agent_id), data=_agent_payload(
        name="Self Email Agent Updated", email="self.email.agent@example.com",
    ))
    assert response.status_code in (302, 303)
    assert fetch_agent_row(agent_id)["name"] == "Self Email Agent Updated"


def test_update_agent_to_another_agents_email_is_rejected(client, track_agents):
    other_id = insert_agent(name="Other Agent", email="other.taken@example.com")
    track_agents.append(other_id)
    agent_id = insert_agent(name="Editing Agent", email="editing.agent@example.com")
    track_agents.append(agent_id)

    response = client.post("/agents/edit/" + str(agent_id), data=_agent_payload(
        name="Editing Agent", email="other.taken@example.com",
    ))
    assert response.status_code == 200
    assert "already used" in response.get_data(as_text=True).lower()
    assert fetch_agent_row(agent_id)["email"] == "editing.agent@example.com"


def test_update_missing_agent_redirects(client):
    response = client.post("/agents/edit/999999", data=_agent_payload())
    assert response.status_code == 302


# =====================================================================
# Delete Agent + business rule: properties remain, agent_id -> NULL
# =====================================================================

def test_delete_agent_succeeds(client, track_agents):
    agent_id = insert_agent(name="Deletable Agent", email="deletable.agent@example.com")

    response = client.post("/agents/delete/" + str(agent_id))
    assert response.status_code == 302
    assert fetch_agent_row(agent_id) is None


def test_delete_missing_agent_is_handled_gracefully(client):
    response = client.post("/agents/delete/999999")
    assert response.status_code == 302
    followed = client.get("/agents", follow_redirects=True)
    assert followed.status_code == 200


def test_get_on_agents_delete_route_is_rejected(client, track_agents):
    agent_id = insert_agent(name="Get Delete Rejected Agent", email="get.delete.rejected@example.com")
    track_agents.append(agent_id)

    # Delete is POST only (Phase 8 QA fix): opening it via GET must answer
    # with a real HTTP 405, landing back on the Agents page - not the 302
    # to the unrelated dashboard it used to fall through to.
    response = client.get("/agents/delete/" + str(agent_id))
    assert response.status_code == 405
    assert fetch_agent_row(agent_id) is not None


def test_deleting_an_agent_does_not_delete_its_properties(client, track_properties):
    agent_id = insert_agent(name="Property Owner Agent", email="property.owner.agent@example.com")
    property_id = insert_property(title="Survives Agent Deletion", agent_id=agent_id)
    track_properties.append(property_id)

    client.post("/agents/delete/" + str(agent_id))

    row = fetch_property_row(property_id)
    assert row is not None, "the property must still exist after its agent is deleted"
    assert row["title"] == "Survives Agent Deletion"


def test_deleting_an_agent_sets_property_agent_id_to_null(client, track_properties):
    agent_id = insert_agent(name="Nulled Agent", email="nulled.agent@example.com")
    property_id = insert_property(title="Agent Id Goes Null", agent_id=agent_id)
    track_properties.append(property_id)

    client.post("/agents/delete/" + str(agent_id))

    assert fetch_property_row(property_id)["agent_id"] is None


def test_property_remains_functional_after_its_agent_is_deleted(client, track_properties):
    agent_id = insert_agent(name="Functional Test Agent", email="functional.test.agent@example.com")
    property_id = insert_property(title="Still Functional Property", agent_id=agent_id)
    track_properties.append(property_id)

    client.post("/agents/delete/" + str(agent_id))

    response = client.get("/properties/view/" + str(property_id))
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Still Functional Property" in html
    assert "No agent assigned" in html


# =====================================================================
# Security: SQL injection / XSS
# =====================================================================

def test_agent_search_with_sql_injection_does_not_error(client):
    response = client.get("/agents", query_string={"q": "'; DROP TABLE agents; --"})
    assert response.status_code == 200
    # The agents table must still be usable afterwards.
    assert count_agents() >= 4


def test_create_agent_with_sql_injection_in_name_is_stored_safely(client, track_agents):
    payload_name = "Robert'); DROP TABLE agents; --"
    response, new_id = _create_ui(client, track_agents, name=payload_name,
                                   email="sql.injection.agent@example.com")
    assert response.status_code in (302, 303)
    assert count_agents() >= 4
    assert fetch_agent_row(new_id)["name"] == payload_name


def test_create_agent_with_xss_in_name_is_not_executed(client, track_agents):
    payload_name = "<script>alert('xss')</script>"
    response, new_id = _create_ui(client, track_agents, name=payload_name,
                                   email="xss.agent@example.com")
    assert response.status_code in (302, 303)

    html = client.get("/agents/" + str(new_id)).get_data(as_text=True)
    assert "<script>alert('xss')</script>" not in html
    # Jinja auto-escaping must have turned it into inert markup.
    assert "&lt;script&gt;" in html


def test_agent_search_with_xss_payload_is_escaped(client):
    html = client.get("/agents", query_string={"q": "<script>alert(1)</script>"}).get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html


# =====================================================================
# Pure validation function
# =====================================================================

def test_validate_agent_payload_accepts_a_valid_submission():
    errors, cleaned = agent_validation.validate_agent_payload(
        {"name": "Valid Agent", "email": "valid.agent@example.com", "phone": "010-1111-2222"},
        existing_emails=set(),
    )
    assert errors == []
    assert cleaned["name"] == "Valid Agent"


def test_validate_agent_payload_rejects_duplicate_email_case_insensitively():
    errors, cleaned = agent_validation.validate_agent_payload(
        {"name": "Case Test", "email": "Case.Test@Example.com", "phone": "010-1111-2222"},
        existing_emails={"case.test@example.com"},
    )
    assert errors
    assert cleaned is None


def test_validate_agent_payload_rejects_missing_fields():
    errors, cleaned = agent_validation.validate_agent_payload(
        {"name": "", "email": "", "phone": ""}, existing_emails=set(),
    )
    assert len(errors) == 3
    assert cleaned is None


# =====================================================================
# Existing pages still work alongside Agents
# =====================================================================

def test_dashboard_still_works(client):
    assert client.get("/dashboard").status_code == 200


def test_properties_manage_still_works(client):
    assert client.get("/properties/manage").status_code == 200


def test_agents_nav_link_present_on_dashboard(client):
    html = client.get("/dashboard").get_data(as_text=True)
    assert 'href="/agents"' in html
    assert ">Agents<" in html
