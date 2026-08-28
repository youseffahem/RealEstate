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

import os

import agent_queries
import agent_validation
from conftest import (
    count_agents,
    delete_agent_row,
    fetch_agent_row,
    fetch_property_row,
    insert_agent,
    insert_property,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _agent_payload(**overrides):
    payload = {
        "name": "Layla Mostafa",
        "email": "layla.mostafa.test@example.com",
        "phone": "010-5555-1234",
        "gender": "Female",
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
# Agents page - gender grouping (Male agents before Female agents, each
# in their own section; an empty gender group renders no section at all).
#
# The seeded catalog always has at least one Male and one Female agent
# (see real_estate_db.DEMO_AGENTS), so "empty group" and "order" scenarios
# below are exercised against agent_queries.group_agents_by_gender()
# directly - a pure, DB-free function - rather than by deleting seeded
# agents out from under the rest of the suite.
# =====================================================================

def test_group_agents_by_gender_splits_male_and_female():
    agents = [
        {"id": 1, "name": "A", "gender": "Male"},
        {"id": 2, "name": "B", "gender": "Female"},
        {"id": 3, "name": "C", "gender": "Male"},
    ]
    male_agents, female_agents = agent_queries.group_agents_by_gender(agents)
    assert [a["id"] for a in male_agents] == [1, 3]
    assert [a["id"] for a in female_agents] == [2]


def test_group_agents_by_gender_preserves_relative_order():
    agents = [
        {"id": 1, "name": "Zed", "gender": "Male"},
        {"id": 2, "name": "Amy", "gender": "Male"},
    ]
    male_agents, _ = agent_queries.group_agents_by_gender(agents)
    assert [a["name"] for a in male_agents] == ["Zed", "Amy"]


def test_group_agents_by_gender_with_no_male_agents_is_an_empty_list():
    agents = [{"id": 1, "name": "Only Female", "gender": "Female"}]
    male_agents, female_agents = agent_queries.group_agents_by_gender(agents)
    assert male_agents == []
    assert len(female_agents) == 1


def test_group_agents_by_gender_with_no_female_agents_is_an_empty_list():
    agents = [{"id": 1, "name": "Only Male", "gender": "Male"}]
    male_agents, female_agents = agent_queries.group_agents_by_gender(agents)
    assert female_agents == []
    assert len(male_agents) == 1


def test_group_agents_by_gender_with_no_agents_returns_two_empty_lists():
    male_agents, female_agents = agent_queries.group_agents_by_gender([])
    assert male_agents == []
    assert female_agents == []


def test_agents_page_shows_no_visible_gender_section_headings(client, track_agents):
    # Both groups present (seeded catalog plus one fresh female agent), and
    # neither the word "Male Agents" nor "Female Agents" may appear
    # anywhere on the page - the grouping is internal-only now.
    female_id = insert_agent(name="No Heading Female Agent", email="no.heading.female@example.com",
                              gender="Female")
    track_agents.append(female_id)

    html = client.get("/agents").get_data(as_text=True)
    assert "Male Agents" not in html
    assert "Female Agents" not in html


def test_male_agents_appear_before_female_agents_on_agents_page(client, track_agents):
    # Unique, alphabetically-late names so they cannot collide with the
    # seeded catalog or be reordered by the (alphabetical) SQL ORDER BY.
    male_id = insert_agent(name="Zzyx Male Order Agent", email="zzyx.male.order@example.com",
                            gender="Male")
    track_agents.append(male_id)
    female_id = insert_agent(name="Aaaa Female Order Agent", email="aaaa.female.order@example.com",
                              gender="Female")
    track_agents.append(female_id)

    html = client.get("/agents").get_data(as_text=True)
    # Every male card must still come before every female card - as one
    # continuous, unlabeled grid - even though "Aaaa..." would sort before
    # "Zzyx..." alphabetically within a single ungrouped list.
    assert html.index("Zzyx Male Order Agent") < html.index("Aaaa Female Order Agent")


def test_agents_page_renders_no_grid_for_an_empty_gender_group():
    # The seeded catalog is never emptied out (see module docstring), so
    # this is asserted against the template logic directly: an empty list
    # for one gender must not render a second, empty .agent-grid container
    # (there is no heading left to hide - the grid itself is the thing
    # that must not appear).
    from flask import render_template

    from app import app as flask_app

    solo_male = {"id": 1, "name": "Solo Male", "gender": "Male", "email": "solo@example.com",
                 "phone": "010-0000-0000", "photo_url": None, "property_count": 0,
                 "available_count": 0, "sold_count": 0, "rented_count": 0}

    with flask_app.test_request_context():
        html = render_template(
            "agents/index.html",
            agents=[solo_male],
            male_agents=[solo_male],
            female_agents=[],
            stats={"total_agents": 1, "agents_with_properties": 0, "unassigned_properties": 0},
            filters={},
        )
    assert "Male Agents" not in html
    assert "Female Agents" not in html
    assert "Solo Male" in html
    assert html.count('class="property-grid agent-grid"') == 1


# =====================================================================
# Agents page - centered incomplete rows / max 4 per row (CSS)
#
# There is no headless browser in this suite, so the layout contract is
# verified at its source: the stylesheet rule that lays out .agent-grid.
# Flexbox + `justify-content: center` is what makes an incomplete row
# (1, 2 or 3 cards) center itself instead of sticking to the left, and
# `max-width: calc(25% - ...)` is what caps a row at 4 cards on desktop.
# =====================================================================

def _agent_grid_css_block():
    css_path = os.path.join(ROOT, "static", "style.css")
    with open(css_path, "r", encoding="utf-8") as handle:
        css = handle.read()
    start = css.index(".agent-grid {")
    # Grab a generous window after the first .agent-grid rule - enough to
    # include its own responsive breakpoints, without depending on exact
    # byte offsets for the end of that CSS section.
    return css[start:start + 1800]


def test_agent_grid_uses_flexbox_with_centered_wrapping():
    block = _agent_grid_css_block()
    assert "display: flex" in block
    assert "flex-wrap: wrap" in block
    assert "justify-content: center" in block


def test_agent_grid_caps_four_cards_per_row_on_desktop():
    block = _agent_grid_css_block()
    assert "calc(25% - 15px)" in block


def test_agent_grid_has_tablet_and_mobile_breakpoints():
    block = _agent_grid_css_block()
    assert "@media (max-width: 980px)" in block
    assert "calc(50% - 10px)" in block
    assert "@media (max-width: 640px)" in block


def test_agent_grid_connects_to_a_following_agent_grid_with_normal_row_spacing():
    # With the headings gone, Male -> Female must read as one continuous
    # grid: the second .agent-grid (Female) gets the same row-to-row
    # rhythm a wrapped row gets *inside* one group, not a bigger or a
    # smaller gap.
    block = _agent_grid_css_block()
    assert ".agent-grid + .agent-grid" in block
    assert "margin-top: 20px" in block


def test_property_grid_css_rule_is_unmodified_by_the_agent_grid_change():
    css_path = os.path.join(ROOT, "static", "style.css")
    with open(css_path, "r", encoding="utf-8") as handle:
        css = handle.read()
    # .property-grid itself - used by the untouched Properties/Inquiries
    # pages - must still be the original CSS Grid rule.
    start = css.index(".property-grid {")
    block = css[start:start + 200]
    assert "display: grid" in block
    assert "auto-fill" in block


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
# Agent gender - required field, validated server-side, stored in MySQL
# =====================================================================

def test_create_male_agent_succeeds_and_is_stored(client, track_agents):
    response, new_id = _create_ui(client, track_agents, name="Male Gender Agent",
                                   email="male.gender.agent@example.com", gender="Male")
    assert response.status_code in (302, 303)
    assert new_id is not None
    assert fetch_agent_row(new_id)["gender"] == "Male"


def test_create_female_agent_succeeds_and_is_stored(client, track_agents):
    response, new_id = _create_ui(client, track_agents, name="Female Gender Agent",
                                   email="female.gender.agent@example.com", gender="Female")
    assert response.status_code in (302, 303)
    assert new_id is not None
    assert fetch_agent_row(new_id)["gender"] == "Female"


def test_create_agent_missing_gender_is_rejected(client, track_agents):
    response, new_id = _create_ui(client, track_agents, gender="")
    assert response.status_code == 200
    assert new_id is None
    assert "gender is required" in response.get_data(as_text=True).lower()


def test_create_agent_with_invalid_gender_is_rejected(client, track_agents):
    response, new_id = _create_ui(client, track_agents, gender="Other")
    assert response.status_code == 200
    assert new_id is None
    assert "gender must be one of" in response.get_data(as_text=True).lower()
    # Nothing was ever written for an invalid gender - the database still
    # only ever has agents with a valid gender.
    assert new_id is None


def test_create_agent_with_sql_injection_in_gender_is_rejected(client, track_agents):
    response, new_id = _create_ui(client, track_agents, gender="Male'; DROP TABLE agents; --")
    assert response.status_code == 200
    assert new_id is None
    assert count_agents() >= 4


def test_edit_agent_gender_can_be_changed(client, track_agents):
    agent_id = insert_agent(name="Gender Change Agent", email="gender.change.agent@example.com",
                             gender="Male")
    track_agents.append(agent_id)

    response = client.post("/agents/edit/" + str(agent_id), data=_agent_payload(
        name="Gender Change Agent", email="gender.change.agent@example.com", gender="Female",
    ))
    assert response.status_code in (302, 303)
    assert fetch_agent_row(agent_id)["gender"] == "Female"


def test_edit_agent_with_invalid_gender_is_rejected_and_keeps_old_value(client, track_agents):
    agent_id = insert_agent(name="Bad Gender Edit Agent", email="bad.gender.edit.agent@example.com",
                             gender="Male")
    track_agents.append(agent_id)

    response = client.post("/agents/edit/" + str(agent_id), data=_agent_payload(
        name="Bad Gender Edit Agent", email="bad.gender.edit.agent@example.com", gender="Unknown",
    ))
    assert response.status_code == 200
    assert "gender must be one of" in response.get_data(as_text=True).lower()
    assert fetch_agent_row(agent_id)["gender"] == "Male"


def test_agent_card_shows_gender(client, track_agents):
    agent_id = insert_agent(name="Card Gender Agent", email="card.gender.agent@example.com",
                             gender="Female")
    track_agents.append(agent_id)

    html = client.get("/agents").get_data(as_text=True)
    assert "Card Gender Agent" in html
    # The card's own badge row carries the gender pill.
    assert '<span class="badge-pill">Female</span>' in html


def test_agent_detail_shows_gender(client, track_agents):
    agent_id = insert_agent(name="Detail Gender Agent", email="detail.gender.agent@example.com",
                             gender="Male")
    track_agents.append(agent_id)

    html = client.get("/agents/" + str(agent_id)).get_data(as_text=True)
    assert "Gender" in html
    assert "Male" in html


def test_validate_agent_payload_rejects_missing_gender():
    errors, cleaned = agent_validation.validate_agent_payload(
        {"name": "No Gender", "email": "no.gender@example.com", "phone": "010-1111-2222", "gender": ""},
        existing_emails=set(),
    )
    assert any("gender" in error.lower() for error in errors)
    assert cleaned is None


def test_validate_agent_payload_rejects_invalid_gender():
    errors, cleaned = agent_validation.validate_agent_payload(
        {"name": "Bad Gender", "email": "bad.gender@example.com", "phone": "010-1111-2222",
         "gender": "Non-binary"},
        existing_emails=set(),
    )
    assert any("gender" in error.lower() for error in errors)
    assert cleaned is None


def test_validate_agent_payload_accepts_male_and_female():
    for gender in agent_validation.GENDERS:
        errors, cleaned = agent_validation.validate_agent_payload(
            {"name": "Valid Gender", "email": "valid.gender.%s@example.com" % gender.lower(),
             "phone": "010-1111-2222", "gender": gender},
            existing_emails=set(),
        )
        assert errors == []
        assert cleaned["gender"] == gender


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
        {"name": "Valid Agent", "email": "valid.agent@example.com", "phone": "010-1111-2222",
         "gender": "Male"},
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
        {"name": "", "email": "", "phone": "", "gender": ""}, existing_emails=set(),
    )
    assert len(errors) == 4
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
