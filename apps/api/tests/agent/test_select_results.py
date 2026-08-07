from lewis_api.agent.select_results import select_results


def _job(id_, company, score, seniority="unknown"):
    return {
        "external_id": id_,
        "company": company,
        "score": score,
        "seniority": seniority,
    }


def test_company_cap_enforced():
    ranked = [
        _job("1", "Acme", 99),
        _job("2", "Acme", 98),
        _job("3", "Acme", 97),  # would be 3rd Acme -> skipped
        _job("4", "Beta", 50),
    ]
    out = select_results(ranked, {}, max_results=4)
    assert [j["external_id"] for j in out] == ["1", "2", "4"]


def test_adjacent_tier_cap_enforced():
    ranked = [
        _job("1", "A", 99, "senior"),
        _job("2", "B", 98, "senior"),
        _job("3", "C", 97, "senior"),
        _job("4", "D", 96, "senior"),  # 4th adjacent-above -> skipped
        _job("5", "E", 50, "mid"),  # exact match, doesn't consume the cap
    ]
    out = select_results(ranked, {"seniority": "mid"}, max_results=5)
    assert [j["external_id"] for j in out] == ["1", "2", "3", "5"]


def test_prefers_highest_score_among_eligible():
    ranked = [_job("2", "B", 95), _job("1", "A", 90), _job("3", "C", 80)]
    out = select_results(ranked, {}, max_results=2)
    assert [j["external_id"] for j in out] == ["2", "1"]


def test_stops_at_max_results():
    ranked = [_job(str(i), f"Co{i}", 100 - i) for i in range(10)]
    out = select_results(ranked, {}, max_results=3)
    assert len(out) == 3
