"""Server-side validation for the Real Estate `inquiries` form, plus the
business rule that governs how an inquiry's status is allowed to move.

Every function here is plain Python with no database access, so it can be
unit-tested without MySQL. The caller (a Flask route in app.py) fetches the
property ids that currently exist with inquiry_queries.get_valid_property_ids()
and passes them in - the same pattern property_validation.py already uses
for its own foreign keys (valid_ids is fetched by the caller and passed in).
"""

import re

NAME_MAX_LENGTH = 120       # matches inquiries.name VARCHAR(120)
EMAIL_MAX_LENGTH = 160      # matches inquiries.email VARCHAR(160)
PHONE_MAX_LENGTH = 30       # matches inquiries.phone VARCHAR(30)
PHONE_MIN_LENGTH = 6        # a reasonable floor - rejects "1", "abc", etc.
MESSAGE_MAX_LENGTH = 2000   # reasonable cap; the column itself is TEXT

STATUSES = ("New", "Contacted", "Closed")

# Business rule (Section 11): an inquiry only ever moves forward through
# New -> Contacted -> Closed. This order is also what lets a transition be
# validated as "did the index go backward?" instead of a hand-written list
# of every allowed (from, to) pair.
_STATUS_ORDER = {status: index for index, status in enumerate(STATUSES)}

# A plain, reasonable email shape check (not a full RFC 5322 parser) -
# matches what the create/edit form's own type="email" input expects, and
# mirrors agent_validation.py's own check.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Section 15: reject javascript:/data:/vbscript: in free-text fields,
# wherever they appear in the string (not only as a URL prefix) - a
# customer's name or message is never rendered as a link, but this keeps
# the raw stored text itself free of an inert-looking attack payload.
_DANGEROUS_SCHEME_RE = re.compile(r"(javascript|data|vbscript)\s*:", re.IGNORECASE)


def _has_dangerous_scheme(text):
    return bool(_DANGEROUS_SCHEME_RE.search(text))


def validate_inquiry_payload(form, valid_property_ids):
    """Validate an inquiry submission (both the customer-facing Create form
    and the agent-facing Edit form share this).

    `form` is anything with .get(name) - typically request.form.
    `valid_property_ids` is a set of property ids that currently exist,
    from inquiry_queries.get_valid_property_ids().

    A customer never sends a `status` field (Section 6), so it defaults to
    "New" when absent - the caller never has to special-case create vs.
    edit here. Returns (errors, cleaned): `errors` is a list of
    human-readable messages (empty when the payload is valid); `cleaned`
    is the ready-to-store dict when there are no errors, otherwise None.
    """
    errors = []
    cleaned = {}

    # ----- name: required, trimmed, reasonable maximum length -----
    name = (form.get("name") or "").strip()
    if not name:
        errors.append("Name is required.")
    elif len(name) > NAME_MAX_LENGTH:
        errors.append("Name must be " + str(NAME_MAX_LENGTH) + " characters or fewer.")
    elif _has_dangerous_scheme(name):
        errors.append("Name contains content that is not allowed.")
    cleaned["name"] = name

    # ----- email: required, valid shape, reasonable maximum length -----
    email = (form.get("email") or "").strip()
    if not email:
        errors.append("Email is required.")
    elif len(email) > EMAIL_MAX_LENGTH:
        errors.append("Email must be " + str(EMAIL_MAX_LENGTH) + " characters or fewer.")
    elif not _EMAIL_RE.match(email):
        errors.append("Enter a valid email address.")
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

    # ----- message: required, reasonable maximum length -----
    message = (form.get("message") or "").strip()
    if not message:
        errors.append("Message is required.")
    elif len(message) > MESSAGE_MAX_LENGTH:
        errors.append("Message must be " + str(MESSAGE_MAX_LENGTH) + " characters or fewer.")
    elif _has_dangerous_scheme(message):
        errors.append("Message contains content that is not allowed.")
    cleaned["message"] = message

    # ----- property_id: required, must be a valid integer id that exists -----
    property_raw = (form.get("property_id") or "").strip()
    property_id = None
    if not property_raw:
        errors.append("Property is required.")
    else:
        try:
            property_id = int(property_raw)
        except ValueError:
            errors.append("Property must be a valid id.")
            property_id = None
        else:
            if property_id not in valid_property_ids:
                errors.append("That property does not exist.")
                property_id = None
    cleaned["property_id"] = property_id

    # ----- status: only the three controlled values; defaults to "New" -----
    # A customer's Create form never renders this field at all, so it is
    # simply absent from request.form and defaults here - the customer
    # never gets to choose the status (Section 6).
    status = (form.get("status") or "").strip() or "New"
    if status not in STATUSES:
        errors.append("Status must be one of: " + ", ".join(STATUSES) + ".")
        status = "New"
    cleaned["status"] = status

    if errors:
        return errors, None
    return [], cleaned


def validate_status_transition(current_status, new_status):
    """Enforce the Section 11 workflow rule: New -> Contacted -> Closed only
    ever moves forward (skipping a step, e.g. New straight to Closed, is
    still forward and allowed; going backward, e.g. Closed back to New, is
    not). Returns an error message, or None when the move is allowed.

    Kept deliberately simple (an index comparison, not a hand-written
    table of pairs) so it stays easy to read and to unit-test on its own.
    """
    if new_status not in _STATUS_ORDER:
        return "Status must be one of: " + ", ".join(STATUSES) + "."
    if current_status not in _STATUS_ORDER:
        # The stored status is already outside the controlled ENUM values,
        # which the database itself never allows - nothing more to check.
        return None
    if _STATUS_ORDER[new_status] < _STATUS_ORDER[current_status]:
        return "An inquiry cannot move backward from '" + current_status + "' to '" + new_status + "'."
    return None
