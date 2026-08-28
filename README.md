# REAL ESTATE MANAGEMENT SYSTEM

A full-stack property management platform built with **Flask**, **MySQL** and **Jinja2** —
properties, agents and inquiries/leads on one normalized relational schema, a live analytics
dashboard, and a hand-written cosmic/glassmorphism front end (vanilla CSS + JavaScript, no
front-end framework). Built incrementally across 8 phases; this document reflects the final,
QA'd state of the project.

---

## 1. Project Overview

REAL ESTATE started as a simple Product CRUD teaching exercise and was evolved, phase by
phase, into a real estate management system: a property portfolio with a searchable listing
grid, a photo gallery per property, an agent directory, a customer inquiry/lead pipeline, and
a dashboard with live, database-driven analytics. Every number on screen is a real aggregate
query — nothing shown in the app is hard coded.

The original product catalog (`/`, `/add`, `/edit/<id>`, `/delete/<id>`) is kept, unlinked
from the navigation, exactly as it was — see [§4 System Architecture](#4-system-architecture)
and [§20 Project Structure](#20-project-structure) for why it was archived-in-place rather
than deleted.

## 2. Main Features

- **Properties** — searchable/filterable listing grid, detail page with an image gallery,
  create/edit forms with live preview, soft business rules (e.g. a "For Sale" listing can't be
  "Rented").
- **Property Gallery** — up to 12 image URLs per property, reorderable, `http(s)`-only.
- **Agents** — directory with per-agent assigned-properties and received-inquiries views.
- **Inquiries / Leads** — a customer inquiry against a property, worked by staff through a
  `New → Contacted → Closed` status pipeline.
- **Dashboard & Analytics** — portfolio value, status/listing-type/property-type/location
  breakdowns, agent performance, recent activity — all live MySQL aggregates.
- **Search & filters** on Properties, Agents and Inquiries.
- The full cosmic visual system: space background, aurora, particles, constellation, floating
  orbs, mouse trail, cursor glow, mouse-proximity effects, 3D card tilt, sparkles, sonar,
  glassmorphism — frozen as-is for this phase.

## 3. System Architecture

Flask app with one process, one MySQL database, and a strict thin-controller pattern: every
route in `app.py` reads a form/query string, hands it to a `*_validation.py` module, then to a
`*_queries.py` module for the actual SQL, and renders a template. There is exactly one
implementation of each entity's CRUD logic in the whole app — routes never duplicate it.

```
Browser
  │  HTML forms / links
  ▼
app.py            Flask routes — thin controllers only
  │                     │
  ▼                     ▼
*_validation.py    *_queries.py   ──►  MySQL (InnoDB)
(pure Python,       (parameterised
 no DB access)       SQL, %s binds)
```

## 4. Technology Stack

| Layer          | Technology                                    |
|----------------|------------------------------------------------|
| Backend        | Python 3, Flask 3.1.1                          |
| Database       | MySQL (InnoDB), `mysql-connector-python` 26.7.0 |
| Config         | `python-dotenv` 1.1.1 (`.env`, never committed) |
| Templating     | Jinja2 (bundled with Flask), autoescaping on   |
| Front end      | Vanilla CSS + JavaScript — no frameworks       |
| Tests          | pytest (309 tests, against a separate test DB) |

## 5. Database Architecture

Six tables, InnoDB, created automatically on first run (`real_estate_db.py`):

| Table            | Purpose                                             |
|------------------|------------------------------------------------------|
| `property_types` | Reference list (Apartment, Villa, Office, …)          |
| `locations`      | Reference list (name + city)                          |
| `agents`         | Agent directory (unique email)                        |
| `properties`     | The listings themselves                               |
| `property_images`| Gallery photos for a property                         |
| `inquiries`      | Customer leads against a property                     |

Key constraints (all enforced in the schema, not just in application code):

- `properties.listing_type` and `properties.status` are native MySQL `ENUM` columns — an
  invalid value is rejected by the database itself.
- `properties.price` is `DECIMAL(14, 2)` with `CHECK (price >= 0)`; `area_sqm` is
  `DECIMAL(8, 2)` with `CHECK (area_sqm > 0)`. Neither is ever a `FLOAT`.
- `property_types.name` and `agents.email` are `UNIQUE`; `locations` has a composite
  `UNIQUE (name, city)`.
- Indexes on every foreign key (automatic in InnoDB) plus explicit indexes on
  `properties.status`, `listing_type`, `price`, `area_sqm` and `inquiries.status` for the
  dashboard's and the filters' aggregate queries.
- `created_at` / `updated_at` timestamps on `agents`, `properties` (with
  `ON UPDATE CURRENT_TIMESTAMP`), `property_images` and `inquiries`.
- The legacy `products` table (from the original CRUD exercise) is untouched and unrelated.

A separate `<DB_NAME>_test` database is created for the test suite, so tests never touch demo
or real data.

## 6. Entity Relationships

```
property_types  1───N  properties
locations       1───N  properties
agents          1───N  properties            (agent_id NULLable)
properties      1───N  property_images
properties      1───N  inquiries
```

- **`property → property_images`** — `ON DELETE CASCADE`: deleting a property removes its
  photos.
- **`property → inquiries`** — `ON DELETE CASCADE`: deleting a property removes the leads sent
  about it.
- **`agent → properties`** — `ON DELETE SET NULL`: deleting an agent never deletes or blocks
  on their properties; each one simply becomes unassigned and keeps working normally.

## 7. Main Routes

| Area       | Page routes (server-rendered HTML)                                                                                  |
|------------|------------------------------------------------------------------------------------------------------------------------|
| Dashboard  | `GET /dashboard`                                                                                                       |
| Properties | `GET /properties/manage` · `GET /properties/view/<id>` · `GET,POST /properties/new` · `GET,POST /properties/<id>/edit` · `POST /properties/<id>/delete` |
| Agents     | `GET /agents` · `GET /agents/<id>` · `GET,POST /agents/add` · `GET,POST /agents/edit/<id>` · `POST /agents/delete/<id>` |
| Inquiries  | `GET /inquiries` · `GET /inquiries/<id>` · `GET,POST /inquiries/add` · `GET,POST /inquiries/edit/<id>` · `POST /inquiries/delete/<id>` |

The **REAL ESTATE** wordmark always links to `/dashboard`.

A separate, JSON-only property API also exists at `/properties`, `/properties/stats`,
`/properties/<id>`, `/properties/add`, `/properties/edit/<id>`, `/properties/delete/<id>` —
built in an earlier phase and still fully tested (`tests/test_properties.py`), kept at its own
paths specifically so it can keep answering in pure JSON while the HTML pages above answer in
HTML (see the "PHASE 3" comment block in `app.py` for the full reasoning).

The legacy product catalog also still answers at `GET /`, `GET,POST /add`,
`GET,POST /edit/<id>`, `POST /delete/<id>` — not linked from the nav, but fully working and
covered by `tests/test_crud.py`.

Every unknown URL returns a friendly **404**; every wrong HTTP method (e.g. `GET` on a
POST-only delete route) returns a real **405**, both inside the app's own design rather than a
bare server error page.

## 8. Properties Management

`property_queries.py` / `property_validation.py`. Full CRUD plus:

- Search across title, description, location name and city (`?q=`), and filters for status,
  listing type, property type, location, price range and area range.
- Server-enforced business rule: a `For Sale` listing cannot be `Rented`; a `For Rent` listing
  cannot be `Sold`.
- Foreign keys (`property_type_id`, `location_id`, `agent_id`) are checked against what
  actually exists in the database before a save is accepted, not just cast to an int.

## 9. Property Gallery

Each property can carry up to 12 photo URLs (`property_images`, `sort_order`-ordered). A URL
is only ever accepted (and only ever rendered as an `<img src>`) if it parses as a plain
`http://` or `https://` link with a domain — this is what blocks `javascript:`, `data:` and
`vbscript:` links from ever being stored. The property detail page shows the full gallery with
keyboard-operable next/previous and thumbnail navigation; listing cards show the first
("primary") image.

## 10. Agents Management

`agent_queries.py` / `agent_validation.py`. Full CRUD, a unique-email rule (checked against
the database, excluding the agent's own row on edit), and a detail page listing every property
currently assigned to that agent plus every inquiry received on those properties. Deleting an
agent never deletes or blocks on their properties — see [§6](#6-entity-relationships).

## 11. Inquiries / Leads

`inquiry_queries.py` / `inquiry_validation.py`. A visitor sends an inquiry from a property's
detail page (always starts as `New`, regardless of anything forged in the form); staff work it
from the Inquiries page through `New → Contacted → Closed`. Filterable by status, property and
agent (via the property's assigned agent). Deleting a property cascades to its inquiries;
deleting an inquiry never touches the property.

## 12. Dashboard & Analytics

`analytics_queries.py`, rendered by `dashboard.html`. Every figure is a live MySQL aggregate,
recomputed on every request:

- Portfolio totals: property count, total value, average price, status breakdown.
- Charts: property status (donut), listing-type split (donut), properties by type (bar list),
  top locations (bar list), agent performance (table).
- Recent properties and recent inquiries panels.
- Every chart carries a text/table equivalent alongside the visual (a legend list or a real
  `<table>`) — no information is conveyed by color alone.

## 13. Security

- **SQL injection** — every statement uses `%s` parameter binding; no user-controlled string
  is ever concatenated or `.format()`-ted into SQL text.
- **XSS** — Jinja2 autoescaping is used everywhere; no `| safe` filter or `Markup()` call
  exists in the codebase.
- **Image URLs** — restricted to `http`/`https` with a domain (see [§9](#9-property-gallery)).
- **Destructive actions are POST-only** — every delete route rejects `GET` with a real `405`,
  never a silent success.
- **IDs** — path ids use Flask's `<int:id>` converter (a non-numeric id 404s before the route
  body runs); query-string and form ids are parsed with `int()` inside a `try/except` and
  simply dropped/rejected if invalid, never trusted as-is.
- **Enums** — `listing_type`, property `status` and inquiry `status` are checked against a
  fixed allow-list in both the validation layer and the database's own `ENUM` columns.
- **Error handling** — every database error is logged server-side
  (`app.logger.error(...)`) and only ever shown to the visitor as a generic message; no raw
  exception text, SQL, or stack trace ever reaches a flashed message or JSON response.
- **Secrets** — the database password and Flask secret key are read from `.env` via
  `os.environ.get(...)`; `.env` is excluded by `.gitignore` and was never committed. Set a real
  `SECRET_KEY` in `.env` before showing this outside your own machine — the hardcoded fallback
  is a development-only default.
- **Debug mode** — `python app.py` no longer hardcodes `debug=True` (a Phase 8 fix): the
  interactive Werkzeug debugger, which can leak stack traces and expose remote code execution
  through its console, is now off unless `FLASK_DEBUG=1` is explicitly set.

## 14. Validation

Every submission is validated server-side before it reaches MySQL — client-side HTML5
attributes are a convenience, not the actual guard:

- **Properties** — required fields, foreign keys checked against what exists, numeric fields
  parsed and range-checked against their `DECIMAL`/`TINYINT` column limits, the
  listing-type/status business rule, and up to 12 `http(s)` image URLs.
- **Agents** — name/email/phone required and length-capped, a pragmatic email-shape regex, and
  a database-checked unique email.
- **Inquiries** — name/email/phone/message required and length-capped, the same email check,
  the property id checked against real properties, and status forced to `New` on creation and
  restricted to the three known values on edit.
- **Legacy products** — name/price/description required, price numeric/finite/non-negative and
  within `DECIMAL(10,2)`.

## 15. Installation

```
pip install -r requirements.txt
```

To run the test suite you additionally need `pytest` (not a runtime dependency, so it isn't in
`requirements.txt`):

```
pip install pytest
```

## 16. Environment Variables

Create a `.env` file next to `app.py` (never commit this file):

```
SECRET_KEY=<a long random string of your own>
DB_HOST=<your MySQL host, e.g. localhost>
DB_PORT=<your MySQL port, e.g. 3306>
DB_USER=<your MySQL user>
DB_PASSWORD=<your MySQL password>
DB_NAME=<your database name>
```

`FLASK_DEBUG=1` optionally re-enables Flask's interactive debugger for `python app.py` — leave
it unset for anything other than local development on your own machine.

## 17. Database Setup

Nothing has to be created by hand. On startup, `app.py` calls `init_db()`, which:

1. Creates the database (`CREATE DATABASE IF NOT EXISTS`) and the legacy `products` table.
2. Calls `real_estate_db.init_real_estate()`, which creates all six real-estate tables
   (`CREATE TABLE IF NOT EXISTS`) and seeds baseline demo data.

Every seed step is idempotent by construction — running it any number of times never
duplicates a row:

- Reference data (`property_types`, `locations`, `agents`) is inserted per-row, only for names
  not already present.
- Demo properties (with their images and inquiries) are inserted only while `properties` is
  still completely empty.
- A one-time backfill (`backfill_demo_property_images`) fixes any demo property whose gallery
  is still empty, without ever touching a property that already has real images.

To top up an existing database that already has rows, without starting the app:

```
python seed.py               # legacy product catalog
python seed_real_estate.py   # real estate reference/demo data
```

## 18. Running the Application

```
python app.py          # development server on http://127.0.0.1:5000
flask run               # same app, standard Flask launcher
```

## 19. Running Tests

```
python -m pytest -v
```

309 tests, run against a separate `<DB_NAME>_test` database so they never touch real or demo
data:

| File                              | Covers                                                        |
|------------------------------------|----------------------------------------------------------------|
| `test_crud.py` (64)                | Legacy product CRUD, validation, security, error handling      |
| `test_real_estate_schema.py` (20)  | Schema: tables, keys, constraints, indexes, seed idempotency    |
| `test_properties.py` (58)          | Property JSON API: CRUD, filters, stats, validation, security  |
| `test_property_images.py` (34)     | Gallery: image CRUD, ordering, URL validation, cascades         |
| `test_agents.py` (41)              | Agent CRUD, uniqueness, `SET NULL` on delete, 404/405           |
| `test_inquiries.py` (65)           | Inquiry CRUD, status pipeline, filters, cascades, 404/405       |
| `test_dashboard_analytics.py` (27) | Dashboard aggregates against direct MySQL counts                |

## 20. Project Structure

```
app.py                      Flask app - every route (thin controllers only)
property_queries.py         All SQL for properties + reference lookups
property_validation.py      Server-side validation + business rules for properties
agent_queries.py            All SQL for agents
agent_validation.py         Server-side validation for agents
inquiry_queries.py          All SQL for inquiries
inquiry_validation.py       Server-side validation for inquiries
analytics_queries.py        Dashboard aggregate queries + chart-shaping helpers
real_estate_db.py           Real estate schema (DDL) + demo data + idempotent seeding
seed.py                     Optional: top up the legacy product catalog
seed_real_estate.py         Optional: top up the real estate reference/demo data
requirements.txt            Runtime dependencies
.env                        Local secrets (git-ignored, never committed)

templates/
  base.html                 Shared shell: REAL ESTATE brand, nav, toasts
  index.html, add.html,
  edit.html, _product_form.html   Legacy product pages (unlinked, still tested)
  dashboard.html             Dashboard & Analytics
  properties/                Property Management, Details, Add, Edit (+ shared form)
  agents/                    Agent list, Details, Add, Edit (+ shared form)
  inquiries/                 Inquiries list, Details, Add, Edit (+ shared form)
  _icons.html                Inline SVG icon set

static/
  style.css                 The full visual system (cosmic/glassmorphism, responsive)
  script.js                 Effect system (single pointer listener, single rAF loop)
                             + page behaviour (toasts, dialogs, live preview, filters)
  favicon.svg

tests/                       pytest suite (see §19) + conftest.py fixtures
_archive/                    Pre-real-estate project files, excluded from git
```

---

Built and hardened across 8 phases. This phase (8) audited, cleaned and documented the
project for training/demo without changing the visual identity or adding new features.
