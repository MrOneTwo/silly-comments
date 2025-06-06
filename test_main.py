import frontend as ft
import ulid

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
