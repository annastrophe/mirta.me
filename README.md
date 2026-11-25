# mirta.me

Static site for Mirta Syazanna (PropNex), in the Homes with AIMS brand. Hosted on GitHub Pages.

## Pages
- `index.html` – home (`/`)
- `property-updates.html` – `/property-updates` (market data + articles)
- `post/*.html` – the three Upgrade Guides (`/post/<slug>`). The old Malay-families URL redirects to the new evergreen one.

## Weekly market data
`.github/workflows/update-market.yml` runs every Monday 08:17 SGT. It runs
`scripts/update_market.py`, which pulls HDB resale data for the North, North-East and East
towns (set in `REGIONS` at the top of the script) from data.gov.sg, writes `data/market.json`, and rewrites the blocks between the
`<!-- MARKET... -->` markers in `index.html` and `property-updates.html`.
Run it any time from the Actions tab ("Run workflow").

Optional: add a free data.gov.sg API key as the repo secret `DATA_GOV_SG_API_KEY`.

## Going live
1. Push this folder to a new GitHub repo.
2. Settings → Pages → Deploy from branch → `main` / root.
3. Settings → Pages → Custom domain: `mirta.me` (the `CNAME` file is already here). Tick "Enforce HTTPS" once it appears.
4. At the domain registrar, point `mirta.me` to GitHub Pages: A records 185.199.108.153, 185.199.109.153, 185.199.110.153, 185.199.111.153, and `www` CNAME to `<username>.github.io`.
5. Cancel the old GoHighLevel site only after the new one loads on mirta.me.
6. In Search Console, submit `https://mirta.me/sitemap.xml`.
