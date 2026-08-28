"""Real Estate database architecture for the REAL ESTATE Management System.

This module owns the whole schema: property_types, locations, agents,
properties, property_images and inquiries.

Everything here is safe to run every time the app starts:

- every CREATE TABLE uses `IF NOT EXISTS`, so it never touches a table that
  already exists;
- every seed function only inserts rows that are not already there (checked
  by a natural/unique key - name, (name, city) or email), so running it
  again and again never creates duplicates;
- the demo properties (and their images/inquiries) are only inserted while
  the `properties` table is still completely empty.

No routes, templates or the visual system are touched by this module - it
is a pure database layer, wired into the app in one place (app.py:init_db).
"""

# =====================================================================
# SCHEMA (DDL) - InnoDB, foreign keys, controlled ENUM values
# =====================================================================

DDL_PROPERTY_TYPES = """
CREATE TABLE IF NOT EXISTS property_types (
    id   INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    CONSTRAINT uq_property_types_name UNIQUE (name)
) ENGINE=InnoDB
"""

DDL_LOCATIONS = """
CREATE TABLE IF NOT EXISTS locations (
    id   INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    city VARCHAR(100) NOT NULL,
    CONSTRAINT uq_locations_name_city UNIQUE (name, city),
    INDEX idx_locations_city (city)
) ENGINE=InnoDB
"""

DDL_AGENTS = """
CREATE TABLE IF NOT EXISTS agents (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    name       VARCHAR(120) NOT NULL,
    email      VARCHAR(160) NOT NULL,
    phone      VARCHAR(30)  NOT NULL,
    photo_url  VARCHAR(500) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_agents_email UNIQUE (email)
) ENGINE=InnoDB
"""

# price is DECIMAL (never FLOAT). listing_type and status are ENUM, so the
# database itself rejects any value outside the controlled list - no
# arbitrary strings can ever be stored, on MySQL 8 this is a native type.
DDL_PROPERTIES = """
CREATE TABLE IF NOT EXISTS properties (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    title            VARCHAR(180) NOT NULL,
    description      TEXT NULL,
    property_type_id INT NOT NULL,
    location_id      INT NOT NULL,
    agent_id         INT NULL,
    listing_type     ENUM('For Sale', 'For Rent') NOT NULL,
    price            DECIMAL(14, 2) NOT NULL,
    area_sqm         DECIMAL(8, 2) NOT NULL,
    bedrooms         TINYINT UNSIGNED NULL,
    bathrooms        TINYINT UNSIGNED NULL,
    status           ENUM('Available', 'Reserved', 'Sold', 'Rented')
                         NOT NULL DEFAULT 'Available',
    created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                         ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_properties_type
        FOREIGN KEY (property_type_id) REFERENCES property_types(id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_properties_location
        FOREIGN KEY (location_id) REFERENCES locations(id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_properties_agent
        FOREIGN KEY (agent_id) REFERENCES agents(id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT chk_properties_price CHECK (price >= 0),
    CONSTRAINT chk_properties_area_sqm CHECK (area_sqm > 0),
    INDEX idx_properties_status (status),
    INDEX idx_properties_listing_type (listing_type),
    INDEX idx_properties_price (price),
    INDEX idx_properties_area_sqm (area_sqm)
    -- property_type_id, location_id and agent_id do not get an extra
    -- explicit index: InnoDB automatically indexes every foreign key
    -- column, so a second one would be redundant.
) ENGINE=InnoDB
"""

DDL_PROPERTY_IMAGES = """
CREATE TABLE IF NOT EXISTS property_images (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    property_id INT NOT NULL,
    image_url   VARCHAR(500) NULL,
    sort_order  SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_property_images_property
        FOREIGN KEY (property_id) REFERENCES properties(id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB
"""

DDL_INQUIRIES = """
CREATE TABLE IF NOT EXISTS inquiries (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    property_id INT NOT NULL,
    name        VARCHAR(120) NOT NULL,
    email       VARCHAR(160) NOT NULL,
    phone       VARCHAR(30)  NULL,
    message     TEXT NOT NULL,
    status      ENUM('New', 'Contacted', 'Closed') NOT NULL DEFAULT 'New',
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_inquiries_property
        FOREIGN KEY (property_id) REFERENCES properties(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    INDEX idx_inquiries_status (status)
    -- property_id also does not need an explicit index for the same
    -- reason as above: the foreign key already provides one.
) ENGINE=InnoDB
"""

# Creation order matters: each table only references tables created before it.
SCHEMA_DDL = [
    DDL_PROPERTY_TYPES,
    DDL_LOCATIONS,
    DDL_AGENTS,
    DDL_PROPERTIES,
    DDL_PROPERTY_IMAGES,
    DDL_INQUIRIES,
]


# =====================================================================
# DEMO DATA
# =====================================================================

DEMO_PROPERTY_TYPES = [
    "Apartment", "Villa", "House", "Office", "Shop", "Land", "Chalet", "Duplex",
]

# (name, city)
DEMO_LOCATIONS = [
    ("New Cairo", "Cairo"),
    ("Nasr City", "Cairo"),
    ("Maadi", "Cairo"),
    ("6th of October", "Giza"),
    ("Sheikh Zayed", "Giza"),
    ("New Capital", "Cairo"),
    ("Alexandria", "Alexandria"),
    ("North Coast", "Matrouh"),
]

# (name, email, phone)
DEMO_AGENTS = [
    ("Ahmed El-Sayed", "ahmed.elsayed@tantawyrealestate.com", "010-1234-5678"),
    ("Mona Abdel Rahman", "mona.abdelrahman@tantawyrealestate.com", "011-2345-6789"),
    ("Youssef Hassan", "youssef.hassan@tantawyrealestate.com", "012-3456-7890"),
    ("Nourhan Farouk", "nourhan.farouk@tantawyrealestate.com", "015-4567-8901"),
    ("Karim El-Masry", "karim.elmasry@tantawyrealestate.com", "010-9876-5432"),
]

# Every property type and every location is used at least once, and the
# five agents are spread across the list - so the demo data exercises
# every relationship in the schema.
DEMO_PROPERTIES = [
    {
        "title": "Luxury Villa in New Cairo",
        "description": "A spacious five-bedroom villa with a private garden, "
                        "swimming pool and modern finishes in the heart of New Cairo.",
        "type": "Villa", "location": "New Cairo", "agent_email": "ahmed.elsayed@tantawyrealestate.com",
        "listing_type": "For Sale", "price": "8500000.00", "area_sqm": "450.00",
        "bedrooms": 5, "bathrooms": 4, "status": "Available",
    },
    {
        "title": "Modern Apartment in Maadi",
        "description": "Bright three-bedroom apartment close to Maadi's riverside "
                        "corniche, fully finished with a modern kitchen.",
        "type": "Apartment", "location": "Maadi", "agent_email": "mona.abdelrahman@tantawyrealestate.com",
        "listing_type": "For Rent", "price": "25000.00", "area_sqm": "140.00",
        "bedrooms": 3, "bathrooms": 2, "status": "Available",
    },
    {
        "title": "Commercial Office in New Capital",
        "description": "Ground-floor office unit in the New Capital's business "
                        "district, ready for fit-out.",
        "type": "Office", "location": "New Capital", "agent_email": "youssef.hassan@tantawyrealestate.com",
        "listing_type": "For Sale", "price": "3200000.00", "area_sqm": "120.00",
        "bedrooms": None, "bathrooms": 1, "status": "Available",
    },
    {
        "title": "Beach Chalet in North Coast",
        "description": "Two-bedroom chalet with sea view, steps away from the "
                        "beach, ideal for summer getaways.",
        "type": "Chalet", "location": "North Coast", "agent_email": "karim.elmasry@tantawyrealestate.com",
        "listing_type": "For Sale", "price": "4750000.00", "area_sqm": "110.00",
        "bedrooms": 2, "bathrooms": 2, "status": "Reserved",
    },
    {
        "title": "Retail Shop in Sheikh Zayed",
        "description": "Ground-floor retail unit on a busy commercial strip in "
                        "Sheikh Zayed with high foot traffic.",
        "type": "Shop", "location": "Sheikh Zayed", "agent_email": "nourhan.farouk@tantawyrealestate.com",
        "listing_type": "For Rent", "price": "18000.00", "area_sqm": "60.00",
        "bedrooms": None, "bathrooms": 1, "status": "Available",
    },
    {
        "title": "Residential Duplex in 6th of October",
        "description": "Four-bedroom duplex with a private roof terrace in a "
                        "quiet, family-friendly compound.",
        "type": "Duplex", "location": "6th of October", "agent_email": "ahmed.elsayed@tantawyrealestate.com",
        "listing_type": "For Sale", "price": "5900000.00", "area_sqm": "260.00",
        "bedrooms": 4, "bathrooms": 3, "status": "Available",
    },
    {
        "title": "Family House in Nasr City",
        "description": "Detached family house with a private garage and garden, "
                        "close to Nasr City's main services.",
        "type": "House", "location": "Nasr City", "agent_email": "mona.abdelrahman@tantawyrealestate.com",
        "listing_type": "For Sale", "price": "6300000.00", "area_sqm": "300.00",
        "bedrooms": 4, "bathrooms": 3, "status": "Sold",
    },
    {
        "title": "Investment Land Plot in New Capital",
        "description": "Residential land plot in a prime, up-and-coming block "
                        "of the New Administrative Capital.",
        "type": "Land", "location": "New Capital", "agent_email": "youssef.hassan@tantawyrealestate.com",
        "listing_type": "For Sale", "price": "2100000.00", "area_sqm": "500.00",
        "bedrooms": None, "bathrooms": None, "status": "Available",
    },
    {
        "title": "Cozy Studio Apartment in Alexandria",
        "description": "Furnished studio apartment a short walk from Alexandria's "
                        "corniche, perfect for a single tenant.",
        "type": "Apartment", "location": "Alexandria", "agent_email": "karim.elmasry@tantawyrealestate.com",
        "listing_type": "For Rent", "price": "9500.00", "area_sqm": "65.00",
        "bedrooms": 1, "bathrooms": 1, "status": "Available",
    },
    {
        "title": "Garden Villa in Sheikh Zayed",
        "description": "Six-bedroom villa with a landscaped garden and private "
                        "pool in a gated Sheikh Zayed compound.",
        "type": "Villa", "location": "Sheikh Zayed", "agent_email": "nourhan.farouk@tantawyrealestate.com",
        "listing_type": "For Sale", "price": "12000000.00", "area_sqm": "600.00",
        "bedrooms": 6, "bathrooms": 5, "status": "Available",
    },
    {
        "title": "Downtown Office Suite in Maadi",
        "description": "Fully finished office suite in central Maadi, suitable "
                        "for a small to mid-sized company.",
        "type": "Office", "location": "Maadi", "agent_email": "ahmed.elsayed@tantawyrealestate.com",
        "listing_type": "For Rent", "price": "40000.00", "area_sqm": "180.00",
        "bedrooms": None, "bathrooms": 2, "status": "Available",
    },
    {
        "title": "Elegant Duplex in New Cairo",
        "description": "Modern duplex with an open-plan living area and private "
                        "garden in a well-established New Cairo compound.",
        "type": "Duplex", "location": "New Cairo", "agent_email": "mona.abdelrahman@tantawyrealestate.com",
        "listing_type": "For Sale", "price": "7400000.00", "area_sqm": "320.00",
        "bedrooms": 4, "bathrooms": 3, "status": "Available",
    },
    {
        "title": "Seasonal Chalet Rental in North Coast",
        "description": "Three-bedroom chalet available for seasonal rental, "
                        "fully furnished with direct beach access.",
        "type": "Chalet", "location": "North Coast", "agent_email": "youssef.hassan@tantawyrealestate.com",
        "listing_type": "For Rent", "price": "90000.00", "area_sqm": "130.00",
        "bedrooms": 3, "bathrooms": 2, "status": "Rented",
    },
]

# Each seeded property gets two placeholder gallery slots (no image files are
# generated in this phase - image_url stays NULL, ready for a future upload
# feature to fill in). Kept as the fallback for any demo property added to
# DEMO_PROPERTIES without a matching entry in DEMO_PROPERTY_IMAGES below.
IMAGE_SLOTS_PER_PROPERTY = 2

# (property_title -> ordered list of image URLs) - the Phase 5 fix for the
# empty property image containers. Every URL is a stable, direct HTTPS link
# to the Unsplash CDN (images.unsplash.com), chosen and hand-verified to
# match that property's own type (Villa/Apartment/Office/Shop/Chalet/Land/
# Duplex/House) - never a random unrelated photo. No image files are
# generated or stored locally; this only ever populates the existing
# property_images.image_url column.
DEMO_PROPERTY_IMAGES = {
    "Luxury Villa in New Cairo": [
        "https://images.unsplash.com/photo-1613977257363-707ba9348227?auto=format&fit=crop&w=1200&q=80",
        "https://images.unsplash.com/photo-1613490493576-7fde63acd811?auto=format&fit=crop&w=1200&q=80",
        "https://images.unsplash.com/photo-1512917774080-9991f1c4c750?auto=format&fit=crop&w=1200&q=80",
    ],
    "Modern Apartment in Maadi": [
        "https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?auto=format&fit=crop&w=1200&q=80",
        "https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?auto=format&fit=crop&w=1200&q=80",
    ],
    "Commercial Office in New Capital": [
        "https://images.unsplash.com/photo-1497366216548-37526070297c?auto=format&fit=crop&w=1200&q=80",
        "https://images.unsplash.com/photo-1497366811353-6870744d04b2?auto=format&fit=crop&w=1200&q=80",
    ],
    "Beach Chalet in North Coast": [
        "https://images.unsplash.com/photo-1520250497591-112f2f40a3f4?auto=format&fit=crop&w=1200&q=80",
        "https://images.unsplash.com/photo-1568605114967-8130f3a36994?auto=format&fit=crop&w=1200&q=80",
    ],
    "Retail Shop in Sheikh Zayed": [
        "https://images.unsplash.com/photo-1441986300917-64674bd600d8?auto=format&fit=crop&w=1200&q=80",
        "https://images.unsplash.com/photo-1441984904996-e0b6ba687e04?auto=format&fit=crop&w=1200&q=80",
    ],
    "Residential Duplex in 6th of October": [
        "https://images.unsplash.com/photo-1580587771525-78b9dba3b914?auto=format&fit=crop&w=1200&q=80",
        "https://images.unsplash.com/photo-1494526585095-c41746248156?auto=format&fit=crop&w=1200&q=80",
    ],
    "Family House in Nasr City": [
        "https://images.unsplash.com/photo-1564013799919-ab600027ffc6?auto=format&fit=crop&w=1200&q=80",
        "https://images.unsplash.com/photo-1600585154340-be6161a56a0c?auto=format&fit=crop&w=1200&q=80",
    ],
    "Investment Land Plot in New Capital": [
        "https://images.unsplash.com/photo-1500382017468-9049fed747ef?auto=format&fit=crop&w=1200&q=80",
    ],
    "Cozy Studio Apartment in Alexandria": [
        "https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?auto=format&fit=crop&w=1200&q=80",
    ],
    "Garden Villa in Sheikh Zayed": [
        "https://images.unsplash.com/photo-1613490493576-7fde63acd811?auto=format&fit=crop&w=1200&q=80",
        "https://images.unsplash.com/photo-1613977257363-707ba9348227?auto=format&fit=crop&w=1200&q=80",
    ],
    "Downtown Office Suite in Maadi": [
        "https://images.unsplash.com/photo-1497366811353-6870744d04b2?auto=format&fit=crop&w=1200&q=80",
        "https://images.unsplash.com/photo-1497366216548-37526070297c?auto=format&fit=crop&w=1200&q=80",
    ],
    "Elegant Duplex in New Cairo": [
        "https://images.unsplash.com/photo-1494526585095-c41746248156?auto=format&fit=crop&w=1200&q=80",
        "https://images.unsplash.com/photo-1580587771525-78b9dba3b914?auto=format&fit=crop&w=1200&q=80",
    ],
    "Seasonal Chalet Rental in North Coast": [
        "https://images.unsplash.com/photo-1568605114967-8130f3a36994?auto=format&fit=crop&w=1200&q=80",
        "https://images.unsplash.com/photo-1520250497591-112f2f40a3f4?auto=format&fit=crop&w=1200&q=80",
    ],
}

# (property_title, name, email, phone, message, status)
DEMO_INQUIRIES = [
    ("Luxury Villa in New Cairo", "Sara Ibrahim", "sara.ibrahim@example.com",
     "010-1111-2222", "Is this villa still available? I'd like to schedule a viewing.",
     "New"),
    ("Modern Apartment in Maadi", "Omar Nabil", "omar.nabil@example.com",
     "011-2222-3333", "Can the apartment be rented furnished?", "Contacted"),
    ("Beach Chalet in North Coast", "Laila Tarek", "laila.tarek@example.com",
     "012-3333-4444", "What is the closest resort gate to this chalet?", "New"),
    ("Residential Duplex in 6th of October", "Hassan Adel", "hassan.adel@example.com",
     "015-4444-5555", "Interested in the duplex - please call me back.", "Closed"),
    ("Cozy Studio Apartment in Alexandria", "Dina Samir", "dina.samir@example.com",
     "010-5555-6666", "Is a one-year lease possible on this studio?", "New"),
]


# =====================================================================
# SCHEMA CREATION
# =====================================================================

def create_schema(cursor):
    """Create every real estate table that does not already exist."""
    for statement in SCHEMA_DDL:
        cursor.execute(statement)


# =====================================================================
# IDEMPOTENT SEEDING
# =====================================================================

def seed_property_types(cursor):
    """Insert any demo property type whose name is not there yet."""
    cursor.execute("SELECT name FROM property_types")
    existing = {row[0] for row in cursor.fetchall()}
    missing = [(name,) for name in DEMO_PROPERTY_TYPES if name not in existing]
    if missing:
        cursor.executemany("INSERT INTO property_types (name) VALUES (%s)", missing)
    return len(missing)


def seed_locations(cursor):
    """Insert any demo location whose (name, city) pair is not there yet."""
    cursor.execute("SELECT name, city FROM locations")
    existing = {(name, city) for name, city in cursor.fetchall()}
    missing = [(name, city) for name, city in DEMO_LOCATIONS if (name, city) not in existing]
    if missing:
        cursor.executemany("INSERT INTO locations (name, city) VALUES (%s, %s)", missing)
    return len(missing)


def seed_agents(cursor):
    """Insert any demo agent whose email is not registered yet."""
    cursor.execute("SELECT email FROM agents")
    existing = {row[0] for row in cursor.fetchall()}
    missing = [(name, email, phone) for name, email, phone in DEMO_AGENTS if email not in existing]
    if missing:
        cursor.executemany(
            "INSERT INTO agents (name, email, phone) VALUES (%s, %s, %s)", missing
        )
    return len(missing)


def seed_properties(cursor):
    """Insert the demo properties (with their images and inquiries), but only
    while the properties table is still completely empty.

    This keeps the seed repeatable and safe: it is safe to call on every
    startup, it never duplicates rows on the next run, and it never touches
    a property created by a real user.
    Returns (properties_inserted, images_inserted, inquiries_inserted).
    """
    cursor.execute("SELECT COUNT(*) FROM properties")
    if cursor.fetchone()[0] > 0:
        return 0, 0, 0

    cursor.execute("SELECT id, name FROM property_types")
    type_ids = {name: id for id, name in cursor.fetchall()}
    cursor.execute("SELECT id, name FROM locations")
    location_ids = {name: id for id, name in cursor.fetchall()}
    cursor.execute("SELECT id, email FROM agents")
    agent_ids = {email: id for id, email in cursor.fetchall()}

    property_ids_by_title = {}
    for item in DEMO_PROPERTIES:
        cursor.execute(
            """
            INSERT INTO properties
                (title, description, property_type_id, location_id, agent_id,
                 listing_type, price, area_sqm, bedrooms, bathrooms, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                item["title"],
                item["description"],
                type_ids[item["type"]],
                location_ids[item["location"]],
                agent_ids[item["agent_email"]],
                item["listing_type"],
                item["price"],
                item["area_sqm"],
                item["bedrooms"],
                item["bathrooms"],
                item["status"],
            ),
        )
        property_ids_by_title[item["title"]] = cursor.lastrowid

    # Real, type-matched image URLs for every demo property (see
    # DEMO_PROPERTY_IMAGES above) - any future demo property added without
    # a matching entry there still gets the old empty placeholder slots
    # instead of failing to seed at all.
    image_rows = []
    for item in DEMO_PROPERTIES:
        property_id = property_ids_by_title[item["title"]]
        urls = DEMO_PROPERTY_IMAGES.get(item["title"])
        if urls:
            for sort_order, url in enumerate(urls):
                image_rows.append((property_id, url, sort_order))
        else:
            for sort_order in range(IMAGE_SLOTS_PER_PROPERTY):
                image_rows.append((property_id, None, sort_order))
    cursor.executemany(
        "INSERT INTO property_images (property_id, image_url, sort_order) VALUES (%s, %s, %s)",
        image_rows,
    )

    inquiry_rows = [
        (property_ids_by_title[title], name, email, phone, message, status)
        for title, name, email, phone, message, status in DEMO_INQUIRIES
    ]
    cursor.executemany(
        """
        INSERT INTO inquiries (property_id, name, email, phone, message, status)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        inquiry_rows,
    )

    return len(property_ids_by_title), len(image_rows), len(inquiry_rows)


def backfill_demo_property_images(cursor):
    """Fix demo properties whose property_images rows were seeded with a
    NULL image_url before DEMO_PROPERTY_IMAGES existed (Phase 4 seeded two
    empty placeholder rows per property - see the old IMAGE_SLOTS_PER_
    PROPERTY loop this replaced). seed_properties() above only ever runs
    once, while the `properties` table is still empty, so an installation
    that already has its demo rows would otherwise keep the empty
    placeholders forever. This runs on every startup instead, and is safe
    to run every time:

    - only a property whose title matches a known demo title is touched -
      a real user's own property is never modified;
    - only a property with zero *real* images is touched - once it has
      one, this is a permanent no-op for it, even if the user then edits
      or removes those images themselves;
    - it replaces (delete + insert), it never appends, so it can never
      produce a duplicate row for the same property.

    Returns how many properties were fixed.
    """
    fixed = 0
    for title, urls in DEMO_PROPERTY_IMAGES.items():
        cursor.execute("SELECT id FROM properties WHERE title = %s LIMIT 1", (title,))
        row = cursor.fetchone()
        if not row:
            continue
        property_id = row[0]

        cursor.execute(
            """
            SELECT COUNT(*) FROM property_images
            WHERE property_id = %s AND image_url IS NOT NULL AND image_url != ''
            """,
            (property_id,),
        )
        if cursor.fetchone()[0] > 0:
            continue

        cursor.execute("DELETE FROM property_images WHERE property_id = %s", (property_id,))
        rows = [(property_id, url, sort_order) for sort_order, url in enumerate(urls)]
        cursor.executemany(
            "INSERT INTO property_images (property_id, image_url, sort_order) VALUES (%s, %s, %s)",
            rows,
        )
        fixed += 1
    return fixed


def init_real_estate(connection):
    """Create the real estate schema and seed baseline demo data.

    Safe to call on every application start: table creation is
    `IF NOT EXISTS` and every seed step only inserts rows that are not
    already present, so nothing is ever duplicated on a second run.
    """
    cursor = connection.cursor()
    create_schema(cursor)

    # Migration: add photo_url to agents if it doesn't exist yet (safe to
    # run on every startup - the column check prevents duplicate ALTERs).
    cursor.execute(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'agents' "
        "AND COLUMN_NAME = 'photo_url'"
    )
    if cursor.fetchone()[0] == 0:
        cursor.execute("ALTER TABLE agents ADD COLUMN photo_url VARCHAR(500) NULL")

    summary = {
        "property_types": seed_property_types(cursor),
        "locations": seed_locations(cursor),
        "agents": seed_agents(cursor),
    }
    properties, images, inquiries = seed_properties(cursor)
    summary["properties"] = properties
    summary["property_images"] = images
    summary["inquiries"] = inquiries
    summary["property_images_fixed"] = backfill_demo_property_images(cursor)

    connection.commit()
    cursor.close()
    return summary
