from lewis_api.agent.sources.seed import load_seed

_VALID_INDUSTRIES = {
    "fintech",
    "healthtech",
    "devtools",
    "cybersecurity",
    "ecommerce",
    "enterprise_saas",
    "consumer",
    "ai_ml",
    "biotech",
    "media_entertainment",
    "real_estate",
    "logistics_supply_chain",
    "gaming",
    "edtech",
    "hardware_robotics",
    "climate_energy",
    "unknown",
}


def test_seed_list_is_large_and_well_formed():
    entries = load_seed()
    assert len(entries) >= 250  # generous floor below the 300 target
    for e in entries:
        assert e.source in ("greenhouse", "ashby")
        assert e.board_token
        assert e.company
        assert e.industry in _VALID_INDUSTRIES


def test_seed_list_has_industry_diversity():
    entries = load_seed()
    industries = {e.industry for e in entries if e.industry != "unknown"}
    assert len(industries) >= 6  # not all companies dumped into one bucket
