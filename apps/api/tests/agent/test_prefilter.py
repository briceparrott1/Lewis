from lewis_api.agent.prefilter import prefilter


def _job(title, location):
    return {"title": title, "location": location, "description": ""}


def test_required_role_is_hard_filter():
    prefs = {"role_keywords": ["fde"], "required": ["role"], "locations": ["SF"]}
    jobs = [_job("Forward Deployed Engineer (FDE)", "NYC"), _job("Barista", "SF")]
    out = prefilter(jobs, prefs)
    assert len(out) == 1
    assert "Forward" in out[0]["title"]  # non-FDE dropped despite SF match


def test_soft_location_does_not_drop_but_scores():
    prefs = {
        "role_keywords": ["fde"],
        "locations": ["SF"],
        "priorities": ["role", "location"],
    }
    sf = _job("FDE", "San Francisco")
    ny = _job("FDE", "New York")
    out = prefilter([ny, sf], prefs)
    assert next(j["location"] for j in out) == "San Francisco"  # SF ranks first
    assert len(out) == 2  # neither dropped (location is soft)


def test_zero_signal_dropped_and_cap_applies():
    prefs = {"role_keywords": ["fde"]}
    jobs = [_job("Chef", "SF") for _ in range(3)] + [_job("FDE", "SF")]
    out = prefilter(jobs, prefs, cap=2)
    assert all("fde" in j["title"].lower() for j in out)
    assert len(out) == 1
