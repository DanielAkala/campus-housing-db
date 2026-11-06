#!/usr/bin/env python3
"""
Generate realistic fake data for the campus_housing database.

Usage:
    python3 generate_seed.py > seed.sql
    mysql -u root < housing_schema.sql
    mysql -u root campus_housing < seed.sql

Everything here is fictional: invented buildings, invented residents.
The data also contains a handful of DELIBERATE problems (a double-booked
bed, a gender-designation mismatch, bad check-in statuses, etc.) so the
audit queries have something real to catch. They are listed in the
header of the generated seed.sql.

Author: Daniel Akala
"""
import random
from datetime import date, datetime, time, timedelta

random.seed(2026)  # same output every run

# ---------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------
FIRST = ["Aaliyah", "Adrian", "Alejandro", "Amara", "Andre", "Angela", "Anh",
         "Brianna", "Carlos", "Chloe", "Daniela", "David", "Diego", "Emily",
         "Ethan", "Fatima", "Gabriel", "Grace", "Hannah", "Hiro", "Isabella",
         "Jacob", "Jasmine", "Javier", "Jayden", "Jessica", "Jordan", "Joshua",
         "Kayla", "Kevin", "Kimberly", "Leila", "Liam", "Lucia", "Malik",
         "Maria", "Mateo", "Maya", "Michael", "Minh", "Nadia", "Nathan",
         "Nia", "Noah", "Olivia", "Omar", "Priya", "Rafael", "Riley", "Samantha",
         "Samuel", "Sofia", "Tariq", "Thanh", "Tyler", "Valeria", "Vanessa",
         "Victor", "Wei", "Xavier", "Yesenia", "Zoe"]
LAST = ["Aguilar", "Alvarez", "Bui", "Castillo", "Chen", "Cruz", "Davis",
        "Diaz", "Do", "Flores", "Garcia", "Gomez", "Gonzalez", "Gupta",
        "Hernandez", "Ibrahim", "Jackson", "Johnson", "Kim", "Le", "Lee",
        "Lopez", "Martinez", "Mendoza", "Nguyen", "O'Brien", "Okafor", "Ortiz",
        "Park", "Patel", "Pham", "Ramirez", "Reyes", "Rivera", "Rodriguez",
        "Santos", "Shah", "Smith", "Tran", "Vargas", "Vasquez", "Williams",
        "Wong", "Yang", "Zhang"]

TERMS = [
    # id, name, start, end
    (1, "Fall 2026",   date(2026, 8, 20), date(2026, 12, 18)),
    (2, "Spring 2027", date(2027, 1, 19), date(2027, 5, 21)),
]
FALL_ID, _, TERM_START, TERM_END = TERMS[0]

N_RESIDENTS = 230
HOLD_BACK_BEDS = 14   # beds kept open for late admits / emergencies

# ---------------------------------------------------------------------
# Containers for every table
# ---------------------------------------------------------------------
buildings, units, rooms, beds = [], [], [], []
holds, residents, applications, assignments, changes = [], [], [], [], []
planted = []          # human-readable list of deliberate errors


def add_room(building_id, unit_id, number, floor, rtype, gender, accessible):
    room_id = len(rooms) + 1
    rooms.append(dict(room_id=room_id, building_id=building_id, unit_id=unit_id,
                      room_number=number, floor=floor, room_type=rtype,
                      gender=gender, accessible=accessible))
    n_beds = {"single": 1, "double": 2, "triple": 3}[rtype]
    for label in "ABC"[:n_beds]:
        beds.append(dict(bed_id=len(beds) + 1, room_id=room_id, unit_id=unit_id,
                         building_id=building_id, label=label, gender=gender,
                         accessible=accessible, room_type=rtype))


def add_unit(building_id, number, floor, kitchen):
    units.append(dict(unit_id=len(units) + 1, building_id=building_id,
                      unit_number=number, floor=floor, kitchen=kitchen))
    return len(units)


# ---------------------------------------------------------------------
# 1. Facilities: two traditional halls, one suite building, one apartment
# ---------------------------------------------------------------------
def build_hall(name, floor_genders):
    bid = len(buildings) + 1
    buildings.append(dict(building_id=bid, name=name, type="residence_hall",
                          floors=len(floor_genders)))
    for floor, gender in floor_genders.items():
        for i in range(1, 11):                     # 10 rooms per floor
            accessible = (floor == 1 and i == 1)
            rtype = "single" if i >= 9 else "double"
            add_room(bid, None, f"{floor}{i:02d}", floor, rtype,
                     "all_gender" if accessible else gender, accessible)


def build_suites(name, floors):
    bid = len(buildings) + 1
    buildings.append(dict(building_id=bid, name=name, type="suite", floors=floors))
    for floor in range(1, floors + 1):
        for u in range(1, 5):                      # 4 suites per floor
            number = f"{floor}{u:02d}"
            accessible = (floor == 1 and u == 1)
            if accessible or floor == floors:
                gender = "all_gender"              # top floor is all-gender
            else:
                gender = "male" if u % 2 else "female"
            uid = add_unit(bid, number, floor, kitchen=False)
            for letter in "AB":                    # 2 double bedrooms per suite
                add_room(bid, uid, number + letter, floor, "double", gender, accessible)


def build_apartments(name, floors):
    bid = len(buildings) + 1
    buildings.append(dict(building_id=bid, name=name, type="apartment", floors=floors))
    cycle = ["male", "female", "all_gender"]
    for floor in range(1, floors + 1):
        for u in range(1, 5):                      # 4 apartments per floor
            number = f"{floor}{u:02d}"
            accessible = (floor == 1 and u == 1)
            gender = "all_gender" if accessible else cycle[(floor + u) % 3]
            uid = add_unit(bid, number, floor, kitchen=True)
            for letter in "ABCD":                  # 4 single bedrooms per apt
                add_room(bid, uid, number + letter, floor, "single", gender, accessible)


build_hall("Oak Hall",   {1: "male", 2: "female", 3: "all_gender"})
build_hall("Maple Hall", {1: "female", 2: "male", 3: "all_gender"})
build_suites("Cedar Suites", floors=4)
build_apartments("Willow Apartments", floors=3)

btype = {b["building_id"]: b["type"] for b in buildings}
bname = {b["building_id"]: b["name"] for b in buildings}
bed_by_id = {b["bed_id"]: b for b in beds}


def where(bed):
    room = rooms[bed["room_id"] - 1]
    return f'{bname[bed["building_id"]]} {room["room_number"]}-{bed["label"]}'


# ---------------------------------------------------------------------
# 2. Bed holds
# ---------------------------------------------------------------------
def add_hold(bed, kind, start, end, note):
    holds.append(dict(hold_id=len(holds) + 1, bed_id=bed["bed_id"], type=kind,
                      start=start, end=end, note=note))


regular = [b for b in beds if not b["accessible"]]
accessible_beds = [b for b in beds if b["accessible"]]
random.shuffle(regular)

for b in regular[:3]:
    add_hold(b, "maintenance", date(2026, 8, 1), None,
             random.choice(["Water damage - drywall repair", "Broken window",
                            "Mold remediation", "HVAC unit replacement"]))
for b in random.sample(accessible_beds, 2):
    add_hold(b, "accommodation", date(2026, 8, 1), TERM_END,
             "Held for DSS accessible-room placement")
for b in [x for x in regular[3:] if btype[x["building_id"]] == "suite"][:2]:
    add_hold(b, "athletics", date(2026, 8, 1), TERM_END,
             "Held for incoming winter-sport athletes")
apt = [x for x in regular[3:] if btype[x["building_id"]] == "apartment"][0]
add_hold(apt, "emergency_housing", date(2026, 8, 1), None,
         "Basic Needs Services emergency housing bed")

held = {h["bed_id"] for h in holds}
maintenance_beds = [h["bed_id"] for h in holds if h["type"] == "maintenance"]

# ---------------------------------------------------------------------
# 3. Residents and applications
# ---------------------------------------------------------------------
used_ids = set()
for rid in range(1, N_RESIDENTS + 1):
    first, last = random.choice(FIRST), random.choice(LAST)
    while True:
        cid = "888" + f"{random.randint(0, 999999):06d}"
        if cid not in used_ids:
            used_ids.add(cid)
            break
    level = random.choices(["first_year", "transfer", "continuing", "graduate"],
                           [50, 15, 30, 5])[0]
    residents.append(dict(
        resident_id=rid, campus_id=cid, first=first, last=last,
        email=f'{first}.{last}{rid}@example.edu'.lower().replace("'", ""),
        level=level,
        gender=random.choices(["female", "male", "nonbinary"], [48, 45, 7])[0],
        accessible=False, athlete=random.random() < 0.05))

for r in random.sample(residents, 4):
    r["accessible"] = True

PREF = {"first_year": (["residence_hall", "suite", "no_preference"], [55, 35, 10]),
        "transfer":   (["suite", "apartment", "no_preference"], [40, 40, 20]),
        "continuing": (["apartment", "suite", "no_preference"], [55, 30, 15]),
        "graduate":   (["apartment", "no_preference"], [85, 15])}

for r in residents:
    opts, w = PREF[r["level"]]
    submitted = datetime(2026, 3, 1, 9) + timedelta(
        minutes=random.randint(0, 152 * 24 * 60))    # March 1 - July 31
    applications.append(dict(app_id=r["resident_id"], rid=r["resident_id"],
                             submitted=submitted, pref=random.choices(opts, w)[0],
                             roommate=None, status="submitted"))
app_of = {a["rid"]: a for a in applications}
res_of = {r["resident_id"]: r for r in residents}

for a in random.sample(applications, 8):
    a["status"] = "cancelled"

# Mutual roommate requests: same housing gender, both want a double room
pool = [r for r in residents if app_of[r["resident_id"]]["status"] != "cancelled"
        and r["gender"] in ("male", "female") and not r["accessible"]]
random.shuffle(pool)
pairs, taken = [], set()
for r in pool:
    if len(pairs) == 8 or r["resident_id"] in taken:
        continue
    mate = next((m for m in pool if m["gender"] == r["gender"]
                 and m["resident_id"] != r["resident_id"]
                 and m["resident_id"] not in taken), None)
    if mate:
        taken |= {r["resident_id"], mate["resident_id"]}
        pairs.append((r["resident_id"], mate["resident_id"]))
        pref = random.choice(["residence_hall", "suite"])
        for x, y in ((r, mate), (mate, r)):
            app_of[x["resident_id"]]["roommate"] = y["resident_id"]
            app_of[x["resident_id"]]["pref"] = pref

# ---------------------------------------------------------------------
# 4. Assignment process (accessible needs first, then by submit time)
# ---------------------------------------------------------------------
occupied = set()       # beds with any Fall assignment


def gender_ok(bed, r):
    return bed["gender"] == "all_gender" or bed["gender"] == r["gender"]


def free_beds(pred=lambda b: True, allow_held=False):
    return [b for b in beds if b["bed_id"] not in occupied
            and (allow_held or b["bed_id"] not in held) and pred(b)]


def checkin_time():
    day = TERM_START + timedelta(days=random.randint(0, 2))   # move-in weekend
    return datetime.combine(day, time(random.randint(8, 17), random.choice([0, 15, 30, 45])))


def assign(r, bed, start=TERM_START, end=TERM_END, status="checked_in", when=None):
    occupied.add(bed["bed_id"])
    row = dict(asg_id=len(assignments) + 1, rid=r["resident_id"], bed_id=bed["bed_id"],
               start=start, end=end, status=status,
               check_in=when if when else (checkin_time() if status != "pending" else None),
               check_out=None)
    assignments.append(row)
    return row


cap = len(beds) - len(held) - HOLD_BACK_BEDS
order = sorted([a for a in applications if a["status"] != "cancelled"],
               key=lambda a: (not res_of[a["rid"]]["accessible"], a["submitted"]))
done = set()

for a in order:
    r = res_of[a["rid"]]
    if r["resident_id"] in done:
        continue
    count = len(assignments)

    if a["roommate"]:                                 # place the pair together
        m = res_of[a["roommate"]]
        rooms_ok = {}
        for b in free_beds(lambda b: b["room_type"] == "double" and gender_ok(b, r)):
            rooms_ok.setdefault(b["room_id"], []).append(b)
        both = [v for v in rooms_ok.values() if len(v) == 2]
        pref_both = [v for v in both if btype[v[0]["building_id"]] == a["pref"]]
        if count + 2 <= cap and (pref_both or both):
            b1, b2 = random.choice(pref_both or both)
            assign(r, b1); assign(m, b2)
            a["status"] = app_of[m["resident_id"]]["status"] = "assigned"
        else:
            a["status"] = app_of[m["resident_id"]]["status"] = "waitlisted"
        done |= {r["resident_id"], m["resident_id"]}
        continue

    cands = free_beds(lambda b: gender_ok(b, r) and (b["accessible"] or not r["accessible"]))
    if r["accessible"]:
        cands = [b for b in cands if b["accessible"]]
    preferred = [b for b in cands if btype[b["building_id"]] == a["pref"]]
    if count < cap and (preferred or cands):
        assign(r, random.choice(preferred or cands))
        a["status"] = "assigned"
    else:
        a["status"] = "waitlisted"
    done.add(r["resident_id"])

normal = [x for x in assignments]                   # untouched so far
random.shuffle(normal)

# Late arrivals: assigned but not yet checked in
for x in normal[:5]:
    x["status"], x["check_in"] = "pending", None
# Early departures (withdrew mid-term)
early = normal[5:9]
for x in early:
    leave = date(2026, 10, 1) + timedelta(days=random.randint(0, 45))
    x["end"], x["status"] = leave, "checked_out"
    x["check_out"] = datetime.combine(leave, time(random.randint(9, 16), 0))
in_use = normal[9:]                                 # pool for later picks


def pop_movable():
    """Take a checked-in assignment whose resident has a free bed to move into."""
    for i, x in enumerate(in_use):
        r = res_of[x["rid"]]
        spots = free_beds(lambda b: gender_ok(b, r) and not b["accessible"])
        if spots:
            return in_use.pop(i), r, random.choice(spots)
    raise RuntimeError("no free bed for a room change")

# ---------------------------------------------------------------------
# 5. Room change requests
# ---------------------------------------------------------------------
REASONS = ["roommate_conflict", "location", "facilities_issue", "cost", "other"]


def add_change(rid, from_id, to_id, requested, reason, status, decided):
    changes.append(dict(req_id=len(changes) + 1, rid=rid, from_id=from_id, to_id=to_id,
                        requested=requested, reason=reason, status=status, decided=decided))


for _ in range(3):                                  # approved moves
    x, r, target = pop_movable()
    move = date(2026, 9, 8) + timedelta(days=random.randint(0, 22))
    x["end"], x["status"] = move - timedelta(days=1), "checked_out"
    x["check_out"] = datetime.combine(move, time(10, 0))
    new = assign(r, target, start=move, when=datetime.combine(move, time(11, 0)))
    req = datetime.combine(move - timedelta(days=random.randint(5, 14)), time(13, 0))
    add_change(r["resident_id"], x["asg_id"], new["asg_id"], req,
               random.choice(REASONS), "approved", req + timedelta(days=2))

for status in ["open", "open", "denied"]:
    x = in_use.pop()
    req = datetime(2026, 10, 5, 14) + timedelta(days=random.randint(0, 30))
    add_change(x["rid"], x["asg_id"], None, req, random.choice(REASONS), status,
               req + timedelta(days=3) if status == "denied" else None)

# ---------------------------------------------------------------------
# 6. Deliberate data problems for the audit queries to catch
# ---------------------------------------------------------------------
waitlist = [a for a in applications if a["status"] == "waitlisted"]
random.shuffle(waitlist)
assert len(waitlist) >= 6 and len(in_use) >= 3, "not enough data to plant errors"


def pull_waitlisted(pred=lambda r: True):
    for i, a in enumerate(waitlist):
        if pred(res_of[a["rid"]]):
            return waitlist.pop(i), res_of[a["rid"]]
    raise RuntimeError("no waitlisted resident fits")


late = datetime(2026, 8, 25, 12, 0)

# E1: double-booked bed
victim = in_use.pop()
a1, r1 = pull_waitlisted(lambda r: gender_ok(bed_by_id[victim["bed_id"]], r))
a1["status"] = "assigned"
assign(r1, bed_by_id[victim["bed_id"]], when=late)
planted.append(f'E1 double-booked bed: {where(bed_by_id[victim["bed_id"]])} '
               f'(residents {victim["rid"]} and {r1["resident_id"]})')

# E2: resident in two beds at once (room change where old stay never closed)
x, r2, target = pop_movable()
move = date(2026, 9, 21)
new = assign(r2, target, start=move, when=datetime.combine(move, time(11, 0)))
add_change(r2["resident_id"], x["asg_id"], new["asg_id"],
           datetime(2026, 9, 14, 10), "roommate_conflict", "approved",
           datetime(2026, 9, 16, 10))
planted.append(f'E2 resident {r2["resident_id"]} in two beds from {move} '
               f'(old assignment {x["asg_id"]} never closed)')

# E3: assigned to a bed under a maintenance hold
mbed = bed_by_id[maintenance_beds[0]]
a3, r3 = pull_waitlisted(lambda r: gender_ok(mbed, r))
a3["status"] = "assigned"
assign(r3, mbed, when=late)
planted.append(f'E3 resident {r3["resident_id"]} assigned to maintenance-hold bed {where(mbed)}')

# E4: gender-designation mismatch
for want, room_g in (("male", "female"), ("female", "male")):
    spots = free_beds(lambda b: b["gender"] == room_g)
    if spots and any(res_of[a["rid"]]["gender"] == want for a in waitlist):
        a4, r4 = pull_waitlisted(lambda r: r["gender"] == want)
        a4["status"] = "assigned"
        bed4 = random.choice(spots)
        assign(r4, bed4, when=late)
        planted.append(f'E4 {want} resident {r4["resident_id"]} in {room_g}-designated room {where(bed4)}')
        break

# E5: resident who needs an accessible room placed in a non-accessible one
a5, r5 = pull_waitlisted(lambda r: free_beds(lambda b: gender_ok(b, r) and not b["accessible"]))
r5["accessible"] = True
a5["status"] = "assigned"
bed5 = random.choice(free_beds(lambda b: gender_ok(b, r5) and not b["accessible"]))
assign(r5, bed5, when=late)
planted.append(f'E5 resident {r5["resident_id"]} needs accessible room but is in {where(bed5)}')

# E6: status inconsistencies
x = in_use.pop()
x["check_in"] = None
planted.append(f'E6a assignment {x["asg_id"]} is checked_in with no check-in time')
early[0]["check_out"] = None
planted.append(f'E6b assignment {early[0]["asg_id"]} is checked_out with no check-out time')

# E7: application status disagrees with assignments
a7, r7 = pull_waitlisted(lambda r: free_beds(lambda b: gender_ok(b, r) and not b["accessible"]))
bed7 = random.choice(free_beds(lambda b: gender_ok(b, r7) and not b["accessible"]))
assign(r7, bed7, when=late)                              # app stays 'waitlisted'
planted.append(f'E7a resident {r7["resident_id"]} is waitlisted but has an assignment')
a7b, r7b = pull_waitlisted()
a7b["status"] = "assigned"                               # ...but no assignment
planted.append(f'E7b resident {r7b["resident_id"]} marked assigned with no assignment')

# E8: assignment dates outside the term
x = in_use.pop()
x["end"] = date(2026, 12, 31)
planted.append(f'E8 assignment {x["asg_id"]} ends 2026-12-31, after the term ends')

# ---------------------------------------------------------------------
# 7. Emit SQL
# ---------------------------------------------------------------------
def q(v):
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, datetime):
        return f"'{v:%Y-%m-%d %H:%M:%S}'"
    if isinstance(v, date):
        return f"'{v:%Y-%m-%d}'"
    return "'" + str(v).replace("'", "''") + "'"


def insert(table, cols, rows):
    if not rows:
        return
    print(f"INSERT INTO {table} ({', '.join(cols)}) VALUES")
    print(",\n".join("  (" + ", ".join(q(v) for v in row) + ")" for row in rows) + ";\n")


print("-- Seed data for campus_housing (generated by generate_seed.py)")
print("-- All buildings and people are fictional.")
print("--")
print("-- Deliberate data problems for the audit queries to find:")
for p in planted:
    print(f"--   {p}")
print("\nUSE campus_housing;\n")

insert("building", ["building_id", "name", "building_type", "floors"],
       [(b["building_id"], b["name"], b["type"], b["floors"]) for b in buildings])
insert("unit", ["unit_id", "building_id", "unit_number", "floor", "has_kitchen"],
       [(u["unit_id"], u["building_id"], u["unit_number"], u["floor"], u["kitchen"]) for u in units])
insert("room", ["room_id", "building_id", "unit_id", "room_number", "floor", "room_type",
                "gender_designation", "is_accessible"],
       [(r["room_id"], r["building_id"], r["unit_id"], r["room_number"], r["floor"],
         r["room_type"], r["gender"], r["accessible"]) for r in rooms])
insert("bed", ["bed_id", "room_id", "bed_label"],
       [(b["bed_id"], b["room_id"], b["label"]) for b in beds])
insert("bed_hold", ["hold_id", "bed_id", "hold_type", "start_date", "end_date", "note"],
       [(h["hold_id"], h["bed_id"], h["type"], h["start"], h["end"], h["note"]) for h in holds])
insert("term", ["term_id", "name", "start_date", "end_date"], TERMS)
insert("resident", ["resident_id", "campus_id", "first_name", "last_name", "email",
                    "class_level", "housing_gender", "needs_accessible_room", "is_athlete"],
       [(r["resident_id"], r["campus_id"], r["first"], r["last"], r["email"], r["level"],
         r["gender"], r["accessible"], r["athlete"]) for r in residents])
insert("application", ["application_id", "resident_id", "term_id", "submitted_at",
                       "pref_building_type", "pref_roommate_id", "status"],
       [(a["app_id"], a["rid"], FALL_ID, a["submitted"], a["pref"], a["roommate"], a["status"])
        for a in applications])
insert("assignment", ["assignment_id", "resident_id", "bed_id", "term_id", "start_date",
                      "end_date", "status", "check_in_at", "check_out_at"],
       [(x["asg_id"], x["rid"], x["bed_id"], FALL_ID, x["start"], x["end"], x["status"],
         x["check_in"], x["check_out"]) for x in assignments])
insert("room_change_request", ["request_id", "resident_id", "from_assignment_id",
                               "to_assignment_id", "requested_at", "reason", "status",
                               "decided_at"],
       [(c["req_id"], c["rid"], c["from_id"], c["to_id"], c["requested"], c["reason"],
         c["status"], c["decided"]) for c in changes])
