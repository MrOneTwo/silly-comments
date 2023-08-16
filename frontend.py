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
from datetime import date, datetime
import logging, logging.config
from enum import IntEnum, unique

import params

# I currently assume that NGINX will proxy to /. The HTMX
# requests have to send requests to correct URL though.
# That's what URL_PREFIX is for.
URL_PREFIX = "/silly"

app = Flask(__name__,
            static_url_path='/static')

logging.config.dictConfig({
    'version': 1,
    'formatters': {
        'default': {'format': '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',}
    },
    'handlers': {
        'wsgi': {
            'class': 'logging.StreamHandler',
            'stream': 'ext://flask.logging.wsgi_errors_stream',
            'formatter': 'default'
        },
        'log_file': {
            'class': 'logging.FileHandler',
            'filename': 'frontend.log',
            'formatter': 'default'
        },
    },
    'loggers': {
        'root': {
            'level': 'INFO',
            'handlers': ['wsgi']
        },
        'my_logger': {
            'level': 'INFO',
            # 'handlers': ['log_file'],
            'handlers': ['wsgi'],
            'propagate': False
        }
    }
})

app_log = logging.getLogger('my_logger')
app_log.info("------------------ Started the app ------------------")


class Comment():
    def __init__(self):
        self.created_on_ts = 0
        self.created_on_dt = 0
        self.created_by = ""
        self.created_by_contact = ""
        self.paragraphs = list()


# - HTML functions --------------------------------------------------------------------------------

# The \ avoids the empty line.
html_index = '''\
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
        <div style="grid-row: 1" id="comments" hx-get="{{ prefix }}/comments" hx-vals='{"for": "example"}' hx-swap="innerHTML" hx-trigger="load">
        </div>

    </div>
</body>
</html>
'''

html_comments = '''\
<link rel="stylesheet" href="static/silly.css">

<div class="comments">
    {%- for c in comments %}
    <div class="comment">
        <div class="comment-meta">
            <div class="comment-author">
                <span>{{ c.created_by }}</span>
                <span>{{ c.created_by_contact }}</span>
            </div>
            <div class="comment-date">
                <span>{{ c.created_on_dt.date() }}</span>
                <span>{{ '%02d' % c.created_on_dt.hour }}</span><span>{{ '%02d' % c.created_on_dt.minute }}</span><span class="comment-date-seconds">{{ '%02d' % c.created_on_dt.second }}</span>
            </div>
        </div>
        <div class="comment-content">
        {%- for p in c.paragraphs %}
        <p>
            {{ p }}
        </p>
        {%- endfor %}
        </div>
    </div>
    {%- endfor %}
</div>

<div class="comment-submit">
    <form hx-post="/comments" hx-vals='{"for": {{ which }} }' hx-target="#comments" fenctype="multipart/form-data">
        <input type="text" id="comment_author" name="comment_author" placeholder="Name" required><br>
        <input type="text" id="comment_contact" name="comment_contact" placeholder="e-mail or other contact info"><br>
        <textarea id="comment" name="comment" placeholder="Comment..." required></textarea><br>
        <button id="submit" class="custom-file-upload" type="submit">Submit</button>
    </form>
</div>
'''

load = DictLoader(
    {"templ_comments": html_comments,
     "templ_index": html_index,
    }
)
env = Environment(loader=load)

# - end --- HTML functions ------------------------------------------------------------------------

def get_comments_for_slug(slug: str, path: list=[]):
    paths = list(Path(params.COMMENTS_DIR, *path, slug).glob('*.txt'))
    comments = list()
    app_log.info(f"Reading comments from {Path(params.COMMENTS_DIR, slug)}")
    app_log.info(f"{paths}")

    for comment_file in paths:
        # I assume that a comment paragraph can be split over multiple lines.
        # Need to concat those lines but still keep the comment split into
        # paragraphs.
        comment_raw = comment_file.read_text()
        # Empty lines will show up as zero len string elements.
        comment_raw_list = comment_raw.split('\n')
        comment_raw_list_cleaned_up = list()

        chunk = ""
        # Iterate until there is no next element.
        for i, line in enumerate(comment_raw_list):
            try:
                if line == '':
                    comment_raw_list_cleaned_up.append(chunk)
                    chunk = ""
                    continue
                chunk = chunk + " " + line
            except IndexError:
                break

        c = Comment()
        # The ULID generates a 26 char long hashes.
        if len(comment_file.stem) == 26:
            c.created_on_ts = ulid.parse(comment_file.stem).timestamp().int
            c.created_on_dt = datetime.fromtimestamp(c.created_on_ts / 1000)
        else:
            app_log.warn(f"Skipping file {comment_file} (len {len(comment_file.stem)})")
            continue
        c.created_by = comment_raw_list_cleaned_up[0]
        c.paragraphs = comment_raw_list_cleaned_up[1:]

        comments.append(c)

    # TODO(michalc): might be better to move this to when we create a new comment.
    comments = sorted(comments, key=lambda c: c.created_on_ts)

    return comments


def create_new_comment(author_name: str, author_contact: str, comment: str, comment_fname: str, slug: str):
    app_log.info(f"Creating new comment from {author_name}, {author_contact}")

    if not Path(params.COMMENTS_DIR, slug).exists():
        Path(params.COMMENTS_DIR, slug).mkdir(parents=True)

    p = Path(params.COMMENTS_DIR, slug, comment_fname).with_suffix('.txt')

    try:
        with p.open(mode='x') as new_comment_file:
            new_comment_file.write(f"{author_name},{author_contact}\n")
            new_comment_file.write("\n")
            new_comment_file.write(comment)
            new_comment_file.write("\n")
            app_log.info(f"Comment saved to {p}")
    except FileExistsError:
        app_log.error(f"File {p} already exists, skipping comment!")


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'GET':
        return env.get_template('templ_index').render()

        # I guess this could be a way to disable rendering an entire website.
        # So a release mode solution?
        # return redirect(url_for(URL_PREFIX))
        return "no"


@app.route("/comments", methods=['GET', 'POST', 'OPTIONS'])
def comments_for_article():
    which = request.values.get('for', None)

    # The request path might look like ?for=project/a_project, to support putting
    # comments in a more complex filesystem structure.
    which_list = [x for x in which.split('/') if len(x) > 0 ]
    which = which_list[-1]
    which_path = which_list[:-1]
    app_log.info(f"path: {Path(*which_path)}, slug: {which}")

    if which in params.KNOWN_SLUGS:

        if request.method == 'GET':
            if which:
                comments = get_comments_for_slug(which, which_path)
            else:
                comments = ""
            ret = Response(env.get_template('templ_comments').render(which=which, comments=comments))
            ret.headers['Access-Control-Allow-Origin'] = '*'
            return ret

        if request.method == 'POST':
            form = request.form.to_dict()
            app_log.info(f"Got form: {form}")
            author = form.get('comment_author').strip()
            author_contact = form.get('comment_contact').strip()

            try:
                # split with value 1 will create two elements.
                comment = form.get('comment').strip()
                comment_fname = str(ulid.new())
                create_new_comment(author, author_contact, comment, comment_fname, which)
            except ValueError:
                app_log.error(f"Failed to extract the author's name and email from {form}")

            comments = get_comments_for_slug(which, which_path)
            ret = Response(env.get_template('templ_comments').render(which=which, comments=comments))
            return ret

        # Let's handle the preflight request.
        if request.method == 'OPTIONS':
            ret = Response("")
            ret.headers['Access-Control-Allow-Origin'] = '*'
            ret.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT'
            # This was important to set to '*'. 'Content-Type' was used before
            # and it didn't work.
            ret.headers['Access-Control-Allow-Headers'] = '*'
            ret.headers['Access-Control-Max-Age'] = '300'
            return ret
    else:
        app_log.error(f"Slug '{which}' not known, check params.py!")
        return "no"
