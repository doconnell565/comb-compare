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

Every push to `main` runs `.github/workflows/deploy.yml`, which deploys with wrangler. It needs one repository secret, `CLOUDFLARE_API_TOKEN`, created at https://dash.cloudflare.com/profile/api-tokens with the "Edit Cloudflare Workers" template.
