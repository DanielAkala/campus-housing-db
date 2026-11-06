-- =====================================================================
-- Housing data audit
-- Each check finds one kind of data problem without knowing in advance
-- where the problems are. A clean database returns zero rows for every
-- check. Run the SUMMARY at the bottom for a one-screen health report.
--
-- Date convention: start_date = first night, end_date = last night.
-- Two stays overlap when each starts on or before the other ends.
-- "Active" = an assignment that isn't cancelled.
-- Author: Daniel Akala
-- =====================================================================
USE campus_housing;

-- ---------------------------------------------------------------------
-- CHECK 1: Double-booked beds
-- Two different residents in the same bed on the same night.
-- ---------------------------------------------------------------------
SELECT  bl.building, bl.room_number, bl.bed_label,
        a.resident_id AS resident_1, a.start_date AS start_1, a.end_date AS end_1,
        b.resident_id AS resident_2, b.start_date AS start_2, b.end_date AS end_2
FROM assignment a
JOIN assignment b
     ON  b.bed_id = a.bed_id
     AND b.assignment_id > a.assignment_id          -- each pair once
     AND b.resident_id <> a.resident_id
     AND a.start_date <= b.end_date
     AND b.start_date <= a.end_date
JOIN v_bed_location bl ON bl.bed_id = a.bed_id
WHERE a.status <> 'cancelled' AND b.status <> 'cancelled';

-- ---------------------------------------------------------------------
-- CHECK 2: Residents in two beds at once
-- Usually a room change where the old assignment was never closed.
-- ---------------------------------------------------------------------
SELECT  r.resident_id, r.first_name, r.last_name,
        a.assignment_id AS assignment_1, bl1.building AS building_1, bl1.room_number AS room_1,
        b.assignment_id AS assignment_2, bl2.building AS building_2, bl2.room_number AS room_2,
        GREATEST(a.start_date, b.start_date) AS overlap_from,
        LEAST(a.end_date, b.end_date)        AS overlap_to
FROM assignment a
JOIN assignment b
     ON  b.resident_id = a.resident_id
     AND b.assignment_id > a.assignment_id
     AND a.start_date <= b.end_date
     AND b.start_date <= a.end_date
JOIN resident r        ON r.resident_id = a.resident_id
JOIN v_bed_location bl1 ON bl1.bed_id = a.bed_id
JOIN v_bed_location bl2 ON bl2.bed_id = b.bed_id
WHERE a.status <> 'cancelled' AND b.status <> 'cancelled';

-- ---------------------------------------------------------------------
-- CHECK 3: Assignments to beds that are on hold
-- Maintenance, accommodation, athletics, staff or emergency beds that
-- someone was assigned to anyway while the hold was in effect.
-- ---------------------------------------------------------------------
SELECT  a.assignment_id, a.resident_id,
        bl.building, bl.room_number, bl.bed_label,
        h.hold_type, h.note, h.start_date AS hold_start, h.end_date AS hold_end
FROM assignment a
JOIN bed_hold h
     ON  h.bed_id = a.bed_id
     AND h.start_date <= a.end_date
     AND (h.end_date IS NULL OR h.end_date >= a.start_date)
JOIN v_bed_location bl ON bl.bed_id = a.bed_id
WHERE a.status <> 'cancelled';

-- ---------------------------------------------------------------------
-- CHECK 4: Gender-designation mismatches
-- Resident placed in a room designated for a different gender.
-- ---------------------------------------------------------------------
SELECT  a.assignment_id, r.resident_id, r.housing_gender,
        bl.building, bl.room_number, bl.gender_designation
FROM assignment a
JOIN resident r        ON r.resident_id = a.resident_id
JOIN v_bed_location bl ON bl.bed_id = a.bed_id
WHERE a.status <> 'cancelled'
  AND bl.gender_designation <> 'all_gender'
  AND bl.gender_designation <> r.housing_gender;

-- ---------------------------------------------------------------------
-- CHECK 5: Accessibility needs not met
-- Resident flagged as needing an accessible room placed in one that isn't.
-- ---------------------------------------------------------------------
SELECT  a.assignment_id, r.resident_id, r.first_name, r.last_name,
        bl.building, bl.room_number, bl.is_accessible
FROM assignment a
JOIN resident r        ON r.resident_id = a.resident_id
JOIN v_bed_location bl ON bl.bed_id = a.bed_id
WHERE a.status <> 'cancelled'
  AND r.needs_accessible_room = TRUE
  AND bl.is_accessible = FALSE;

-- ---------------------------------------------------------------------
-- CHECK 6: Check-in / check-out records that don't match the status
-- ---------------------------------------------------------------------
SELECT  assignment_id, resident_id, status, check_in_at, check_out_at,
        CASE
          WHEN status = 'checked_in'  AND check_in_at  IS NULL  THEN 'checked in, no check-in time'
          WHEN status = 'checked_out' AND check_out_at IS NULL  THEN 'checked out, no check-out time'
          WHEN status = 'pending'     AND check_in_at  IS NOT NULL THEN 'pending, but has a check-in time'
          WHEN check_out_at < check_in_at                       THEN 'check-out before check-in'
        END AS problem
FROM assignment
WHERE (status = 'checked_in'  AND check_in_at  IS NULL)
   OR (status = 'checked_out' AND check_out_at IS NULL)
   OR (status = 'pending'     AND check_in_at  IS NOT NULL)
   OR (check_out_at < check_in_at);

-- ---------------------------------------------------------------------
-- CHECK 7: Application status disagrees with assignments
-- ---------------------------------------------------------------------
-- 7a. Waitlisted or cancelled, but holding an active assignment
SELECT  ap.application_id, ap.resident_id, ap.status AS application_status,
        a.assignment_id, a.status AS assignment_status
FROM application ap
JOIN assignment a
     ON  a.resident_id = ap.resident_id
     AND a.term_id = ap.term_id
     AND a.status <> 'cancelled'
WHERE ap.status IN ('waitlisted', 'cancelled');

-- 7b. Marked assigned, but no assignment exists for that term
SELECT  ap.application_id, ap.resident_id, ap.status AS application_status
FROM application ap
LEFT JOIN assignment a
     ON  a.resident_id = ap.resident_id
     AND a.term_id = ap.term_id
     AND a.status <> 'cancelled'
WHERE ap.status = 'assigned'
  AND a.assignment_id IS NULL;

-- ---------------------------------------------------------------------
-- CHECK 8: Assignment dates outside the term
-- ---------------------------------------------------------------------
SELECT  a.assignment_id, a.resident_id, t.name AS term,
        a.start_date, a.end_date, t.start_date AS term_start, t.end_date AS term_end
FROM assignment a
JOIN term t ON t.term_id = a.term_id
WHERE a.start_date < t.start_date
   OR a.end_date   > t.end_date;

-- ---------------------------------------------------------------------
-- CHECK 9: Approved room changes where the old stay was left open
-- Cross-check for CHECK 2: tells you *why* someone is in two beds.
-- ---------------------------------------------------------------------
SELECT  rc.request_id, rc.resident_id, rc.decided_at,
        old_a.assignment_id AS old_assignment, old_a.status AS old_status, old_a.end_date AS old_end,
        new_a.assignment_id AS new_assignment, new_a.start_date AS new_start
FROM room_change_request rc
JOIN assignment old_a ON old_a.assignment_id = rc.from_assignment_id
JOIN assignment new_a ON new_a.assignment_id = rc.to_assignment_id
WHERE rc.status = 'approved'
  AND old_a.end_date >= new_a.start_date;

-- ---------------------------------------------------------------------
-- CHECK 10 (informational): Mutual roommate requests not honored
-- Not an error by itself; useful to review before move-in.
-- ---------------------------------------------------------------------
SELECT  ap.resident_id, ap.pref_roommate_id,
        bl1.building AS building_1, bl1.room_number AS room_1,
        bl2.building AS building_2, bl2.room_number AS room_2
FROM application ap
JOIN application mate
     ON  mate.resident_id = ap.pref_roommate_id
     AND mate.term_id = ap.term_id
     AND mate.pref_roommate_id = ap.resident_id     -- mutual request
JOIN assignment a1 ON a1.resident_id = ap.resident_id   AND a1.term_id = ap.term_id AND a1.status <> 'cancelled'
JOIN assignment a2 ON a2.resident_id = mate.resident_id AND a2.term_id = ap.term_id AND a2.status <> 'cancelled'
JOIN v_bed_location bl1 ON bl1.bed_id = a1.bed_id
JOIN v_bed_location bl2 ON bl2.bed_id = a2.bed_id
JOIN bed b1 ON b1.bed_id = a1.bed_id
JOIN bed b2 ON b2.bed_id = a2.bed_id
WHERE ap.resident_id < ap.pref_roommate_id
  AND b1.room_id <> b2.room_id;

-- =====================================================================
-- SUMMARY: one row per check with its issue count
-- =====================================================================
SELECT '1 Double-booked beds' AS audit_check, COUNT(*) AS issues
FROM assignment a JOIN assignment b
  ON b.bed_id = a.bed_id AND b.assignment_id > a.assignment_id AND b.resident_id <> a.resident_id
 AND a.start_date <= b.end_date AND b.start_date <= a.end_date
WHERE a.status <> 'cancelled' AND b.status <> 'cancelled'
UNION ALL
SELECT '2 Residents in two beds', COUNT(*)
FROM assignment a JOIN assignment b
  ON b.resident_id = a.resident_id AND b.assignment_id > a.assignment_id
 AND a.start_date <= b.end_date AND b.start_date <= a.end_date
WHERE a.status <> 'cancelled' AND b.status <> 'cancelled'
UNION ALL
SELECT '3 Assigned to held beds', COUNT(*)
FROM assignment a JOIN bed_hold h
  ON h.bed_id = a.bed_id AND h.start_date <= a.end_date
 AND (h.end_date IS NULL OR h.end_date >= a.start_date)
WHERE a.status <> 'cancelled'
UNION ALL
SELECT '4 Gender-designation mismatches', COUNT(*)
FROM assignment a JOIN resident r USING (resident_id) JOIN v_bed_location bl USING (bed_id)
WHERE a.status <> 'cancelled' AND bl.gender_designation <> 'all_gender'
  AND bl.gender_designation <> r.housing_gender
UNION ALL
SELECT '5 Accessibility needs not met', COUNT(*)
FROM assignment a JOIN resident r USING (resident_id) JOIN v_bed_location bl USING (bed_id)
WHERE a.status <> 'cancelled' AND r.needs_accessible_room AND NOT bl.is_accessible
UNION ALL
SELECT '6 Status/timestamp mismatches', COUNT(*)
FROM assignment
WHERE (status = 'checked_in' AND check_in_at IS NULL)
   OR (status = 'checked_out' AND check_out_at IS NULL)
   OR (status = 'pending' AND check_in_at IS NOT NULL)
   OR (check_out_at < check_in_at)
UNION ALL
SELECT '7 Application vs assignment mismatches', COUNT(*)
FROM application ap
WHERE (ap.status IN ('waitlisted', 'cancelled') AND EXISTS
        (SELECT 1 FROM assignment a WHERE a.resident_id = ap.resident_id
          AND a.term_id = ap.term_id AND a.status <> 'cancelled'))
   OR (ap.status = 'assigned' AND NOT EXISTS
        (SELECT 1 FROM assignment a WHERE a.resident_id = ap.resident_id
          AND a.term_id = ap.term_id AND a.status <> 'cancelled'))
UNION ALL
SELECT '8 Dates outside term', COUNT(*)
FROM assignment a JOIN term t USING (term_id)
WHERE a.start_date < t.start_date OR a.end_date > t.end_date
UNION ALL
SELECT '9 Room changes with old stay open', COUNT(*)
FROM room_change_request rc
JOIN assignment o ON o.assignment_id = rc.from_assignment_id
JOIN assignment n ON n.assignment_id = rc.to_assignment_id
WHERE rc.status = 'approved' AND o.end_date >= n.start_date
UNION ALL
SELECT '10 Roommate requests not honored (info)', COUNT(*)
FROM application ap
JOIN application m ON m.resident_id = ap.pref_roommate_id AND m.term_id = ap.term_id
                  AND m.pref_roommate_id = ap.resident_id
JOIN assignment a1 ON a1.resident_id = ap.resident_id AND a1.term_id = ap.term_id AND a1.status <> 'cancelled'
JOIN assignment a2 ON a2.resident_id = m.resident_id  AND a2.term_id = ap.term_id AND a2.status <> 'cancelled'
JOIN bed b1 ON b1.bed_id = a1.bed_id
JOIN bed b2 ON b2.bed_id = a2.bed_id
WHERE ap.resident_id < ap.pref_roommate_id AND b1.room_id <> b2.room_id;
