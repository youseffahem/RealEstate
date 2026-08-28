# REAL ESTATE — Property Management

A **Create / Read / Update / Delete** application built with **Flask**, **MySQL** and
**Jinja2**, with a hand-written front end (vanilla CSS and JavaScript — no frameworks).

The app is now a **Real Estate Management System**: a full property portfolio (dashboard,
search/filter, create/edit/delete, property details) sits alongside the original product
catalog it grew out of. See [Real Estate frontend (Phase 3)](#real-estate-frontend-phase-3)
below for the property-facing routes and templates.

---

## The four CRUD operations

| Operation  | Route                    | Method      | Where you see it in the app                          |
|------------|--------------------------|-------------|------------------------------------------------------|
| **CREATE** | `/add`                   | `GET`,`POST`| "Add product" in the header, or the empty-state button |
| **READ**   | `/`                      | `GET`       | The product list and the four live statistics cards   |
| **UPDATE** | `/edit/<id>`             | `GET`,`POST`| The **Edit** button on every product row              |
| **DELETE** | `/delete/<id>`           | `POST` only | The **Delete** button, behind a confirmation dialog   |

Every SQL statement is **parameterised** (`%s` placeholders), so user input can never be
executed as SQL. All output goes through Jinja2 autoescaping, so it can never be executed as
HTML. Delete is **POST only** — opening `/delete/1` in the address bar does nothing.

---

## Running it

**1. Install the dependencies**

```
pip install -r requirements.txt
```

**2. Set the database connection** in a `.env` file next to `app.py`:

```
SECRET_KEY=change-this-to-your-own-random-secret
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your-mysql-password
DB_NAME=product_crud
```

**3. Start it** — either command works:

```
python app.py          # development server on http://127.0.0.1:5000
flask run              # same app, standard Flask launcher
```

The database, the `products` table and a demo catalog are created automatically on the first
start. Nothing has to be set up by hand.

---

## The database

```sql
CREATE TABLE products (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(120)   NOT NULL,
    price       DECIMAL(10, 2) NOT NULL,
    description TEXT           NOT NULL
);
```

The four dashboard cards are **real aggregate queries** — `COUNT(*)`, `SUM(price)`,
`AVG(price)` and the newest row. Nothing is hard coded, so the numbers move as you create,
edit and delete.

### Demo data

The demo catalog is inserted automatically **only while the table is empty**, so it never
duplicates itself and never competes with products you added yourself. To add it to a database
that already has rows in it:

```
python seed.py
```

That script inserts only the demo products that are missing, so running it twice does nothing.

---

## Real Estate database (Phase 1)

The app was transformed from a product catalog into a **Real Estate Management System**
across three phases. Phase 1 added the real estate database architecture *alongside* the
existing `products` table, without touching any route, template or the visual system.

```
property_types                locations                  agents
┌──────────────┐               ┌──────────────┐           ┌──────────────┐
│ id            │               │ id            │           │ id            │
│ name (unique) │               │ name, city    │           │ name          │
└──────┬────────┘               └──────┬────────┘           │ email (unique)│
       │ 1                             │ 1                   │ phone         │
       │                               │                     └──────┬────────┘
       │ N                             │ N                          │ 1
       └────────────────┐   ┌──────────┘                            │
                         ▼   ▼                                      │ N
                     properties  ◄─────────────────────────────────┘
                    (title, description, listing_type, price DECIMAL,
                     area_sqm, bedrooms, bathrooms, status,
                     created_at, updated_at)
                     │ 1                        │ 1
                     │ N                        │ N
                     ▼                          ▼
              property_images              inquiries
              (image_url, sort_order)      (name, email, phone, message, status)
```

- `listing_type` is a **controlled ENUM**: `For Sale`, `For Rent`.
- `status` is a **controlled ENUM**: `Available`, `Reserved`, `Sold`, `Rented`.
- `price` is `DECIMAL(14, 2)` — never `FLOAT` — with a `CHECK (price >= 0)` constraint.
- Every foreign key uses `InnoDB`; deleting a property cascades to its images and inquiries.
- Seed data (8 property types, 8 locations, 5 agents, 13 properties) is inserted the same
  idempotent way as the product catalog: nothing is duplicated on a second `python app.py`.

Run `python seed_real_estate.py` to top up an existing database with any demo rows it is
missing — see [`real_estate_db.py`](real_estate_db.py) for the full schema and seed data.

**About the old `products` table:** it is a demo electronics catalog (headphones, monitors,
keyboards…), not real estate data, so its rows were **not** migrated into `properties` — doing
so would have produced nonsensical real estate listings. The table, its routes and its
templates are left exactly as they were, unlinked from the main navigation but still fully
working (and still covered by `tests/test_crud.py`) alongside the property system.

---

## Real Estate backend (Phase 2)

Phase 2 added full property CRUD, validation, business rules and dashboard statistics as a
small JSON API (`property_queries.py` for every SQL statement, `property_validation.py` for
server-side validation and the listing-type/status business rules, both wired into `app.py`).
That API is still there, unchanged, at `/properties`, `/properties/stats`, `/properties/<id>`,
`/properties/add`, `/properties/edit/<id>` and `/properties/delete/<id>` — see
`tests/test_properties.py`.

---

## Real Estate frontend (Phase 3)

Phase 3 added a dedicated, server-rendered UI on top of that same backend — the JSON API above
is untouched, and every property page below calls straight into `property_queries.py` /
`property_validation.py` itself, so there is exactly one implementation of property CRUD.

| Page                | Route                        | Method       |
|----------------------|------------------------------|--------------|
| Dashboard            | `/dashboard`                 | `GET`        |
| Property Management  | `/properties/manage`         | `GET`        |
| Property Details     | `/properties/view/<id>`      | `GET`        |
| Create Property      | `/properties/new`            | `GET`,`POST` |
| Edit Property        | `/properties/<id>/edit`      | `GET`,`POST` |
| Delete Property      | `/properties/<id>/delete`    | `POST` only  |

The app is branded **REAL ESTATE** — the header wordmark, nav (`Dashboard` / `Properties` /
`Add Property`), page titles and copy all reflect that. The futuristic space/aurora visual
system itself (particles, aurora, floating orbs, mouse trail, cursor glow, 3D card tilt,
sparkles, sonar, glassmorphism) is unchanged; only the brand-specific wordmark effects were
replaced with a simpler, static glow.

---

## Validation

The server checks every submission before it reaches MySQL, for both products and properties:

- Products — name, price and description are all required (whitespace-only is rejected); name
  must be 120 characters or fewer; price must be a number, not negative, not `NaN` or
  `Infinity`, and within `DECIMAL(10,2)`.
- Properties — see `property_validation.py`: required fields, foreign keys checked against
  what actually exists, numeric ranges that match the DECIMAL columns, and the listing-type ↔
  status business rule (a "For Sale" property can't be "Rented"; a "For Rent" property can't
  be "Sold").

A missing or unknown id, an unknown URL, and a wrong HTTP method all land back on the
appropriate page with a message, inside the app's own design.

---

## Tests

```
python -m pytest -v
```

142 tests: 64 covering all four product CRUD operations, the statistics, validation, error
handling and the security properties (parameterised SQL, escaped output, POST-only delete); 20
covering the real estate database architecture (tables, keys, constraints, indexes, seed data
and relationships — `tests/test_real_estate_schema.py`); and 58 covering the property CRUD API,
validation, business rules, filtering, statistics and security (`tests/test_properties.py`).

The tests run against a **separate** `<DB_NAME>_test` database, so they can never touch the
real catalog.

---

## Project layout

```
app.py                    Flask application - routes, validation, MySQL access
property_queries.py       Every SQL statement for the properties table + reference lookups
property_validation.py    Server-side validation + business rules for a property submission
real_estate_db.py         Real estate schema (DDL) + demo data + idempotent seeding
seed.py                   Optional: top up an existing database with the demo product catalog
seed_real_estate.py       Optional: top up an existing database with the real estate demo data
templates/
  base.html               Shared shell: REAL ESTATE brand, nav, headings, toast region
  index.html / add.html / edit.html / _product_form.html   Legacy product pages (Phase 0)
  dashboard.html           Real Estate Dashboard - live portfolio statistics
  properties/
    index.html             Property Management - search, filters, property grid
    detail.html             Property Details
    add.html / edit.html    Create / Edit Property (share _property_form.html)
    _property_form.html     The shared form and its live preview
  _icons.html               Inline SVG icon set
static/
  style.css               The full visual system
  script.js               Part A - effect system, Part B - page behaviour
  favicon.svg
tests/                    pytest suite
```

---

## About the interface

The visual identity is a dark space / aurora / glassmorphism system in violet, cyan and
crimson. `static/script.js` drives it from a **single** shared pointer listener and a
**single** `requestAnimationFrame` loop, recycles its mouse-trail nodes instead of creating
new ones, pauses completely while the tab is hidden, and reduces its particle counts on
low-power devices.

The whole motion system respects `prefers-reduced-motion`: when the operating system asks for
reduced motion the animations stop, and the aurora, glass, gradients and branding remain.
