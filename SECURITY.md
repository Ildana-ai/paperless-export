# Security

paperless-export talks to one host: the paperless-ngx instance you point it at with
`PAPERLESS_URL`, using the token you supply with `PAPERLESS_TOKEN`. It never contacts anywhere
else, and it is read-only against that instance — no endpoint that writes is ever called.

- **CLI and `--serve`** run on your own machine. `--serve` binds `127.0.0.1` only, for one browser
  session, and the token never enters the browser.
- **The static HTML page** (opened from disk, with no server) makes that same request straight
  from your browser to your instance. It needs `PAPERLESS_CORS_ALLOWED_HOSTS` set on your instance
  to the origin you're opening it from, and your token is typed into the page for that session
  only — it is never saved, never sent anywhere but your instance, and gone when the tab closes.

Plain `http` is only ever used against your own network — loopback, a private address, or a
`.local` name — with a one-line warning; a public host is refused unless you pass `--insecure`
yourself.

## Reporting a problem

Email **hello@ildana.ai**. Please include the paperless-ngx version and, if you can, a sanitized
saved view or filter that reproduces it. You will get a reply; a confirmed issue is fixed in a new
release and credited in the release notes if you want it to be.

## What to expect from a download

Get the code and the static page (`front.html`) only from this repository's
[releases](https://github.com/Ildana-ai/paperless-export/releases). A copy obtained anywhere else
may have been altered.
