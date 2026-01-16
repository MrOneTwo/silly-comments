import sillysimple as ss
import ulid
from pathlib import Path
import pytest


@pytest.fixture()
def file_cleanup(request):
    """
    Gives me the ability to defer the file cleanup, in the test body, by
    appending the paths to this list.
    """
    paths_to_cleanup = []

    def cleanup():
        for p in paths_to_cleanup:
            p.unlink()

    request.addfinalizer(cleanup)
    return paths_to_cleanup


def test_load_comments():
    comments = ss.get_comments_for_slug("example", [".",])
    assert len(comments) == 1

def test_create_comment(file_cleanup):
    comments = ss.get_comments_for_slug("example", [".",])

    comment_fname = str(ulid.new())
    c = ss.Comment()
    c.created_by = "Leon"
    c.created_by_contact = "leon@gmail.com"
    c.paragraphs = "Do you dream, Elliot?"

    path = c.dump_into_file(["example",], comment_fname)
    file_cleanup.append(path)

    comments = ss.get_comments_for_slug("example", [".",])

    assert comments[1].created_by == "Leon"
    assert len(comments) == 2

def test_comment_api_from_path():
    p = Path("comments", "example", "01H7A86Y8EM4DM3FM25EWPHB8W.txt")
    c = ss.Comment.from_path(p)
    #print(c)

    assert len(c.paragraphs) == 3

def test_comment_api_into_file_author_fail():
    comment_fname = str(ulid.new())

    comment = ss.Comment()
    comment.created_by_contact = "leon@gmail.com"
    comment.paragraphs = ["Do you dream, Elliot?", "You scraping so hard..."]

    assert comment.dump_into_file(["example",], comment_fname) is None

    comments = ss.get_comments_for_slug("example", [".",])

def test_comment_api_into_file(file_cleanup):
    comments = ss.get_comments_for_slug("example", [".",])

    comment_fname = str(ulid.new())

    comment = ss.Comment()
    comment.created_by = "Elliot"
    comment.created_by_contact = "elliot@protonmail.com"
    comment.paragraphs = ["How do I know which one's for me?",]

    result_path = comment.dump_into_file(["example",], comment_fname)
    file_cleanup.append(result_path)

    comments = ss.get_comments_for_slug("example", [".",])

    assert len(comments[-1].paragraphs) == 1
    assert comments[-1].created_by == "Elliot"
