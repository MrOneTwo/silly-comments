## Silly comments

Comment system for your website
Using *flask* and *htmx* to create and serve comments.

Why silly? Because this implementation is as naive as I could make it.
Comments are just files. I use [ULID](https://github.com/ulid/spec)
for the comments' file names (they're unique and encode the creation
timestamp).

I want this application to be simple enough that anyone can start it,
without asking for a Docker image. Low bar, I know.

```sh
python3 -m venv my_venv
source my_venv/bin/activate
python3 -m pip install -r requirements.txt
./cmd.sh run
```
