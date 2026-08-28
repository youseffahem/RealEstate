"""Server-side validation for the Real Estate `properties` form, plus the
business rules that tie `listing_type` to `status`.

Every function here is plain Python with no database access, so it can be
unit-tested without MySQL. The caller (a Flask route in app.py) fetches the
currently valid foreign key ids with property_queries.get_valid_ids() and
passes them in, so a property can never be saved pointing at a property
type, location or agent that does not exist.
"""

import math
from urllib.parse import urlsplit

TITLE_MAX_LENGTH = 180          # matches properties.title VARCHAR(180)
DESCRIPTION_MAX_LENGTH = 4000   # reasonable cap; column itself is TEXT

# matches property_images.image_url VARCHAR(500)
IMAGE_URL_MAX_LENGTH = 500
# Keeps the gallery lightweight (Phase 4 requirement) - no property ever
# preloads or has to page through hundreds of thumbnails.
MAX_IMAGES_PER_PROPERTY = 12
# Only a plain http(s) link is ever stored or rendered as an <img src>.
# This is what actually blocks javascript:/data:/vbscript: URLs - they
# simply are not "http" or "https".
ALLOWED_IMAGE_URL_SCHEMES = {"http", "https"}

# price is DECIMAL(14, 2): 12 digits before the point, 2 after.
MAX_PRICE = 10 ** 12 - 0.01
# area_sqm is DECIMAL(8, 2): 6 digits before the point, 2 after.
MAX_AREA = 10 ** 6 - 0.01
# bedrooms/bathrooms are TINYINT UNSIGNED.
MAX_ROOM_COUNT = 255

LISTING_TYPES = ("For Sale", "For Rent")
STATUSES = ("Available", "Reserved", "Sold", "Rented")

# Business rule: which statuses make sense for each listing type.
#   For Sale + Rented  -> rejected (a sale listing can't be "rented")
#   For Rent + Sold     -> rejected (a rental listing can't be "sold")
ALLOWED_STATUSES_BY_LISTING_TYPE = {
    "For Sale": {"Available", "Reserved", "Sold"},
    "For Rent": {"Available", "Reserved", "Rented"},
}


def validate_property_payload(form, valid_ids):
    """Validate a property submission.

    `form` is anything with .get(name) - typically request.form.
    `valid_ids` is {"property_type_ids": set, "location_ids": set,
    "agent_ids": set}, from property_queries.get_valid_ids().

    Returns (errors, cleaned): `errors` is a list of human-readable
    messages (empty when the payload is valid); `cleaned` is the
    ready-to-store dict when there are no errors, otherwise None.
    """
    errors = []
    cleaned = {}

    # ----- title: required, trimmed, reasonable maximum length -----
    title = (form.get("title") or "").strip()
    if not title:
        errors.append("Title is required.")
    elif len(title) > TITLE_MAX_LENGTH:
        errors.append("Title must be " + str(TITLE_MAX_LENGTH) + " characters or fewer.")
    cleaned["title"] = title

    # ----- description: nullable, reasonable maximum length -----
    description = (form.get("description") or "").strip()
    if len(description) > DESCRIPTION_MAX_LENGTH:
        errors.append("Description must be " + str(DESCRIPTION_MAX_LENGTH) + " characters or fewer.")
    cleaned["description"] = description or None

    # ----- property_type_id: required, must reference an existing row -----
    property_type_id = _parse_required_id(form.get("property_type_id"), "Property type", errors)
    if property_type_id is not None and property_type_id not in valid_ids["property_type_ids"]:
        errors.append("That property type does not exist.")
        property_type_id = None
    cleaned["property_type_id"] = property_type_id

    # ----- location_id: required, must reference an existing row -----
    location_id = _parse_required_id(form.get("location_id"), "Location", errors)
    if location_id is not None and location_id not in valid_ids["location_ids"]:
        errors.append("That location does not exist.")
        location_id = None
    cleaned["location_id"] = location_id

    # ----- agent_id: nullable, must reference an existing row if given -----
    agent_raw = (form.get("agent_id") or "").strip()
    agent_id = None
    if agent_raw:
        try:
            agent_id = int(agent_raw)
        except ValueError:
            errors.append("Agent must be a valid id.")
            agent_id = None
        else:
            if agent_id not in valid_ids["agent_ids"]:
                errors.append("That agent does not exist.")
                agent_id = None
    cleaned["agent_id"] = agent_id

    # ----- listing_type: only "For Sale" or "For Rent" -----
    listing_type = (form.get("listing_type") or "").strip()
    if listing_type not in LISTING_TYPES:
        errors.append("Listing type must be 'For Sale' or 'For Rent'.")
    cleaned["listing_type"] = listing_type

    # ----- price: required, numeric, finite, >= 0, fits DECIMAL(14, 2) -----
    cleaned["price"] = _parse_price(form.get("price"), errors)

    # ----- area_sqm: required, numeric, finite, > 0, fits DECIMAL(8, 2) -----
    cleaned["area_sqm"] = _parse_area(form.get("area_sqm"), errors)

    # ----- bedrooms / bathrooms: nullable, integer if provided, >= 0 -----
    cleaned["bedrooms"] = _parse_room_count(form.get("bedrooms"), "Bedrooms", errors)
    cleaned["bathrooms"] = _parse_room_count(form.get("bathrooms"), "Bathrooms", errors)

    # ----- status: only the four controlled values (defaults to Available) -----
    status = (form.get("status") or "").strip() or "Available"
    if status not in STATUSES:
        errors.append("Status must be one of: " + ", ".join(STATUSES) + ".")
    cleaned["status"] = status

    # ----- business rule: listing_type <-> status -----
    if listing_type in ALLOWED_STATUSES_BY_LISTING_TYPE and status in STATUSES:
        allowed = ALLOWED_STATUSES_BY_LISTING_TYPE[listing_type]
        if status not in allowed:
            errors.append(
                "A '" + listing_type + "' property cannot have status '" + status + "'."
            )

    if errors:
        return errors, None
    return [], cleaned


def validate_image_urls(raw_urls):
    """Validate the gallery URLs typed into the create/edit form.

    `raw_urls` is a list of strings (typically request.form.getlist
    ("image_urls")). A blank entry (an empty row the user never filled in)
    is silently dropped rather than treated as an error. Every non-blank
    entry must be a plain http:// or https:// URL with a domain - this is
    what rejects javascript:, data:, vbscript: and any other scheme.

    Returns (errors, cleaned): `errors` is a list of human-readable
    messages (empty when every URL is fine); `cleaned` is the ordered
    list of URLs to store (their position becomes property_images.
    sort_order), always returned even when there are errors, so the
    caller can decide whether to use it.
    """
    errors = []
    cleaned = []

    for raw in raw_urls:
        url = (raw or "").strip()
        if not url:
            continue

        if len(url) > IMAGE_URL_MAX_LENGTH:
            errors.append(
                "Image URL is too long (max " + str(IMAGE_URL_MAX_LENGTH) + " characters)."
            )
            continue

        # Accept locally uploaded files (served at /uploads/...)
        if url.startswith("/uploads/"):
            cleaned.append(url)
            continue

        parsed = urlsplit(url)
        if parsed.scheme.lower() not in ALLOWED_IMAGE_URL_SCHEMES:
            errors.append("Image URL must start with http:// or https://.")
            continue
        if not parsed.netloc:
            errors.append("Image URL is missing a domain.")
            continue

        cleaned.append(url)

    if len(cleaned) > MAX_IMAGES_PER_PROPERTY:
        errors.append("A property can have at most " + str(MAX_IMAGES_PER_PROPERTY) + " images.")

    return errors, cleaned


# =====================================================================
# Field-level helpers
# =====================================================================

def _parse_required_id(raw, label, errors):
    raw = (raw or "").strip()
    if not raw:
        errors.append(label + " is required.")
        return None
    try:
        return int(raw)
    except ValueError:
        errors.append(label + " must be a valid id.")
        return None


def _parse_price(raw, errors):
    raw = (raw or "").strip()
    if not raw:
        errors.append("Price is required.")
        return None
    try:
        price = float(raw)
    except ValueError:
        errors.append("Price must be a number.")
        return None
    # float() also accepts "nan", "inf" and "1e400" - none of which the
    # DECIMAL(14, 2) column can store.
    if not math.isfinite(price):
        errors.append("Price must be a real number.")
        return None
    if price < 0:
        errors.append("Price cannot be negative.")
        return None
    if price > MAX_PRICE:
        errors.append("Price is too large for this database column.")
        return None
    return price


def _parse_area(raw, errors):
    raw = (raw or "").strip()
    if not raw:
        errors.append("Area is required.")
        return None
    try:
        area = float(raw)
    except ValueError:
        errors.append("Area must be a number.")
        return None
    if not math.isfinite(area):
        errors.append("Area must be a real number.")
        return None
    if area <= 0:
        errors.append("Area must be greater than zero.")
        return None
    if area > MAX_AREA:
        errors.append("Area is too large for this database column.")
        return None
    return area


def _parse_room_count(raw, label, errors):
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        count = int(raw)
    except ValueError:
        errors.append(label + " must be a whole number.")
        return None
    if count < 0:
        errors.append(label + " cannot be negative.")
        return None
    if count > MAX_ROOM_COUNT:
        errors.append(label + " is too large.")
        return None
    return count
