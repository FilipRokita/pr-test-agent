import json

from test_agent import github, report


class FakeGh:
    """Records `gh api` calls and answers the comment listing from a canned list."""

    def __init__(self, comments):
        self.comments = comments
        self.calls = []

    def __call__(self, args, body=None):
        self.calls.append((args, body))
        if args[0] == "api" and "--paginate" in args:
            return json.dumps([self.comments])
        return "{}"


def _comment(cid, login, text):
    return {"id": cid, "user": {"login": login}, "body": text}


def test_a_new_comment_is_created_when_none_exists():
    gh = FakeGh([_comment(1, "someone", "hello")])
    github.upsert_comment("o/r", 7, report.MARKER + "\nbody", run=gh)
    method_calls = [c for c in gh.calls if "--paginate" not in c[0]]
    assert len(method_calls) == 1
    assert "repos/o/r/issues/7/comments" in method_calls[0][0]
    assert "POST" in method_calls[0][0]


def test_the_existing_bot_comment_is_edited_in_place():
    gh = FakeGh([_comment(1, "someone", "hello"), _comment(42, "github-actions[bot]", report.MARKER + "\nold")])
    github.upsert_comment("o/r", 7, report.MARKER + "\nnew", run=gh)
    method_calls = [c for c in gh.calls if "--paginate" not in c[0]]
    assert "repos/o/r/issues/comments/42" in method_calls[0][0]
    assert "PATCH" in method_calls[0][0]


def test_a_user_who_copies_the_marker_cannot_take_over_the_comment():
    gh = FakeGh([_comment(5, "mallory", report.MARKER + "\nfake")])
    github.upsert_comment("o/r", 7, report.MARKER + "\nreal", run=gh)
    method_calls = [c for c in gh.calls if "--paginate" not in c[0]]
    assert "POST" in method_calls[0][0]
    assert "comments/5" not in " ".join(method_calls[0][0])


def test_the_body_is_sent_as_data_not_on_the_command_line():
    gh = FakeGh([])
    github.upsert_comment("o/r", 7, report.MARKER + "\n$(rm -rf /) `x`", run=gh)
    args, body = [c for c in gh.calls if "--paginate" not in c[0]][0]
    assert "rm -rf" not in " ".join(args)
    assert json.loads(body)["body"].endswith("`x`")


def test_the_bot_comment_body_is_found_for_reading_the_previous_state():
    gh = FakeGh([_comment(1, "someone", report.MARKER + " fake"), _comment(2, "github-actions[bot]", report.MARKER + "\nreal")])
    assert github.bot_comment_body("o/r", 7, run=gh).endswith("real")
    assert github.bot_comment_body("o/r", 7, run=FakeGh([])) is None
