import pytest

from lewis_api.agent.seniority import classify_relationship, filter_by_seniority


@pytest.mark.parametrize(
    "user_level,job_level,expected",
    [
        ("mid", "mid", "exact"),
        ("mid", "senior", "adjacent_above"),
        ("mid", "new_grad", "exclude"),  # one tier below
        ("mid", "staff", "exclude"),  # two tiers above
        ("mid", "intern", "exclude"),  # two tiers below
        ("mid", "unknown", "unrestricted"),
        (None, "intern", "unrestricted"),
        ("staff", "staff", "exact"),  # top of ladder, no tier above
        ("Senior", "senior", "exact"),  # case variance normalized
        ("mid", "New Grad", "exclude"),  # spaces normalized, one tier below
        ("senior-level", "senior", "unrestricted"),  # not a real ladder value
    ],
)
def test_classify_relationship(user_level, job_level, expected):
    assert classify_relationship(user_level, job_level) == expected


def test_filter_by_seniority_drops_only_excluded():
    ranked = [
        {"external_id": "1", "seniority": "mid"},  # exact -> kept
        {"external_id": "2", "seniority": "senior"},  # adjacent above -> kept
        {"external_id": "3", "seniority": "new_grad"},  # one below -> dropped
        {"external_id": "4", "seniority": "staff"},  # two above -> dropped
        {"external_id": "5", "seniority": "unknown"},  # kept
    ]
    out = filter_by_seniority(ranked, {"seniority": "mid"})
    assert [j["external_id"] for j in out] == ["1", "2", "5"]


def test_filter_by_seniority_noop_when_prefs_unset():
    ranked = [{"external_id": "1", "seniority": "intern"}]
    out = filter_by_seniority(ranked, {})
    assert out == ranked
