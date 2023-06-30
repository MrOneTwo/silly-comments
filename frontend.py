from flask import Flask, flash, request, redirect, url_for
from werkzeug.utils import secure_filename
from pathlib import Path
from jinja2 import Environment, BaseLoader
import yaml
import ulid

import os
import subprocess
import re
import concurrent.futures
import threading
from datetime import date, datetime
import logging, logging.config
from enum import IntEnum, unique


COMMENTS_DIR = "comments"
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
            'handlers': ['log_file'],
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
        <div style="grid-row: 1" id="comments" hx-get="{{ prefix }}" hx-vals='{"for": "article_slug"}' hx-swap="innerHTML" hx-trigger="load">
        </div>

        <div style="grid-row: 2; padding-bottom: 100px;">
            <form hx-post="{{ prefix }}" hx-vals='{"for": "article_slug"}' hx-target="#comments" fenctype=multipart/form-data>
                <input type="text" id="comment_contact" name="comment_contact" placeholder="Name, e-mail" required></input><br>
                <textarea id="comment" name="comment" placeholder="Comment..." required></textarea><br>
                <input id="submit" class="custom-file-upload" type=submit value=Submit>
            </form>
        </div>

    </div>
</body>
</html>
'''

html_comments = '''
    {%- for c in comments %}
    <div class="comment">
        <div style="display: flex">
            <div class="comment_date">
                <span>{{ c.created_on_dt.date() }}</span>
                <span>{{ '%02d' % c.created_on_dt.hour }}</span><span>{{ '%02d' % c.created_on_dt.minute }}</span><span class="comment-date-seconds">{{ '%02d' % c.created_on_dt.second }}</span>
            </div>
            <div class="comment_author">
                {{ c.created_by }}
            </div>
        </div>
        {%- for p in c.paragraphs %}
        <p>
            {{ p }}
        </p>
        {%- endfor %}
    </div>
    {%- endfor %}
    '''

rtemplate = Environment(loader=BaseLoader).from_string(html_index)
templ_comments = Environment(loader=BaseLoader).from_string(html_comments)

# - end --- HTML functions ------------------------------------------------------------------------

def get_comments_for_slug(slug: str):
    paths = list(Path(COMMENTS_DIR, slug).glob('*.txt'))
    comments = list()
    app_log.info(f"Reading comments from {Path(COMMENTS_DIR, slug)}")
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


def create_new_comment(author: str, comment: str, comment_fname: str, slug: str):
    app_log.info(f"Creating new comment from {author}")

    if not Path(COMMENTS_DIR, slug).exists():
        Path(COMMENTS_DIR, slug).mkdir(parents=True)

    p = Path(COMMENTS_DIR, slug, comment_fname).with_suffix('.txt')

    try:
        with p.open(mode='x') as new_comment_file:
            new_comment_file.write(author)
            new_comment_file.write("\n\n")
            new_comment_file.write(comment)
            new_comment_file.write("\n")
            app_log.info(f"Comment saved to {p}")
    except FileExistsError:
        app_log.error(f"File {p} already exists, skipping comment!")


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'GET':
        return rtemplate.render(prefix=URL_PREFIX)

        # I guess this could be a way to disable rendering an entire website.
        # So a release mode solution?
        # return redirect(url_for(URL_PREFIX))


@app.route(URL_PREFIX, methods=['GET', 'POST'])
def comments_for_article():
    which = request.values.get('for', None)
    if request.method == 'GET':
        if which:
            comments = get_comments_for_slug(which)
        else:
            comments = ""
        ret = templ_comments.render(comments=comments)
        return ret
    if request.method == 'POST':
        app_log.info(f"Got form: {request.form.to_dict()}")
        author = request.form.to_dict().get('comment_contact').strip()

        try:
            author_name, author_email = author.split(',')
            comment = request.form.to_dict().get('comment').strip()
            comment_fname = str(ulid.new())
            create_new_comment(author_name, comment, comment_fname , which)
        except ValueError:
            app_log.error(f"Failed to extract the author's name and email from {request.form.to_dict()}")

        comments = get_comments_for_slug(which)
        ret = templ_comments.render(comments=comments)
        return ret
