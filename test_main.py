import frontend as ft
import ulid
from pathlib import Path

def test_load_comments():
    comments = ft.get_comments_for_slug("example", [".",])
    assert len(comments) == 1

def test_create_comment():
    comments = ft.get_comments_for_slug("example", [".",])

    comment_fname = str(ulid.new())
    path = ft.create_new_comment("Leon", "leon@gmail.com", "Do you dream, Elliot?", comment_fname, ["example",])

    comments = ft.get_comments_for_slug("example", [".",])

    assert comments[1].created_by == "Leon"
    assert len(comments) == 2

    # Cleanup after yourself!
    path.unlink()

def test_comment_api_from_path():
    p = Path("comments", "example", "deeper", "01H7A86Y8EM4DM3FM25EWPHB8W.txt")
    c = ft.Comment.from_path(p)
    print(c)

