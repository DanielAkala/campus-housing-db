# Campus Housing Assignment & Audit Database

A MySQL database that models how a university housing office assigns students to beds across residence halls, suites, and apartments, plus a set of audit queries that catch the data errors that break occupancy reporting.

I built this to understand the data side of housing operations: the records behind applications, assignments, room changes, and bed holds, and how to keep them accurate.

## Why it matters

Occupancy numbers, billing, move-in lists, and emergency rosters all depend on assignment data being right. One unclosed room change or one double-booked bed means a student shows up in the wrong place on a report, or in two places at once. This project is about **finding those problems systematically** instead of discovering them on move-in day.

## What's in the repo

| File | What it does |
|---|---|
| `housing_schema.sql` | Creates the database: 10 tables plus reporting views |
| `generate_seed.py` | Generates realistic fake data (230 residents, 220 beds) with 10 deliberate errors |
| `seed.sql` | The generated data, ready to load |
| `audit.sql` | 10 audit checks plus a one-screen summary report |

## How the data is modeled

Every bed on campus is described in four levels:

```
Building  ->  Unit  ->  Room  ->  Bed
```

- **Residence halls** – rooms open onto a hallway, so they have no unit.
- **Suites** – bedrooms grouped into a unit that shares a bathroom/common area.
- **Apartments** – bedrooms grouped into a unit with a shared kitchen and living room.

Students are assigned to a **bed**, not a room, so a double room holds two separate assignments.

Around that structure:

- **Bed holds** take a bed out of the sellable pool for maintenance, accommodations (Disability Support Services), athletics, staff, or emergency housing (Basic Needs).
- **Applications** record term, building preference, and mutual roommate requests.
- **Assignments** record one stay in one bed, with check-in/check-out status and times.
- **Room change requests** link the old assignment to the new one, so move history is preserved.

**Design choices:**

- **Privacy:** housing stores only a "needs accessible room" flag. Accommodation details stay with the office that owns them.
- **Overlaps are audited, not blocked:** a bed can legitimately hold two residents in one term (one moves out, another moves in), so a simple database rule would reject valid data. The audit queries catch overlaps instead, which also covers data that is imported or edited by hand.
- **Room-level gender designation,** with all-gender floors and units, matching how assignments are actually constrained.

## The fake data

All buildings and people are invented. The generator:

- builds 4 buildings (2 traditional halls, 1 suite building, 1 apartment building) with 220 beds
- creates 230 residents with applications, 8 mutual roommate pairs, and 4 students who need accessible rooms
- places students who need accessible rooms first, keeps roommate pairs together, and respects gender designations and holds
- adds real-term events: late arrivals, mid-term withdrawals, and approved/open/denied room changes
- then **plants 10 errors** (listed at the top of `seed.sql`) for the audit to find

## The audit

Each check finds a category of problem without knowing where the errors are. A clean database returns zero rows for every check.

| # | Check | What it catches |
|---|---|---|
| 1 | Double-booked beds | Two residents in the same bed on the same night |
| 2 | Residents in two beds | One resident with overlapping stays |
| 3 | Assigned to held beds | Assignments that overlap a maintenance/accommodation/etc. hold |
| 4 | Gender-designation mismatches | Resident in a room designated for a different gender |
| 5 | Accessibility needs not met | Resident who needs an accessible room placed in one that isn't |
| 6 | Status/timestamp mismatches | For example, "checked in" with no check-in time |
| 7 | Application vs. assignment | Waitlisted but holding a bed, or "assigned" with no bed |
| 8 | Dates outside term | Stays that start before or end after the term |
| 9 | Room changes left open | Approved moves where the old stay was never closed |
| 10 | Roommate requests (info) | Mutual requests placed in different rooms |

Checks 2 and 9 work together: check 2 shows that a student is in two beds, and check 9 shows why (an approved room change whose old assignment was never closed). That's the step to fix in the process, not just in the data.

### Summary output on the seed data

```
+-----------------------------------------+--------+
| audit_check                             | issues |
+-----------------------------------------+--------+
| 1 Double-booked beds                    |      1 |
| 2 Residents in two beds                 |      1 |
| 3 Assigned to held beds                 |      1 |
| 4 Gender-designation mismatches         |      1 |
| 5 Accessibility needs not met           |      1 |
| 6 Status/timestamp mismatches           |      2 |
| 7 Application vs assignment mismatches  |      2 |
| 8 Dates outside term                    |      1 |
| 9 Room changes with old stay open       |      1 |
| 10 Roommate requests not honored (info) |      0 |
+-----------------------------------------+--------+
```

All 10 planted errors are found, with no false positives.

## Reporting views

- `v_bed_location` – every bed with its building, unit, room, type, gender designation, and accessibility.
- `v_occupancy_by_building` – total beds, beds on hold, occupied beds, and occupancy rate (against sellable beds) by building and term.

## Run it

Requires MySQL 8+ (or MariaDB 10.5+) and Python 3.

```bash
mysql -u root < housing_schema.sql
python3 generate_seed.py > seed.sql     # optional: seed.sql is already included
mysql -u root campus_housing < seed.sql
mysql -u root --table campus_housing < audit.sql
```

## Next steps

- Occupancy dashboard built on the reporting views
- Python script that compares an assignment roster export against a check-in log
- Operational queries: open beds by type and gender, waitlist order, suites with N open beds for group requests

---
Daniel Akala · B.S. Computer Science, California State University, Fullerton (Dec 2026)
