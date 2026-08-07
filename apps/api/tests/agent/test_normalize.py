from lewis_api.agent.normalize import job_key, normalize_url


def test_normalize_strips_query_fragment_and_trailing_slash():
    assert normalize_url("HTTP://Jobs.ashbyhq.com/ramp/abc/?utm_source=x#top") == (
        "https://jobs.ashbyhq.com/ramp/abc"
    )


def test_normalize_forces_https_lowercases_host_only():
    assert normalize_url("http://Boards.Greenhouse.io/gitlab/jobs/123") == (
        "https://boards.greenhouse.io/gitlab/jobs/123"
    )


def test_job_key_uses_normalized_url():
    job = {"url": "https://jobs.ashbyhq.com/ramp/abc/?x=1"}
    assert job_key(job) == "https://jobs.ashbyhq.com/ramp/abc"
