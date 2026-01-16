## Silly comments

Webpage comment system, built on *Flask* and *HTMX*. Silly simple, bare
bones, minimal... well except it's Python.

Why silly? Because this implementation is as naive as I could make it.
Comments are just files. I use [ULID](https://github.com/ulid/spec)
for the comments' file names (they're unique and encode the creation
timestamp).

I want this application to be simple enough that anyone can start it,
without needing a Docker image. Low bar, I know.

If you want to host it on your VPS, you can use the `silly_app.conf`
file as a start for your NGINX configuration.

You can start it with:

```sh
python3 -m venv my_venv
source my_venv/bin/activate
python3 -m pip install -r requirements.txt
./cmd.sh run
```

Or go with the [uv](https://docs.astral.sh/uv/):

```sh
uv sync
uv run flask --app sillysimple.py -p 32168
```
