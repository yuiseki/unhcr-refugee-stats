# unhcr-refugee-stats

A reproducible collection of the UNHCR Refugee Population Statistics Database
(the data behind the Refugee Data Finder): counts of refugees, asylum-seekers,
internally displaced people of concern to UNHCR, stateless people, asylum
applications and decisions, solutions (returns, resettlement, naturalisation)
and age/sex breakdowns, for every year and every pair of country of origin and
country of asylum, from 1951 onwards.

## Source

- API: <https://api.unhcr.org/population/v1/> (no key), documented at
  <https://api.unhcr.org/docs/refugee-statistics.html>.
- Only the public API is used. The www.unhcr.org pages are not scraped (the
  website terms forbid it) and the HDX copies are not used.
- For each kind the API's full-period download is taken
  (`download=true&coo_all=true&coa_all=true`, years from the API's `years`
  endpoint). It returns a zip holding the data CSV and `footnotes.csv`, kept
  as served. The CSV identifies countries by name and ISO3 code only;
  `countries.json` (the API's country list) maps ISO3 to UNHCR's own codes.
- The database is overwritten twice a year (end-year figures in June,
  mid-year figures around December, with revisions to past years) and the API
  cannot serve older releases, so the version is the fetch date (UTC).

## Licence

The datasets are licensed under the Creative Commons Attribution 4.0
International licence, subject to UNHCR's Terms of Use for Datasets
(<https://www.unhcr.org/what-we-do/data-and-publications/data-and-statistics/terms-use-datasets>).
Attribute as "UNHCR Refugee Population Statistics Database" and link the
Terms of Use. Item 6 of those terms says that data provided by third parties
may carry other conditions; the IDMC and UNRWA series are therefore kept in
their own folder.

## Run

```sh
uv run python scripts/01_download.py   # fetch into data/raw/<YYYY-MM-DD>/
uv run python scripts/02_verify.py     # re-hash, test zips, count CSV rows
uv run python -m pytest
```

`01_download.py` skips files already recorded in the manifest with a matching
sha256. Each downloaded zip must contain exactly as many data rows as the API
states for the same query (`maxPages` at `limit=1`).

## Layout

```
data/raw/<YYYY-MM-DD>/
  MANIFEST.json              url, bytes, sha256, last_modified, fetched_at,
                             year range, row count and totals the API states
  unhcr/
    population.zip           population.csv + footnotes.csv
    asylum-applications.zip
    asylum-decisions.zip
    solutions.zip
    demographics.zip
    countries.json           API country list (UNHCR code, ISO3, names, regions)
  third-party/
    idmc.zip                 IDMC internal displacement figures
    unrwa.zip                UNRWA registered Palestine refugees
scripts/
  01_download.py
  02_verify.py
tests/
```
