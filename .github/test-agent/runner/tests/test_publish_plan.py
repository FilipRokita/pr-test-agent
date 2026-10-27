import pytest

from test_agent import publish_plan

CTX = {"should_run": True}
AGENT = {"status": "ok"}
VERIFIED = {"status": "verified", "patch_files": ["backend/tests/test_a.py"]}
NOTHING = {"status": "verified", "patch_files": []}
OPEN = {"number": 12}


def decide(**kw):
    base = dict(ctx=CTX, agent=AGENT, verification=VERIFIED, stacked=None, tip_is_bot=None)
    return publish_plan.decide(**{**base, **kw})


def test_a_verified_proposal_creates_the_stacked_pull_request():
    assert decide()["action"] == "create"


def test_a_verified_proposal_updates_the_open_stacked_pull_request():
    assert decide(stacked=OPEN, tip_is_bot=True)["action"] == "update"


def test_a_branch_without_an_open_pull_request_is_reused_when_the_bot_owns_it():
    assert decide(stacked=None, tip_is_bot=True)["action"] == "create"


def test_human_commits_on_the_test_branch_are_never_overwritten():
    result = decide(stacked=OPEN, tip_is_bot=False)
    assert result["action"] == "blocked" and "human" in result["note"]


def test_a_branch_owned_by_someone_else_blocks_even_without_an_open_pull_request():
    assert decide(stacked=None, tip_is_bot=False)["action"] == "blocked"


def test_no_tests_needed_closes_a_stale_stacked_pull_request():
    result = decide(verification=NOTHING, stacked=OPEN, tip_is_bot=True)
    assert result["action"] == "close" and "no longer needed" in result["reason"]


def test_no_tests_needed_and_no_stacked_pull_request_does_nothing():
    assert decide(verification=NOTHING)["action"] == "keep"


@pytest.mark.parametrize("status", ["failing", "rejected"])
def test_a_proposal_that_did_not_pass_supersedes_the_old_stacked_pull_request(status):
    result = decide(verification={"status": status, "patch_files": []}, stacked=OPEN, tip_is_bot=True)
    assert result["action"] == "close" and "superseded" in result["reason"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"ctx": {"should_run": False}},
        {"agent": None},
        {"agent": {"status": "agent_error"}},
        {"agent": {"status": "skipped_no_credentials"}},
        {"verification": None},
        {"verification": {"status": "error", "patch_files": []}},
    ],
)
def test_infrastructure_problems_and_skips_leave_the_stacked_pull_request_alone(kwargs):
    assert decide(stacked=OPEN, tip_is_bot=True, **kwargs)["action"] == "keep"
