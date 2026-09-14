# Comb Compare

A single-page music box comb simulator. Load a MIDI file, hear it the way a 30, 50, or 72 tooth comb would play it, select one cylinder rotation, and export a pin map CSV for machining a cylinder.

Everything runs in the browser. There is no backend and nothing is uploaded.

## Develop

    npm install
    npx wrangler dev

## Deploy

    npx wrangler deploy

The page is `public/index.html`. Served as static assets on Cloudflare Workers.

## Push to deploy

The Worker is connected to this repository through Cloudflare Workers Builds. Every push to `main` builds and deploys inside Cloudflare, with no API token stored in GitHub. Manual deploys still work with `npm run deploy`.

## STEP files for the cylinder and tooling

`tools/make_step.py` builds STEP files for the cylinder (with a blind radial hole per pin), the height-stop pin punch, the pin length jig, and a cradle, from a pin map CSV exported by the page and the dimensions in `tools/params.json`.

    /usr/bin/python3.12 -m venv .venv
    .venv/bin/pip install cadquery
    .venv/bin/python tools/make_step.py

Output lands in `tools/out/` with a `SUMMARY.md` of callouts for the shop. The numbers in `params.json` are placeholders until the movement is measured.
