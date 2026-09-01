import math
import uuid

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    return 2*R*math.asin(math.sqrt(a))

# mock NOTAM crane at 18.53,73.84 radius 1km alt 100m — replace with DB lookup later
MOCK_NOTAMS = [
    {"id": "NOTAM 09/03", "lat": 18.53, "lon": 73.84, "radius_km": 1.0, "max_alt": 100, "text": "Crane 100m at Pune site 18.53,73.84 radius 1km"},
]

def validate_flight(lat: float, lon: float, alt: int):
    """Check DGCA 120m AGL + NOTAM crane. Returns {violation, reason, notam_id}"""
    if alt > 120:
        return {"violation": True, "reason": "DGCA CAR §7: Micro max 120m AGL breached", "notam_id": "DGCA §7"}
    for n in MOCK_NOTAMS:
        d = haversine_km(lat, lon, n["lat"], n["lon"])
        if d <= n["radius_km"] and alt > n["max_alt"]:
            return {"violation": True, "reason": f"{n['id']} crane {n['max_alt']}m within {d:.2f}km — reduce to {n['max_alt']-20}m", "notam_id": n["id"]}
    return {"violation": False, "reason": "clear", "notam_id": None}

def check_notam(lat: float, lon: float, radius_km: float = 1.0):
    out = []
    for n in MOCK_NOTAMS:
        if haversine_km(lat, lon, n["lat"], n["lon"]) <= radius_km:
            out.append(n)
    return out

def create_ticket(issue: str, severity: str, drone_id: str, notam_id: str = None, flight_time: str = None):
    """Idempotent key = hash(flight_id + window + query) — CineFund SETNX transplant, TTL 24h
    Key design: f"ticket:dedupe:{drone_id}:{notam_id or hash(issue)}:{window}" window = flight_time//3600 or date"""
    import hashlib, time as _t
    window = flight_time or str(int(_t.time()//86400))  # daily window — prevents duplicate ticket same NOTAM same day
    raw = f"{drone_id}|{notam_id or issue[:30]}|{window}"
    key = f"ticket:dedupe:{hashlib.sha256(raw.encode()).hexdigest()[:12]}"
    ttl = 86400  # 24h — NOTAM validity window
    if not hasattr(create_ticket, "_seen"):
        create_ticket._seen = {}
    # check TTL expiry mock
    now = _t.time()
    if key in create_ticket._seen:
        ts, tid = create_ticket._seen[key]
        if now - ts < ttl:
            return {"ticket_id": None, "deduped": True, "key": key, "ttl": ttl}
    tid = f"T-{uuid.uuid4().hex[:4].upper()}"
    create_ticket._seen[key] = (now, tid)
    return {"ticket_id": tid, "deduped": False, "key": key, "ttl": ttl, "issue": issue, "severity": severity, "window": window}
