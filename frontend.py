from flask import Flask, flash, request, redirect, url_for, Response
from werkzeug.utils import secure_filename
from pathlib import Path
from jinja2 import Environment, BaseLoader, DictLoader
import ulid

import os
import subprocess
import re
import concurrent.futures
import threading
import time
from datetime import date, datetime
import logging, logging.config
from enum import IntEnum, unique
from importlib import reload

import params
import notifier

# I currently assume that NGINX will proxy to /. The HTMX
# requests have to send requests to correct URL though.
# That's what URL_PREFIX is for.
URL_PREFIX = "/comments"


def reload_params():
    global params
    def get_ts() -> int:
        return int(Path("params.py").stat().st_mtime)

    period = 60 * 10
    timestamp = get_ts()

    app_log.info(f"I'll reload params.py every {period}s")

    time.sleep(5)

    while True:
        timestamp_fresh = get_ts()
        if timestamp_fresh > timestamp:
            app_log.info("Reloading params.py")
            timestamp = timestamp_fresh
            params = reload(params)

        time.sleep(period)


def create_app():
    app = Flask(__name__, static_url_path="/static")

    thr_params_reload = threading.Thread(target=reload_params, daemon=True)
    thr_params_reload.start()

    @app.route("/", methods=["GET", "POST"])
    def index():
        if request.method == "GET":
            return env.get_template("templ_index").render(remote=params.REMOTE_URL)

            # I guess this could be a way to disable rendering an entire website.
            # So a release mode solution?
            # return redirect(url_for(URL_PREFIX))
            return "no"


    @app.route("/comments", methods=["GET", "POST", "OPTIONS"])
    def comments_for_article():
        app_log.info(request.args)

        # Let's handle the preflight request.
        if request.method == "OPTIONS":
            ret = Response("")
            ret.headers["Access-Control-Allow-Origin"] = "*"
            ret.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT"
            # This was important to set to '*'. 'Content-Type' was used before
            # and it didn't work.
            ret.headers["Access-Control-Allow-Headers"] = "*"
            ret.headers["Access-Control-Max-Age"] = "300"
            return ret

        which = request.values.get("for", None)
        app_log.info(f"request values: {request.values}")

        # The request path might look like ?for=project/a_project, to support putting
        # comments in a more complex filesystem structure.
        which_list = [x for x in which.split("/") if len(x) > 0]
        which = which_list[-1]
        which_path = which_list[:-1]
        app_log.info(f"path: {Path(*which_path)}, slug: {which}")

        if which in params.KNOWN_SLUGS:
            if request.method == "GET":
                if which:
                    comments = get_comments_for_slug(which, which_path)
                else:
                    comments = ""
                # Need to use the remote URL, since the comment submit form needs to
                # know where to send the request.
                ret = Response(
                    env.get_template("templ_comments").render(
                        remote=params.REMOTE_URL,
                        endpoint=URL_PREFIX,
                        which="/".join(which_list),
                        comments=comments,
                    )
                )
                # Needs to be present in OPTIONS response and here.
                ret.headers["Access-Control-Allow-Origin"] = "*"
                return ret

            if request.method == "POST":
                form = request.form.to_dict()
                app_log.info(f"Got form: {form}")
                author = form.get("comment_author").strip()
                author_contact = form.get("comment_contact").strip()

                notifier.notify(f"{form}")

                try:
                    # split with value 1 will create two elements.
                    comment = form.get("comment").strip()
                    comment_fname = str(ulid.new())
                    create_new_comment(
                        author, author_contact, comment, comment_fname, which_list
                    )
                except ValueError:
                    app_log.error(
                        f"Failed to extract the author's name and email from {form}"
                    )

                comments = get_comments_for_slug(which, which_path)
                ret = Response(
                    env.get_template("templ_comments").render(
                        remote=params.REMOTE_URL,
                        endpoint=URL_PREFIX,
                        which="/".join(which_list),
                        comments=comments
                    )
                )
                # Needs to be present in OPTIONS response and here.
                ret.headers["Access-Control-Allow-Origin"] = "*"
                return ret

        else:
            app_log.error(f"Slug '{which}' not known, check params.py!")
            return "no"

    return app

logging.config.dictConfig(
    {
        "version": 1,
        "formatters": {
            "default": {
                "format": "[%(asctime)s] %(levelname)s in %(module)s: %(message)s",
            }
        },
        "handlers": {
            "wsgi": {
                "class": "logging.StreamHandler",
                "stream": "ext://flask.logging.wsgi_errors_stream",
                "formatter": "default",
            },
            "log_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": "frontend.log",
                "formatter": "default",
                "mode": "a",
                "maxBytes": 10 * 1024,
                "backupCount": 1,
            },
        },
        "loggers": {
            "root": {"level": "INFO", "handlers": ["wsgi"]},
            "my_logger": {
                "level": "INFO",
                "handlers": ["wsgi", "log_file"],
                "propagate": False,
            },
        },
    }
)

app_log = logging.getLogger("my_logger")
app_log.info("------------------ Started the app ------------------")


class Comment:
    def __init__(self):
        self.created_on_ts = 0
        self.created_on_dt = 0
        self.created_by = ""
        self.created_by_contact = ""
        self.paragraphs = list()


# - HTML functions --------------------------------------------------------------------------------

# The \ avoids the empty line.
html_index = """\
<!doctype html>
<head>
    <meta charset="utf-8">
    <link rel="stylesheet" href="static/main.css">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Source+Serif+Pro&display=swap" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400&family=Source+Serif+Pro&display=swap" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Rubik:wght@900&display=swap" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Rubik&display=swap" rel="stylesheet">
    <script src="https://unpkg.com/htmx.org@1.8.0"></script>

    <script>
      // This is a very small function which is supposed to grab the changed
      // value from an input elements and copy it onto label element.
      function update_name() {
        var from = arguments[0];
        var to = arguments[1];
        to.innerHTML = from.files[0].name;
      }
    </script>

    <title>Silly comments demo...</title>

</head>
<body>
    <div class="wrapper">

        <div class="left" style="grid-row: 1; margin-top: 0em;">
            <p style="margin-top: 0em;">
            Just wanted to make a comment system...
            </p>

            </ul>
        </div>

        <!-- swap self for comments, for this article -->
        <div style="grid-row: 1" hx-get="{{ remote }}/comments" hx-vals='{"for": "example"}' hx-swap="innerHTML" hx-trigger="load">
        </div>

    </div>
</body>
</html>
"""

"""
    <link rel="stylesheet" href="static/silly.css">
"""
html_comments = """\
<div id="comments">
    <div class="comments">
    {%- import 'templ_comment' as comment -%}
    {%- for c in comments %}
        {{ comment.comment(c) -}}
    {%- endfor -%}
    </div>

    <div class="comment-submit">
        <form hx-post="{{ remote }}/{{ endpoint }}" hx-vals='{"for": "{{ which }}" }' hx-target="#comments" hx-swap="outerHTML" enctype="multipart/form-data">
            <input type="text" id="comment_author" name="comment_author" placeholder="Name" required><br>
            <input type="text" id="comment_contact" name="comment_contact" placeholder="e-mail or other contact info"><br>
            <textarea id="comment" name="comment" placeholder="Comment..." required></textarea><br>
            <button id="submit" class="custom-file-upload" type="submit">Submit</button>
        </form>
    </div>
</div>
"""

load = DictLoader(
    {
        "templ_comments": html_comments,
        "templ_index": html_index,
        "templ_comment": """
        {% macro comment(cobject) -%}
        <div class="comment">
            <div class="comment-meta">
                <div class="comment-author">
                    <span>{{ cobject.created_by | e }}</span>
                    {%- if cobject.created_by_contact | length -%}
                    <span>,</span>
                    <span>{{ cobject.created_by_contact | e }}</span>
                    {%- endif -%}
                </div>
                <div class="comment-date">
                    <span>{{ cobject.created_on_dt.date() }}</span>
                    <span>{{ '%02d' % cobject.created_on_dt.hour }}</span><span>{{ '%02d' % cobject.created_on_dt.minute }}</span><span class="comment-date-seconds">{{ '%02d' % cobject.created_on_dt.second }}</span>
                </div>
            </div>
            <div class="comment-content">
            {%- for p in cobject.paragraphs %}
            <p>
                {{ p | e }}
            </p>
            {%- endfor %}
            </div>
        </div>
        {%- endmacro %}
        """
    }
)
env = Environment(loader=load)

# - end --- HTML functions ------------------------------------------------------------------------


def get_comments_for_slug(slug: str, path: list = []):

    """
    Parameters
    ----------
    slug : str
        The leaf directory name, which stores the comment files.
    path : list
        List of directories that build the path to the slug directory.
        There's params.COMMENTS_DIR prepended to that list.
    """
    paths = list(Path(params.COMMENTS_DIR, *path, slug).glob("*.txt"))
    comments = list()
    app_log.info(f"Reading comments from {Path(params.COMMENTS_DIR, slug)}")
    app_log.info(f"{paths}")

    for comment_file in paths:
        # I assume that a comment paragraph can be split over multiple lines.
        # Need to concat those lines but still keep the comment split into
        # paragraphs.
        comment_raw = comment_file.read_text()

        comment_paragraphs = list()
        for paragraph in [x.strip() for x in comment_raw.split("\n\n")]:
            comment_paragraphs.append(paragraph.replace("\n", ""))

        c = Comment()
        # The ULID generates a 26 char long hashes.
        if len(comment_file.stem) == 26:
            c.created_on_ts = ulid.parse(comment_file.stem).timestamp().int
            c.created_on_dt = datetime.fromtimestamp(c.created_on_ts / 1000)
        else:
            app_log.warn(f"Skipping file {comment_file} (len {len(comment_file.stem)})")
            continue

        author = comment_paragraphs[0].split(",")
        if len(author) == 0:
            c.created_by = comment_paragraphs[0]
        elif len(author) == 1:
            c.created_by = author[0]
        elif len(author) == 2:
            c.created_by = author[0]
            c.created_by_contact = author[1]
        c.paragraphs = comment_paragraphs[1:]

        comments.append(c)

    # TODO(michalc): might be better to move this to when we create a new comment.
    comments = sorted(comments, key=lambda c: c.created_on_ts)

    return comments


def create_new_comment(
    author_name: str,
    author_contact: str,
    comment: str,
    comment_fname: str,
    path_list: list,
):
    app_log.info(f"Creating new comment:")
    app_log.info(f"  {author_name}")
    app_log.info(f"  {author_contact}")
    app_log.info(f"  {path_list}")
    app_log.info(f"  {comment_fname}")

    if not Path(params.COMMENTS_DIR, *path_list).exists():
        Path(params.COMMENTS_DIR, *path_list).mkdir(parents=True)

    p = Path(params.COMMENTS_DIR, *path_list, comment_fname).with_suffix(".txt")

    try:
        with p.open(mode="x") as new_comment_file:
            new_comment_file.write(f"{author_name},{author_contact}\n")
            new_comment_file.write("\n")
            new_comment_file.write(comment)
            new_comment_file.write("\n")
            app_log.info(f"Comment saved to {p}")
    except FileExistsError:
        app_log.error(f"File {p} already exists, skipping comment!")

    return p
