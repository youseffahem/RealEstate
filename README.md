<div align="center">

# 🏙️ REAL ESTATE

**A full-stack property management platform for listings, agents and customer leads — built on Flask, MySQL and a normalized relational schema, with a live analytics dashboard.**

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.1.1-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![MySQL](https://img.shields.io/badge/MySQL-InnoDB-4479A1?logo=mysql&logoColor=white)](https://www.mysql.com/)
[![Jinja2](https://img.shields.io/badge/Jinja2-server--rendered-B41717?logo=jinja&logoColor=white)](https://jinja.palletsprojects.com/)
[![Tests](https://img.shields.io/badge/tests-274%20passing-2ea44f?logo=pytest&logoColor=white)](#-testing)
[![Dependencies](https://img.shields.io/badge/runtime%20deps-3-blue)](#-tech-stack)

</div>

---

## 📑 Table of Contents

| | | |
|---|---|---|
| [Overview](#-overview) | [Highlights](#-highlights) | [Features](#-features) |
| [Architecture](#-architecture) | [Tech Stack](#-tech-stack) | [Database](#-database) |
| [Routes](#-routes) | [Getting Started](#-getting-started) | [Testing](#-testing) |
| [Security](#-security) | [Accessibility & Responsive Design](#-accessibility--responsive-design) | [Theme System](#-theme-system) |
| [Project Structure](#-project-structure) | [Future Improvements](#-future-improvements) | [Contributors](#-contributors) |

---

## 🎯 Overview

**REAL ESTATE** is a server-rendered property management system for a real estate agency. It replaces the spreadsheet-and-inbox workflow that small agencies typically run on, and puts the three things that actually drive the business — **what you're selling, who's selling it, and who's asking about it** — into one normalized relational database with a single source of truth for each.

### The problem it solves

A property agency juggles three intertwined datasets that are painful to keep consistent by hand:

1. **The portfolio** — listings with prices, areas, types, locations, statuses and photo galleries, all of which change constantly.
2. **The team** — which agent is responsible for which listing, and how each agent is performing.
3. **The pipeline** — inbound customer inquiries against specific properties, which must be worked from first contact to close without leads going missing.

Kept in separate files, these drift apart: a sold property still shows as available, an inquiry has no owner, a deleted agent takes their listings down with them.

### How this project solves it

The three datasets live in **one InnoDB schema with real foreign keys**, so consistency is enforced by the database rather than by convention:

- A property **cannot** reference a property type, location or agent that does not exist.
- Deleting a property **cascades** to its images and its inquiries — no orphan rows.
- Deleting an agent **never** deletes or blocks their listings; each one simply becomes unassigned (`ON DELETE SET NULL`).
- Prices are `DECIMAL`, never `FLOAT`. Statuses and listing types are native MySQL `ENUM`s — an invalid value is rejected by the database itself, not just by the app.

On top of that schema sits a **live analytics dashboard**: every figure on it is a real aggregate query recomputed on each request. Nothing displayed anywhere in the application is hard-coded.

---

## ✨ Highlights

| | |
|---|---|
| 🗄️ **Database-enforced integrity** | `ENUM` columns, `CHECK` constraints, `DECIMAL` money, `UNIQUE` keys, and explicit `ON DELETE` policies per relationship — correctness is guaranteed below the application layer |
| 🧱 **Strict three-layer separation** | Routes are thin controllers only: every route validates through a `*_validation` module, queries through a `*_queries` module, and renders. Exactly one implementation of each entity's logic exists in the codebase |
| 📊 **Live analytics dashboard** | 12 portfolio KPIs, 5 charts and an agent-performance table — all computed by aggregate SQL (`SUM`/`AVG`/`COUNT`/`GROUP BY`), never cached or hard-coded |
| 🎨 **Zero front-end frameworks** | ~4,300 lines of hand-written CSS and ~1,900 lines of vanilla JavaScript. No React, no Bootstrap, no Tailwind, no charting library — the dashboard's donut is a CSS `conic-gradient` and its bars are styled elements |
| 🌗 **Persistent light/dark theme** | Full dual-palette design token system with a pre-paint script that eliminates the flash-of-wrong-theme |
| ♿ **Accessibility by construction** | Skip link, semantic landmarks, `aria-current`, `aria-pressed`, keyboard-operable gallery, text/table equivalents for every chart, and full `prefers-reduced-motion` support |
| 🧪 **274 passing tests** | Including DDL introspection tests that assert the schema itself — column types, constraints, indexes and cascade behaviour — against a live MySQL server |
| 🔐 **Parameterized SQL everywhere** | `%s` binding on every statement; no user-controlled string is ever concatenated into SQL text |

---

## 🚀 Features

### 🏠 Properties

The core portfolio module — full CRUD with a searchable, filterable listing grid.

- **Search** across property title, description, location name and city in a single query (`?q=`).
- **Filters** for status, listing type, property type, location, price range and area range — all composable, all bound as SQL parameters. Malformed filter values are silently dropped rather than raising, so a hand-edited query string never produces a 500.
- **Detail page** with the full image gallery, the property's specifications, its assigned agent, and a live, database-backed count of the inquiries received on it.
- **Create / edit forms** with a live preview and a shared partial (`_property_form.html`) used by both, so add and edit can never drift apart.
- **Server-enforced business rule** — a `For Sale` listing cannot be marked `Rented`; a `For Rent` listing cannot be marked `Sold`.
- **Foreign keys are verified against the database** before a save is accepted, not merely cast to an integer.

### 🖼️ Image Gallery

Each property carries up to **12 images**, stored in a dedicated `property_images` table and rendered in `sort_order`.

- **Two ways to add an image:** paste an external URL, or upload a file from your computer (`multipart/form-data`, `<input type="file" name="image_files" multiple>`).
- **Uploads** are constrained to `jpg`, `jpeg`, `png` and `webp`, passed through Werkzeug's `secure_filename`, then stored under a freshly generated **UUID4 filename** — the original filename never reaches the filesystem, so it cannot be used for traversal or collision.
- **External URLs** are only accepted — and only ever rendered into an `<img src>` — if they parse as a plain `http://` or `https://` link with a real domain. This is what blocks `javascript:`, `data:` and `vbscript:` URLs from ever being stored.
- **Gallery navigation** on the detail page: main image, thumbnail strip, previous/next controls, and **arrow-key support** once a gallery control has focus.
- Listing cards show the property's first ("primary") image, fetched in a single batched query rather than one query per card.

### 👔 Agents

A directory of the agency's team, with a per-agent workload view.

- Full CRUD with **database-checked unique email** — on edit, the agent's own row is excluded from the uniqueness check so re-saving without changing the email is not falsely rejected.
- **Agent detail page** listing every property currently assigned to that agent, plus every inquiry received on those properties.
- Agents carry an optional **photo** and a **gender** field, and the directory groups the team accordingly.
- The directory carries each agent's **property counts**, aggregated in the same query that lists them rather than one follow-up query per agent.
- **Search** across agent name, email and phone (`?q=`).
- Deleting an agent is always safe: their properties survive and become unassigned.

### 📬 Inquiries (Lead Pipeline)

Customer leads raised against a specific property, worked through a controlled status pipeline.

- A visitor sends an inquiry from a property's detail page. It **always starts as `New`**, regardless of what a forged form submits.
- Staff advance it through **`New` → `Contacted` → `Closed`** from the Inquiries module.
- **Filters** by status, property and agent — the agent filter resolves through the property's assigned agent, since an inquiry has no agent column of its own.
- **Search** across the customer's name, email and phone, the property title, and the message body (`?q=`).
- Deleting a property cascades to its inquiries; deleting an inquiry never touches the property.

### 📈 Dashboard & Analytics

The application's entry point (`/` redirects straight to `/dashboard`). Every value is a live MySQL aggregate.

**KPI tiles** — Total properties · Available · Reserved · Sold · Rented · Total portfolio value · Average property price · Total agents · Total inquiries · New inquiries · Contacted inquiries · Closed inquiries.

**Visualizations** — all rendered with CSS and HTML; **no charting library is used anywhere in the project**:

| Chart | Rendering technique | Data source |
|---|---|---|
| Properties by Status | Donut — CSS `conic-gradient` | `get_dashboard_overview()` → `build_property_status_chart()` |
| Properties by Listing Type | Stacked split bar — CSS widths | `get_listing_type_stats()` → `build_listing_type_chart()` |
| Properties by Type | Horizontal bars — CSS widths | `get_property_type_stats()` → `build_property_type_chart()` |
| Top Locations | Horizontal bars — CSS widths | `get_location_stats()` → `build_location_chart()` |
| Inquiries by Status | Stacked split bar — CSS widths | `get_dashboard_overview()` → `build_inquiry_status_chart()` |
| Agent Performance | Semantic `<table>` | `get_agent_performance()` |

The Inquiry Analytics section additionally reports inquiries received today and an **inquiry closure rate** (closed ÷ total) — labelled in the UI itself as a closure rate rather than a sales conversion rate, because the schema holds no link between an inquiry and a completed sale.

**Activity panels** — Recent Properties and Recent Inquiries, plus a Quick Actions block.

Every chart is paired with a **text or table equivalent** — a legend list or a real `<table>` — so no information is conveyed by colour alone. If the database is unreachable, the dashboard still renders using a zeroed fallback context rather than erroring out.

---

## 🏗️ Architecture

The application follows a strict **thin-controller** pattern. A route reads the request, delegates validation, delegates SQL, and renders. It contains no business rules and no SQL of its own.

```
┌─────────────────────────────────────────────────────────────────┐
│  BROWSER                                                        │
│  Server-rendered HTML · progressive forms · no AJAX, no SPA     │
│  static/style.css  ·  static/script.js  (vanilla, self-hosted)  │
└───────────────────────────┬─────────────────────────────────────┘
                            │  HTTP  (GET links / POST forms)
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  app.py — FLASK ROUTING LAYER (thin controllers)                │
│  • parses request.form / request.args / request.files           │
│  • flashes messages, redirects, renders Jinja2 templates        │
│  • error handlers (404 / 405) · money template filter           │
│  • no SQL, no business rules                                    │
└──────────────┬──────────────────────────────┬───────────────────┘
               │                              │
               ▼                              ▼
┌──────────────────────────────┐  ┌───────────────────────────────┐
│  VALIDATION LAYER            │  │  QUERY LAYER                  │
│  property_validation.py      │  │  property_queries.py          │
│  agent_validation.py         │  │  agent_queries.py             │
│  inquiry_validation.py       │  │  inquiry_queries.py           │
│                              │  │  analytics_queries.py         │
│  Pure Python. Field rules,   │  │                               │
│  length caps, numeric ranges │  │  Every SQL statement lives    │
│  enum allow-lists, business  │  │  here. 100% `%s` parameter    │
│  rules. Receives the set of  │  │  binding — values are never   │
│  valid FK ids; performs no   │  │  interpolated into SQL text.  │
│  database access itself.     │  │                               │
└──────────────────────────────┘  └───────────────┬───────────────┘
                                                  │
                                                  ▼
                                  ┌───────────────────────────────┐
                                  │  MySQL (InnoDB)               │
                                  │  real_estate_db.py owns the   │
                                  │  DDL, startup migrations and  │
                                  │  idempotent seeding.          │
                                  │  ENUM · CHECK · DECIMAL ·     │
                                  │  UNIQUE · FK ON DELETE rules  │
                                  └───────────────────────────────┘
```

### Request lifecycle (a property update)

```
POST /properties/<id>/edit
  │
  ├─▶ app.py                    reads request.form + request.files
  ├─▶ property_queries          get_valid_ids()  — the real FK ids in the DB
  ├─▶ property_validation       validate_property_payload(form, valid_ids)
  │                             validate_image_urls(urls)
  │        └── errors? ─────────▶ re-render the form with what the user typed
  ├─▶ property_queries          update_property()  +  set_property_images()
  └─▶ redirect ──▶ flash("success") ──▶ GET /properties/view/<id>
```

Because validation is pure Python that receives the valid foreign-key ids as an argument, it is **directly unit-testable without a database** while still being able to reject ids that don't exist.

### Resilience

Every route wraps its database work in `try/except mysql.connector.Error`. On failure the exception is logged server-side via `app.logger.error(...)` and the visitor sees a generic flashed message — pages still render, with empty dropdowns or zeroed statistics, rather than returning a stack trace. Startup follows the same rule: `bootstrap()` catches a failed `init_db()` so a briefly unreachable database cannot prevent the application from starting.

---

## 🛠️ Tech Stack

| Layer | Technology | Notes |
|---|---|---|
| **Language** | Python 3.11 | Verified on 3.11.9 |
| **Web framework** | Flask 3.1.1 | Single process, blueprint-free, server-rendered |
| **Templating** | Jinja2 | Bundled with Flask; autoescaping enabled |
| **Database** | MySQL — InnoDB engine | Foreign keys, `ENUM`, `CHECK`, `DECIMAL` |
| **DB driver** | `mysql-connector-python` 26.7.0 | Official connector; `%s` parameter binding |
| **Configuration** | `python-dotenv` 1.1.1 | `.env`, never committed |
| **File uploads** | `werkzeug.utils.secure_filename` + `uuid4` | Bundled with Flask |
| **Front end** | Vanilla CSS + vanilla JavaScript | No framework, no build step, no bundler |
| **Typography** | Inter, via Google Fonts | The project's only external front-end dependency |
| **Testing** | pytest 8.4.1 | Runs against an isolated test database |

**Runtime dependencies: three.** The entire `requirements.txt` is Flask, the MySQL connector and dotenv. There is no build pipeline, no `node_modules`, and no asset compilation step — clone, install three packages, run.

---

## 🗃️ Database

Six InnoDB tables, created automatically on first run by `real_estate_db.py`.

### Entity relationship diagram

```
   property_types                    locations                    agents
  ┌───────────────┐              ┌───────────────┐          ┌──────────────┐
  │ id       PK   │              │ id       PK   │          │ id       PK  │
  │ name  UNIQUE  │              │ name          │          │ name         │
  └───────┬───────┘              │ city    IDX   │          │ email UNIQUE │
          │                      │ UQ(name,city) │          │ phone        │
          │                      └───────┬───────┘          │ photo_url    │
          │ 1                            │ 1                │ gender  ENUM │
          │                              │                  │ created_at   │
          │                              │                  └──────┬───────┘
          │  N                        N  │                       1 │
          └──────────────┐  ┌────────────┘      ┌──────────────────┘
                         ▼  ▼                   │ N
                  ┌──────────────────────────────────────────┐
                  │             properties                   │
                  │  id                PK                    │
                  │  title             VARCHAR(180)          │
                  │  description       TEXT                  │
                  │  property_type_id  FK → RESTRICT         │
                  │  location_id       FK → RESTRICT         │
                  │  agent_id          FK → SET NULL  (NULL) │
                  │  listing_type      ENUM                  │
                  │  price             DECIMAL(14,2) CHECK>=0│
                  │  area_sqm          DECIMAL(8,2)  CHECK >0│
                  │  bedrooms          TINYINT UNSIGNED      │
                  │  bathrooms         TINYINT UNSIGNED      │
                  │  status            ENUM                  │
                  │  created_at / updated_at   TIMESTAMP     │
                  └───────┬──────────────────────────┬───────┘
                        1 │                        1 │
                          │ N                        │ N
              ┌───────────▼─────────┐    ┌───────────▼──────────┐
              │  property_images    │    │      inquiries       │
              │  id           PK    │    │  id            PK    │
              │  property_id  FK ⇊  │    │  property_id   FK ⇊  │
              │  image_url          │    │  name / email / phone│
              │  sort_order         │    │  message       TEXT  │
              │  created_at         │    │  status  ENUM  IDX   │
              └─────────────────────┘    │  created_at          │
                                         └──────────────────────┘
                       ⇊ = ON DELETE CASCADE
```

### Tables

| Table | Purpose |
|---|---|
| `property_types` | Reference list — Apartment, Villa, Office, … |
| `locations` | Reference list — area name + city |
| `agents` | The agency's team directory |
| `properties` | The listings themselves |
| `property_images` | Ordered gallery photos for a property |
| `inquiries` | Customer leads raised against a property |

### Relationships and delete behaviour

| Relationship | Cardinality | On delete of the parent |
|---|---|---|
| `property_types` → `properties` | 1 : N | `RESTRICT` — a type in use cannot be deleted |
| `locations` → `properties` | 1 : N | `RESTRICT` — a location in use cannot be deleted |
| `agents` → `properties` | 1 : N (nullable) | `SET NULL` — listings survive, unassigned |
| `properties` → `property_images` | 1 : N | `CASCADE` — photos are removed with the listing |
| `properties` → `inquiries` | 1 : N | `CASCADE` — leads are removed with the listing |

All foreign keys use `ON UPDATE CASCADE`.

### Controlled values

| Column | Type | Allowed values |
|---|---|---|
| `properties.listing_type` | `ENUM` | `For Sale`, `For Rent` |
| `properties.status` | `ENUM` | `Available`, `Reserved`, `Sold`, `Rented` |
| `inquiries.status` | `ENUM` | `New`, `Contacted`, `Closed` |
| `agents.gender` | `ENUM` | `Male`, `Female` |

These are enforced **twice** — by an allow-list in the validation layer, and by the column type in MySQL. A row inserted outside the application is rejected just the same.

### Integrity constraints and indexes

- **`CHECK` constraints** — `price >= 0` and `area_sqm > 0`.
- **`UNIQUE` constraints** — `property_types.name`, `agents.email`, and a composite `UNIQUE (name, city)` on `locations`.
- **Money is `DECIMAL(14,2)`**, never `FLOAT` — no binary rounding error in portfolio totals.
- **Explicit indexes** for the dashboard aggregates and the listing filters: `properties.status`, `properties.listing_type`, `properties.price`, `properties.area_sqm`, `locations.city`, `inquiries.status` — plus InnoDB's automatic indexes on every foreign key.
- **Timestamps** — `created_at` on `agents`, `properties`, `property_images` and `inquiries`; `properties.updated_at` carries `ON UPDATE CURRENT_TIMESTAMP`.

### Startup migrations

`init_real_estate()` runs two idempotent migrations on every start, each guarded by an `information_schema` column check so the `ALTER` never runs twice:

1. **`agents.photo_url`** — added as `VARCHAR(500) NULL`.
2. **`agents.gender`** — added nullable first so existing rows are never rejected by the `ALTER`, backfilled to a deterministic default, then locked down to `NOT NULL`. No agent row is ever deleted or recreated.

`init_db()` additionally issues a one-time `DROP TABLE IF EXISTS products`, removing the legacy table from the CRUD exercise this project originally grew out of. That functionality — its routes, templates, table and tests — has been **fully removed**; the application is Real Estate only.

---

## 🧭 Routes

### Server-rendered pages (HTML)

| Area | Routes |
|---|---|
| **Entry point** | `GET /` → redirects to `/dashboard` |
| **Dashboard** | `GET /dashboard` |
| **Properties** | `GET /properties/manage` · `GET /properties/view/<id>` · `GET,POST /properties/new` · `GET,POST /properties/<id>/edit` · `POST /properties/<id>/delete` |
| **Agents** | `GET /agents` · `GET /agents/<id>` · `GET,POST /agents/add` · `GET,POST /agents/edit/<id>` · `POST /agents/delete/<id>` |
| **Inquiries** | `GET /inquiries` · `GET /inquiries/<id>` · `GET,POST /inquiries/add` · `GET,POST /inquiries/edit/<id>` · `POST /inquiries/delete/<id>` |
| **Uploads** | `GET /uploads/<filename>` — serves user-uploaded property images |

### JSON API (properties)

A pure-JSON property API lives at its own paths, so it can keep answering in `application/json` while the pages above answer in HTML:

| Method | Route | Returns |
|---|---|---|
| `GET` | `/properties` | `{ count, properties[] }` — honours every listing filter |
| `GET` | `/properties/stats` | Aggregate property statistics |
| `GET` | `/properties/<id>` | `{ property }`, or `404` `{ error }` |
| `GET,POST` | `/properties/add` | Reference data / creates a property |
| `GET,POST` | `/properties/edit/<id>` | Current values / updates a property |
| `POST` | `/properties/delete/<id>` | Deletes a property |

### Query-string filters

| Module | Supported parameters |
|---|---|
| **Properties** | `q`, `status`, `listing_type`, `property_type_id`, `location_id`, `min_price`, `max_price`, `min_area`, `max_area` |
| **Agents** | `q` |
| **Inquiries** | `q`, `status`, `property_id`, `agent_id` |

### Error handling

Custom `404` and `405` handlers keep failures inside the application's own design instead of on Werkzeug's default error page. Both branch on `_wants_json()` — true for any path under `/properties`, which is where the JSON API lives:

| Situation | Response |
|---|---|
| Any error under `/properties` | `404` / `405` **JSON** — `{ "error": … }`, matching the API's content type |
| `GET` on the Agents or Inquiries POST-only delete route | A real **`405`** status, redirecting back to that module's own page |
| Any other unknown URL or wrong method | A flashed message and a redirect to the Dashboard |

In every case the wrong method is rejected by Flask's routing **before the view function runs** — the handler only decides how the rejection is presented, so a delete can never be triggered by a `GET`.

---

## ⚙️ Getting Started

### Prerequisites

- **Python 3.11+**
- **A running MySQL server** — you need credentials for a user that can `CREATE DATABASE`

### 1 — Clone and install

```bash
git clone <repository-url>
cd RealEstate

python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 2 — Configure environment variables

Create a `.env` file next to `app.py`. **This file is git-ignored and must never be committed.**

```ini
# Flask
SECRET_KEY=<a long random string of your own>

# MySQL database connection
DB_HOST=localhost
DB_PORT=3306
DB_USER=<your MySQL user>
DB_PASSWORD=<your MySQL password>
DB_NAME=<the database name to use>
```

| Variable | Required | Purpose |
|---|---|---|
| `SECRET_KEY` | **Yes, in any shared environment** | Signs Flask session cookies. A development-only fallback exists so the app can boot without it — set a real value before running this anywhere but your own machine |
| `DB_HOST` | Recommended | MySQL host |
| `DB_PORT` | Recommended | MySQL port |
| `DB_USER` | **Yes** | MySQL user |
| `DB_PASSWORD` | **Yes** | MySQL password |
| `DB_NAME` | **Yes** | Database to create/use. A `<DB_NAME>_test` database is derived from this for the test suite |
| `FLASK_DEBUG` | No | Set to `1` to enable Werkzeug's interactive debugger for `python app.py`. **Leave unset** outside local development |

> No secret values are stored anywhere in the repository — every credential is read at runtime with `os.environ.get(...)`.

### 3 — Initialize the database

**Nothing needs to be created by hand.** Both `python app.py` and `flask run` import the module, which calls `init_db()` at import time. That single call:

1. Connects without a database and runs `CREATE DATABASE IF NOT EXISTS <DB_NAME>`.
2. Drops the legacy `products` table if an older database still has one.
3. Calls `real_estate_db.init_real_estate()`, which creates all six tables with `CREATE TABLE IF NOT EXISTS`, applies the `photo_url` / `gender` migrations, and seeds baseline demo data.

**Every seeding step is idempotent by construction** — running it any number of times never duplicates a row:

- Reference data (`property_types`, `locations`, `agents`) is inserted per row, and only for names not already present.
- Demo properties, with their images and inquiries, are inserted only while the `properties` table is still completely empty.
- `backfill_demo_property_images()` repairs any demo property whose gallery is empty, and never touches a property that already has its own images.

> The **seeded demo galleries reference external `https://` image URLs** (Unsplash), so demo photos need an internet connection to display. Images you upload yourself are stored locally under `static/uploads/` and have no such dependency.

To top up an existing database without starting the app:

```bash
python seed_real_estate.py
```

### 4 — Run the application

```bash
python app.py     # http://127.0.0.1:5000  (binds 0.0.0.0:5000)
```

or with the standard Flask launcher:

```bash
flask run                # http://127.0.0.1:5000
flask run --debug        # with auto-reload, for local development
```

The application opens directly on the **Dashboard**.

---

## 🧪 Testing

```bash
pip install pytest        # not a runtime dependency, so not in requirements.txt
python -m pytest -v
```

### Current status

```
============================ 274 passed in 19.19s =============================
```

**274 tests, 0 failures, 0 skipped** — verified against a live MySQL server.

| Test file | Tests | Coverage |
|---|--:|---|
| `test_agents.py` | 66 | Agent CRUD, unique-email enforcement, `SET NULL` on delete, detail view, 404/405 handling |
| `test_inquiries.py` | 65 | Inquiry CRUD, the `New → Contacted → Closed` pipeline, filters, cascade deletes, 404/405 |
| `test_properties.py` | 58 | Property JSON API — CRUD, filters, stats, validation rejection, security probes |
| `test_property_images.py` | 35 | Gallery CRUD, ordering, URL scheme validation, seeding and backfill behaviour, cascades |
| `test_dashboard_analytics.py` | 27 | Every dashboard aggregate cross-checked against direct MySQL counts |
| `test_real_estate_schema.py` | 23 | DDL introspection — tables, keys, `ENUM` domains, `DECIMAL` typing, `CHECK` rejection, indexes, seed idempotency |
| **Total** | **274** | |

### What makes the suite unusual

`test_real_estate_schema.py` asserts the **database schema itself** rather than the application's behaviour. It reads `information_schema` to verify that `price` is `DECIMAL` and not `FLOAT`, that the `status` column accepts exactly four values and no others, that the expected search indexes exist — and it proves the constraints by **attempting invalid writes directly against MySQL** and asserting they are rejected. Those tests would still fail if someone loosened the schema while leaving every Python validation rule intact.

> **Note:** the suite requires a reachable MySQL server. It runs against a separate `<DB_NAME>_test` database, so it never touches your development or demo data.

---

## 🔐 Security

Every item below is implemented in the codebase today.

| Threat | Mitigation |
|---|---|
| **SQL injection** | Every statement uses `%s` parameter binding. No user-controlled string is ever concatenated, `%`-formatted or `.format()`-ted into SQL text. Dynamic `WHERE` clauses are assembled from a fixed set of literal fragments while their values stay bound |
| **Cross-site scripting (XSS)** | Jinja2 autoescaping throughout. **The codebase contains no `safe` filter and no `Markup()` call anywhere** — there is no escape hatch to misuse |
| **Malicious image URLs** | Accepted only if they parse as `http`/`https` with a real domain, blocking `javascript:`, `data:` and `vbscript:` payloads at the validation layer, before storage |
| **Malicious uploads** | Extension allow-list (`jpg`, `jpeg`, `png`, `webp`), `secure_filename()`, and a generated UUID4 filename — the user's filename never reaches the filesystem |
| **Destructive requests via `GET`** | Every delete route is declared `methods=["POST"]`, so Flask rejects a `GET` at the routing layer before the view function runs — never a silent success. The `405` handler then answers with JSON, a real `405`, or a flashed redirect depending on the module ([details](#error-handling)) |
| **Parameter tampering on ids** | Path ids use Flask's `<int:id>` converter, so a non-numeric id 404s before the view function runs. Query-string and form ids are parsed inside `try/except` and dropped or rejected if invalid |
| **Invalid enum values** | Checked against a fixed allow-list in the validation layer **and** by the `ENUM` column in MySQL |
| **Forged status escalation** | An inquiry is forced to `New` on creation regardless of what the form submits; on edit, status is restricted to the three known values |
| **Information disclosure** | Every database error is logged server-side with `app.logger.error(...)` and shown to the visitor only as a generic message. No raw exception text, SQL fragment or stack trace ever reaches a flashed message or a JSON response |
| **Secret exposure** | Credentials are read from `.env` via `os.environ.get(...)`. `.env` is git-ignored and has never been committed |
| **Debugger exposure** | `python app.py` does **not** hardcode `debug=True`. Werkzeug's interactive debugger — which can leak stack traces and expose a remote code-execution console — is opt-in via `FLASK_DEBUG=1` and off by default |

### Server-side validation

Client-side HTML5 attributes are treated as a convenience, never as the guard. Every submission is re-validated in Python before it reaches MySQL:

- **Properties** — required fields; foreign keys checked against ids that actually exist; numeric fields parsed and range-checked against their real column limits (title ≤ 180 chars, description ≤ 4,000, price < 10¹², area < 10⁶, bedrooms/bathrooms ≤ 255); the listing-type ↔ status business rule; up to 12 `http(s)` image URLs of ≤ 500 characters each.
- **Agents** — name (≤ 120), email (≤ 160), phone (6–30) required; a pragmatic email-shape regex; a database-checked unique email that excludes the agent's own row on edit; gender restricted to the `ENUM` domain.
- **Inquiries** — name, email, phone and message (≤ 2,000) required and length-capped; the same email check; the property id checked against real properties; an explicit dangerous-scheme scan for `javascript:`, `data:` and `vbscript:` in submitted text; status forced to `New` on creation.

### Known limitations

Stated honestly, since this is a portfolio project rather than a deployed product:

- **There is no authentication or authorization layer.** Every route is public — the application assumes a trusted internal network or a single operator.
- **There is no CSRF protection** on the POST forms.
- **No upload size limit** (`MAX_CONTENT_LENGTH`) is configured.
- The Flask development server is not a production WSGI server.

---

## ♿ Accessibility & Responsive Design

### Accessibility

Implemented in the actual markup, CSS and JavaScript:

- **Skip link** — a "Skip to main content" link is the first focusable element on every page, targeting `#main-content`.
- **Semantic landmarks** — `<main>`, `<nav aria-label="Main">`, real heading hierarchy, and `lang="en"` on the document.
- **Current-page signalling** — `aria-current="page"` on the active navigation link, not colour alone.
- **Charts are never colour-only** — every chart is paired with a legend list or a real `<table>` carrying the same labels, counts and percentages. Each chart is a `role="img"` element whose `aria-label` spells out its full data ("Properties by status: Available 12, Reserved 3, …"); the decorative colour fills inside carry `aria-hidden="true"`.
- **Keyboard operation** — the property gallery responds to `ArrowLeft` / `ArrowRight`; dialogs and the search input close on `Escape` (handled explicitly so the closing animation still plays).
- **Labelled controls** — `<label for>` associations on form fields, and `aria-label` on icon-only buttons such as the theme toggle and the brand link.
- **Toggle state** — the theme button reports `aria-pressed` and updates its accessible label as it flips.
- **Decorative elements are hidden from assistive technology** — the entire atmospheric effect layer (orbits, particles, glow) is `aria-hidden` and click-through.
- **`prefers-reduced-motion: reduce`** — honoured with dedicated media blocks that disable the animation system for visitors who ask for it.

### Responsive design

The layout is fluid and adapts across a full ladder of breakpoints, all hand-written:

| Breakpoint | Adaptation |
|---|---|
| `max-width: 1100px` | Wide analytics grids begin collapsing |
| `max-width: 980px` | Dashboard and detail layouts reflow to fewer columns |
| `max-width: 720px` | Navigation and card grids stack |
| `max-width: 640px` | Form and table layouts condense |
| `max-width: 560px` | Chart and stat blocks go single-column |
| `max-width: 480px` | Full small-phone layout — single column throughout |

Additional capability-based adaptation:

- **`@media (hover: none)`** — hover-only affordances are replaced on touch devices rather than left unreachable.
- **`@media (hover: hover) and (pointer: fine)`** — pointer-driven effects are enabled only for devices that actually have a precise pointer.
- `<meta name="viewport" content="width=device-width, initial-scale=1.0">` on every page.

---

## 🌗 Theme System

A complete dual-palette design system, implemented entirely in CSS custom properties.

- **Dark is the default.** `:root` in `style.css` *is* the dark palette, so no attribute is required for it.
- **Light mode** is a single override block — `:root[data-theme="light"]` — that redefines the same design tokens. Flipping `data-theme` on `<html>` is the entire re-theme: cards, glass surfaces, aurora, particles and constellation lines all follow, because the JavaScript effect layer reads the same `--fx-*-rgb` token triples the stylesheet themes off.
- **Preference persists** in `localStorage` under the key `realestate-theme`.
- **No flash of the wrong theme.** A tiny inline script in `<head>` — deliberately placed there because `script.js` loads at the end of `<body>` and would already be too late — reads the stored preference and sets `data-theme` *before first paint*. It is wrapped in `try/catch`, so a browser with storage disabled simply stays on the dark default.
- **The toggle is accessible** — a real `<button>` with `aria-pressed` and an accessible label that both update on every switch.

The wider visual language is a hand-built "cosmic glassmorphism" system: an animated space background, aurora, particle field, constellation lines, floating orbs, cursor glow and trail, mouse-proximity lighting, 3D card tilt, sparkles and sonar pulses.

`static/script.js` is a single IIFE split into two documented halves — **Part A**, the effect engine (pointer tracking plus `requestAnimationFrame`-driven animation, rendering through transforms), and **Part B**, page behaviour (toasts, search, delete dialogs, the live form preview, the gallery and the theme toggle). It checks `matchMedia('(prefers-reduced-motion: reduce)')` at startup and stands the atmosphere down entirely for visitors who ask for it.

---

## 📂 Project Structure

```
RealEstate/
│
├── app.py                      Flask application — every route (thin controllers only)
│
├── property_queries.py         All SQL for properties, images and reference lookups
├── property_validation.py      Field rules + business rules for properties
├── agent_queries.py            All SQL for agents
├── agent_validation.py         Field rules for agents
├── inquiry_queries.py          All SQL for inquiries
├── inquiry_validation.py       Field rules + status-transition rules for inquiries
├── analytics_queries.py        Dashboard aggregates + chart-shaping helpers
│
├── real_estate_db.py           Schema DDL, startup migrations, idempotent seeding
├── seed_real_estate.py         Standalone top-up of reference/demo data
│
├── requirements.txt            Runtime dependencies (3)
├── .env                        Local secrets — git-ignored, never committed
│
├── templates/
│   ├── base.html               Shell: brand, nav, theme toggle, flash toasts, pre-paint script
│   ├── dashboard.html          KPI tiles, charts, agent performance, activity panels
│   ├── _icons.html             Inline SVG icon set (Jinja macros)
│   ├── properties/
│   │   ├── index.html          Listing grid with search + filters
│   │   ├── detail.html         Detail view with the image gallery
│   │   ├── add.html  edit.html
│   │   └── _property_form.html Shared create/edit form partial
│   ├── agents/
│   │   ├── index.html  detail.html  add.html  edit.html
│   │   ├── _agent_card.html    Shared agent card partial
│   │   └── _agent_form.html    Shared create/edit form partial
│   └── inquiries/
│       ├── index.html  detail.html  add.html  edit.html
│       └── _inquiry_form.html  Shared create/edit form partial
│
├── static/
│   ├── style.css               The complete visual system — tokens, both themes, responsive
│   ├── script.js               Effect engine + page behaviour (gallery, dialogs, toasts, theme)
│   ├── favicon.svg
│   └── uploads/                User-uploaded property images (UUID filenames)
│
└── tests/
    ├── conftest.py                    Fixtures + isolated test-database setup
    ├── test_real_estate_schema.py     Schema/DDL introspection
    ├── test_properties.py             Property JSON API
    ├── test_property_images.py        Gallery and seeding
    ├── test_agents.py                 Agent module
    ├── test_inquiries.py              Inquiry module
    └── test_dashboard_analytics.py    Dashboard aggregates
```

---

## 🔭 Future Improvements

Deliberately out of scope for the current build, and the natural next steps:

- **Authentication and role-based access control** — separate agent, manager and administrator permissions; this is the single largest gap between the project and a deployable product.
- **CSRF tokens** on every state-changing form.
- **Pagination** on the Properties, Agents and Inquiries listings — every index route currently returns the full result set.
- **Upload hardening** — a `MAX_CONTENT_LENGTH` cap and server-side image type verification beyond the extension allow-list.
- **Connection pooling** — routes currently open and close a connection per request; `mysql.connector.pooling` would remove that overhead under load.
- **Production deployment** — a real WSGI server (Gunicorn/Waitress) behind a reverse proxy, replacing the Flask development server.
- **Saved searches and email notifications** on new inquiries.
- **Map view** for the `locations` reference data.

---

## 👥 Contributors

Built collaboratively. Authorship below reflects the repository's actual commit history.

| Contributor | Role |
|---|---|
| **Youssef Fahem Amin** | Application architecture, property/agent/inquiry modules, analytics layer, database schema and test suite, front-end design system |
| **Ahmed** | Agent detail view with photo support, extended property and inquiry displays |

### Contributing

```bash
git checkout -b feature/your-feature
# make your changes
python -m pytest -v          # all 274 tests must stay green
git commit -m "feat: describe your change"
```

Two conventions the codebase holds to, and which any change should preserve:

1. **Routes stay thin.** No SQL and no business rules in `app.py` — validation belongs in a `*_validation` module, SQL in a `*_queries` module.
2. **Never interpolate a value into SQL.** Every value is bound with `%s`, without exception.

---

<div align="center">

**REAL ESTATE** — Flask · MySQL · Jinja2 · vanilla CSS & JavaScript

</div>
