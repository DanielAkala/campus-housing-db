-- =====================================================================
-- Campus Housing Assignment & Occupancy Database
-- Models suites, traditional residence halls, and apartments.
-- Hierarchy: building -> unit (suites/apartments only) -> room -> bed
-- Author: Daniel Akala
-- =====================================================================

DROP DATABASE IF EXISTS campus_housing;
CREATE DATABASE campus_housing;
USE campus_housing;

-- ---------------------------------------------------------------------
-- FACILITIES
-- ---------------------------------------------------------------------

CREATE TABLE building (
    building_id     INT AUTO_INCREMENT PRIMARY KEY,
    name            VARCHAR(60)  NOT NULL UNIQUE,
    building_type   ENUM('residence_hall', 'suite', 'apartment') NOT NULL,
    floors          TINYINT UNSIGNED NOT NULL
);

-- A suite or apartment groups several rooms that share a common space
-- (bathroom, living room, kitchen). Traditional hall rooms have no unit.
CREATE TABLE unit (
    unit_id         INT AUTO_INCREMENT PRIMARY KEY,
    building_id     INT NOT NULL,
    unit_number     VARCHAR(10) NOT NULL,
    floor           TINYINT UNSIGNED NOT NULL,
    has_kitchen     BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (building_id, unit_number),
    FOREIGN KEY (building_id) REFERENCES building(building_id)
);

CREATE TABLE room (
    room_id         INT AUTO_INCREMENT PRIMARY KEY,
    building_id     INT NOT NULL,
    unit_id         INT NULL,                       -- NULL for traditional hall rooms
    room_number     VARCHAR(10) NOT NULL,
    floor           TINYINT UNSIGNED NOT NULL,
    room_type       ENUM('single', 'double', 'triple') NOT NULL,
    gender_designation ENUM('male', 'female', 'all_gender') NOT NULL DEFAULT 'all_gender',
    is_accessible   BOOLEAN NOT NULL DEFAULT FALSE, -- ADA features; used for accommodation holds
    UNIQUE (building_id, room_number),
    FOREIGN KEY (building_id) REFERENCES building(building_id),
    FOREIGN KEY (unit_id)     REFERENCES unit(unit_id)
);

CREATE TABLE bed (
    bed_id          INT AUTO_INCREMENT PRIMARY KEY,
    room_id         INT NOT NULL,
    bed_label       CHAR(1) NOT NULL,               -- A, B, C
    UNIQUE (room_id, bed_label),
    FOREIGN KEY (room_id) REFERENCES room(room_id)
);

-- Beds taken out of service (maintenance, damage) or held for a
-- specific purpose (accommodation, athletics, RA, emergency housing).
CREATE TABLE bed_hold (
    hold_id         INT AUTO_INCREMENT PRIMARY KEY,
    bed_id          INT NOT NULL,
    hold_type       ENUM('maintenance', 'accommodation', 'athletics',
                         'staff', 'emergency_housing', 'other') NOT NULL,
    start_date      DATE NOT NULL,
    end_date        DATE NULL,                      -- NULL = open-ended
    note            VARCHAR(255),
    FOREIGN KEY (bed_id) REFERENCES bed(bed_id),
    CHECK (end_date IS NULL OR end_date >= start_date)
);

-- ---------------------------------------------------------------------
-- PEOPLE & TERMS
-- ---------------------------------------------------------------------

CREATE TABLE term (
    term_id         INT AUTO_INCREMENT PRIMARY KEY,
    name            VARCHAR(30) NOT NULL UNIQUE,    -- e.g. 'Fall 2026', 'Summer 2027'
    start_date      DATE NOT NULL,
    end_date        DATE NOT NULL,
    CHECK (end_date > start_date)
);

-- Only what housing needs to make an assignment. Accommodation details
-- stay with Disability Support Services; housing just sees a flag that
-- an accessible room is required.
CREATE TABLE resident (
    resident_id     INT AUTO_INCREMENT PRIMARY KEY,
    campus_id       CHAR(9) NOT NULL UNIQUE,
    first_name      VARCHAR(40) NOT NULL,
    last_name       VARCHAR(40) NOT NULL,
    email           VARCHAR(100) NOT NULL UNIQUE,
    class_level     ENUM('first_year', 'transfer', 'continuing', 'graduate') NOT NULL,
    housing_gender  ENUM('male', 'female', 'nonbinary') NOT NULL,
    needs_accessible_room BOOLEAN NOT NULL DEFAULT FALSE,
    is_athlete      BOOLEAN NOT NULL DEFAULT FALSE
);

-- ---------------------------------------------------------------------
-- APPLICATION -> ASSIGNMENT -> CHANGES
-- ---------------------------------------------------------------------

CREATE TABLE application (
    application_id  INT AUTO_INCREMENT PRIMARY KEY,
    resident_id     INT NOT NULL,
    term_id         INT NOT NULL,
    submitted_at    DATETIME NOT NULL,
    pref_building_type ENUM('residence_hall', 'suite', 'apartment', 'no_preference')
                       NOT NULL DEFAULT 'no_preference',
    pref_roommate_id INT NULL,                      -- mutual roommate request
    status          ENUM('submitted', 'waitlisted', 'assigned',
                         'cancelled') NOT NULL DEFAULT 'submitted',
    UNIQUE (resident_id, term_id),
    FOREIGN KEY (resident_id)      REFERENCES resident(resident_id),
    FOREIGN KEY (term_id)          REFERENCES term(term_id),
    FOREIGN KEY (pref_roommate_id) REFERENCES resident(resident_id)
);

-- One row per stay in a bed. A room change ends one assignment and
-- starts another, so a resident can have several rows in one term.
-- Overlaps (double-booked beds, residents in two beds) are NOT blocked
-- by a constraint on purpose: they are caught by the audit queries,
-- the same way imported or hand-edited data gets checked in practice.
CREATE TABLE assignment (
    assignment_id   INT AUTO_INCREMENT PRIMARY KEY,
    resident_id     INT NOT NULL,
    bed_id          INT NOT NULL,
    term_id         INT NOT NULL,
    start_date      DATE NOT NULL,
    end_date        DATE NOT NULL,
    status          ENUM('pending', 'checked_in', 'checked_out',
                         'cancelled') NOT NULL DEFAULT 'pending',
    check_in_at     DATETIME NULL,
    check_out_at    DATETIME NULL,
    FOREIGN KEY (resident_id) REFERENCES resident(resident_id),
    FOREIGN KEY (bed_id)      REFERENCES bed(bed_id),
    FOREIGN KEY (term_id)     REFERENCES term(term_id),
    CHECK (end_date >= start_date)
);

CREATE TABLE room_change_request (
    request_id      INT AUTO_INCREMENT PRIMARY KEY,
    resident_id     INT NOT NULL,
    from_assignment_id INT NOT NULL,
    to_assignment_id   INT NULL,                    -- filled in once approved & moved
    requested_at    DATETIME NOT NULL,
    reason          ENUM('roommate_conflict', 'accommodation', 'cost',
                         'location', 'facilities_issue', 'other') NOT NULL,
    status          ENUM('open', 'approved', 'denied', 'withdrawn')
                    NOT NULL DEFAULT 'open',
    decided_at      DATETIME NULL,
    FOREIGN KEY (resident_id)        REFERENCES resident(resident_id),
    FOREIGN KEY (from_assignment_id) REFERENCES assignment(assignment_id),
    FOREIGN KEY (to_assignment_id)   REFERENCES assignment(assignment_id)
);

-- Helpful indexes for occupancy and audit queries
CREATE INDEX idx_assignment_term_bed   ON assignment (term_id, bed_id);
CREATE INDEX idx_assignment_term_res   ON assignment (term_id, resident_id);
CREATE INDEX idx_bed_hold_bed_dates    ON bed_hold (bed_id, start_date, end_date);

-- ---------------------------------------------------------------------
-- VIEWS
-- ---------------------------------------------------------------------

-- One row per bed with its full location, ready for reporting.
CREATE VIEW v_bed_location AS
SELECT  be.bed_id,
        b.name           AS building,
        b.building_type,
        u.unit_number,
        r.room_number,
        r.room_type,
        r.gender_designation,
        r.is_accessible,
        be.bed_label
FROM bed be
JOIN room r          ON r.room_id = be.room_id
JOIN building b      ON b.building_id = r.building_id
LEFT JOIN unit u     ON u.unit_id = r.unit_id;

-- Occupancy by building and term: total beds, beds on hold,
-- occupied beds, and occupancy rate against sellable beds.
CREATE VIEW v_occupancy_by_building AS
SELECT  t.name                               AS term,
        b.name                               AS building,
        b.building_type,
        COUNT(DISTINCT be.bed_id)            AS total_beds,
        COUNT(DISTINCT h.bed_id)             AS beds_on_hold,
        COUNT(DISTINCT a.bed_id)             AS occupied_beds,
        ROUND(100 * COUNT(DISTINCT a.bed_id) /
              NULLIF(COUNT(DISTINCT be.bed_id) - COUNT(DISTINCT h.bed_id), 0), 1)
                                             AS occupancy_pct
FROM term t
CROSS JOIN building b
JOIN room r     ON r.building_id = b.building_id
JOIN bed be     ON be.room_id = r.room_id
LEFT JOIN bed_hold h
       ON h.bed_id = be.bed_id
      AND h.start_date <= t.end_date
      AND (h.end_date IS NULL OR h.end_date >= t.start_date)
LEFT JOIN assignment a
       ON a.bed_id = be.bed_id
      AND a.term_id = t.term_id
      AND a.status IN ('pending', 'checked_in')
GROUP BY t.term_id, t.name, b.building_id, b.name, b.building_type;
