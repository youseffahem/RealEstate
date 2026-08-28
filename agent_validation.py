"""Server-side validation for the Real Estate `agents` form.

Every function here is plain Python with no database access, so it can be
unit-tested without MySQL. The caller (a Flask route in app.py) fetches the
emails currently in use with agent_queries.get_all_agent_emails() and
passes them in, so an agent can never be saved with an email that already
belongs to another agent - the same pattern property_validation.py already
uses for foreign keys (valid_ids is fetched by the caller and passed in).
"""

import re

NAME_MAX_LENGTH = 120    # matches agents.name VARCHAR(120)
EMAIL_MAX_LENGTH = 160   # matches agents.email VARCHAR(160)
PHONE_MAX_LENGTH = 30    # matches agents.phone VARCHAR(30)
PHONE_MIN_LENGTH = 6     # a reasonable floor - rejects "1", "abc", etc.

# A plain, reasonable email shape check (not a full RFC 5322 parser) -
# matches what the create/edit form's own type="email" input expects.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_agent_payload(form, existing_emails):
    """Validate an agent submission.

    `form` is anything with .get(name) - typically request.form.
    `existing_emails` is a set of lower-cased emails already used by OTHER
    agents (the caller excludes the agent's own current email on an edit,
    via agent_queries.get_all_agent_emails(connection, exclude_id=...)).

    Returns (errors, cleaned): `errors` is a list of human-readable
    messages (empty when the payload is valid); `cleaned` is the
    ready-to-store dict when there are no errors, otherwise None.
    """
    errors = []
    cleaned = {}

    # ----- name: required, trimmed, reasonable maximum length -----
    name = (form.get("name") or "").strip()
    if not name:
        errors.append("Name is required.")
    elif len(name) > NAME_MAX_LENGTH:
        errors.append("Name must be " + str(NAME_MAX_LENGTH) + " characters or fewer.")
    cleaned["name"] = name

    # ----- email: required, valid shape, unique across every agent -----
    email = (form.get("email") or "").strip()
    if not email:
        errors.append("Email is required.")
    elif len(email) > EMAIL_MAX_LENGTH:
        errors.append("Email must be " + str(EMAIL_MAX_LENGTH) + " characters or fewer.")
    elif not _EMAIL_RE.match(email):
        errors.append("Enter a valid email address.")
    elif email.lower() in existing_emails:
        errors.append("That email is already used by another agent.")
    cleaned["email"] = email

    # ----- phone: required, reasonable length -----
    phone = (form.get("phone") or "").strip()
    if not phone:
        errors.append("Phone is required.")
    elif len(phone) > PHONE_MAX_LENGTH:
        errors.append("Phone must be " + str(PHONE_MAX_LENGTH) + " characters or fewer.")
    elif len(phone) < PHONE_MIN_LENGTH:
        errors.append("Phone number is too short.")
    cleaned["phone"] = phone

    if errors:
        return errors, None
    return [], cleaned
