---
license: cc-by-4.0
language:
- en
- fr
tags:
- refugees
- asylum
- forced-displacement
- migration
- statelessness
- official-statistics
- country-pairs
size_categories:
- 100K<n<1M
configs:
- config_name: '2026-10-04.population'
  data_files: parquet/2026-10-04/population.parquet
  default: true
- config_name: '2026-10-04.asylum-applications'
  data_files: parquet/2026-10-04/asylum-applications.parquet
- config_name: '2026-10-04.asylum-decisions'
  data_files: parquet/2026-10-04/asylum-decisions.parquet
- config_name: '2026-10-04.solutions'
  data_files: parquet/2026-10-04/solutions.parquet
- config_name: '2026-10-04.demographics'
  data_files: parquet/2026-10-04/demographics.parquet
- config_name: '2026-10-04.footnotes'
  data_files: parquet/2026-10-04/footnotes.parquet
- config_name: '2026-10-04.countries'
  data_files: parquet/2026-10-04/countries.parquet
---

# unhcr-refugee-stats

A copy of the UNHCR Refugee Population Statistics Database, the data behind
UNHCR's Refugee Data Finder, as its public API served it: for every year and
every pair of country of origin and country of asylum, the number of
refugees, asylum-seekers, internally displaced people of concern to UNHCR,
stateless people and others of concern; asylum applications and decisions;
returns, resettlement arrivals and naturalisations; and an age and sex
breakdown. Figures go back to 1951 for refugees and start later for the
other series.

Source: UNHCR Refugee Population Statistics Database.
Terms of Use for Datasets:
https://www.unhcr.org/what-we-do/data-and-publications/data-and-statistics/terms-use-datasets

CC BY 4.0, under those terms (see Licence). This dataset is not made,
sponsored or endorsed by UNHCR.

## Versions

UNHCR overwrites the database twice a year (end-year figures in June,
mid-year figures around December) and revises past years each time. The API
cannot serve an earlier state, so each fetch is kept as its own version,
named by the date (UTC) it was fetched, and a later fetch is added beside the
earlier ones. A subset is one table of one version, named
`<version>.<table>`.

| subset | rows | years | origins | asylum countries |
|---|---:|---|---:|---:|
| `2026-10-04.population` | 138,893 | 1951 to 2025 | 217 | 196 |
| `2026-10-04.asylum-applications` | 120,597 | 2000 to 2025 | 215 | 186 |
| `2026-10-04.asylum-decisions` | 113,929 | 2000 to 2025 | 211 | 185 |
| `2026-10-04.solutions` | 21,258 | 1959 to 2025 | 189 | 171 |
| `2026-10-04.demographics` | 116,781 | 2001 to 2025 | 217 | 195 |
| `2026-10-04.footnotes` | 658 | | | |
| `2026-10-04.countries` | 232 | | | |

Version 2026-10-04 holds the end-year figures for 2025 published on
2026-06-11. Countries are counted by their ISO code in the CSV.

Under `raw/2026-10-04/` are the files as the API served them, byte for byte:

- `unhcr/population.zip`, `unhcr/asylum-applications.zip`,
  `unhcr/asylum-decisions.zip`, `unhcr/solutions.zip`,
  `unhcr/demographics.zip`: the API's full-period download
  (`yearFrom=1951&yearTo=2027&coo_all=true&coa_all=true&download=true`), each
  holding the data CSV and `footnotes.csv`
- `unhcr/countries.json`: the API's country list
- `MANIFEST.json`: for each file the URL, size, sha256, Last-Modified, fetch
  time, and the row count and totals the API stated for the same query

### What is not here

The Refugee Data Finder also shows figures provided by two other
organisations: internal displacement from the Internal Displacement
Monitoring Centre (IDMC) and registered Palestine refugees from UNRWA. The
API serves them as the `idmc` and `unrwa` series. They were fetched with the
rest but are not published here. Item 6 of UNHCR's Terms of Use for
Datasets says:

> Some datasets and indicators are provided by third parties, and may not be
> shared, redistributed or reused without the consent of the original data
> provider, or may be subject to terms and conditions that are different from
> those described herein.

No consent from IDMC or UNRWA was sought. `MANIFEST.json` still lists the
two files under `third-party/`, because it is the record of the fetch, but
the files themselves are not in this dataset. Get them from the API or from
their providers.

## Files and columns

The Parquet under `parquet/<version>/` is made from the raw files. Column
names are the CSV headings exactly as UNHCR wrote them, including spaces,
capitals and the misspelling `Returned IDPss` (for returned IDPs). No column
was added, renamed or dropped, and rows are in the order of the CSV. Write
the names in double quotes in SQL.

The type of a column comes from a fixed table in
`scripts/03_export_parquet.py`, never from inference:

- `Year` of the five data tables is INTEGER.
- The count columns listed below are BIGINT. The CSV writes `-` where it has
  no figure; that is NULL in the Parquet. Any other value that is not a
  whole number stops the build.
- Everything else is the text of the source.

### population

Stock figures at the end of each year.

| column | type |
|---|---|
| `Year` | INTEGER |
| `Country of origin` | VARCHAR |
| `Country of origin (ISO)` | VARCHAR |
| `Country of asylum` | VARCHAR |
| `Country of asylum (ISO)` | VARCHAR |
| `Refugees under UNHCR's mandate` | BIGINT |
| `Asylum-seekers` | BIGINT |
| `Returned refugees` | BIGINT |
| `IDPs of concern to UNHCR` | BIGINT |
| `Returned IDPss` | BIGINT |
| `Stateless persons` | BIGINT |
| `Others of concern` | BIGINT |
| `Other people in need of international protection` | BIGINT, NULL where the CSV has `-` |
| `Host Community` | BIGINT |

### asylum-applications

| column | type |
|---|---|
| `Year`, `Country of origin`, `Country of origin (ISO)`, `Country of asylum`, `Country of asylum (ISO)` | as in population |
| `Authority` | VARCHAR: `G` government, `J` joint, `U` UNHCR |
| `Application type` | VARCHAR, UNHCR's code |
| `Stage of procedure` | VARCHAR, UNHCR's code |
| `Cases / Persons` | VARCHAR: `C` cases, `P` persons |
| `applied` | BIGINT |

### asylum-decisions

| column | type |
|---|---|
| `Year`, `Country of origin`, `Country of origin (ISO)`, `Country of asylum`, `Country of asylum (ISO)` | as in population |
| `Authority` | VARCHAR: `G`, `J`, `U` as above |
| `Stage of procedure` | VARCHAR, UNHCR's code |
| `Cases / Persons` | VARCHAR: `C` or `P` |
| `Recognized decisions` | BIGINT |
| `Complementary protection` | BIGINT |
| `Rejected decisions` | BIGINT |
| `Otherwise closed` | BIGINT |
| `Total decisions` | BIGINT |

### solutions

Flows during each year.

| column | type |
|---|---|
| `Year`, `Country of origin`, `Country of origin (ISO)`, `Country of asylum`, `Country of asylum (ISO)` | as in population |
| `Returned refugees` | BIGINT, NULL where the CSV has `-` |
| `Resettlement arrivals` | BIGINT, NULL where the CSV has `-` |
| `Naturalisation` | BIGINT, NULL where the CSV has `-` |
| `Returned IDPss` | BIGINT, NULL where the CSV has `-` |

### demographics

| column | type |
|---|---|
| `Year`, `Country of origin`, `Country of origin (ISO)`, `Country of asylum`, `Country of asylum (ISO)` | as in population |
| `Female 0 - 4`, `Female 5 - 11`, `Female 12 - 17`, `Female 18 - 59`, `Female 60`, `Female other`, `Female total` | BIGINT |
| `Male 0 - 4`, `Male 5 - 11`, `Male 12 - 17`, `Male 18 - 59`, `Male 60`, `Male other`, `Male total` | BIGINT |
| `Total` | BIGINT |

### footnotes

UNHCR's notes on particular figures. The five zips carry the same
`footnotes.csv`; this is the one from `population.zip`.

| column | type |
|---|---|
| `Footnote` | VARCHAR |
| `Year` | VARCHAR: a year or a range such as `2018 - 2025` |
| `Country of origin (ISO)` | VARCHAR, NULL where empty |
| `Country of asylum (ISO)` | VARCHAR, NULL where empty |
| `Population type` | VARCHAR: one or more codes such as `REF`, `ASY`, `IDP`, `STA`, `OIP`, separated by commas |

### countries

The API's country list, one row per item, the JSON keys as columns in their
order. JSON null is NULL; an empty string stays empty.

| column | type |
|---|---|
| `0` | INTEGER, 1 in every row; its meaning is not documented |
| `id` | INTEGER, UNHCR's numeric id |
| `code` | VARCHAR, UNHCR's own three-letter code (not ISO) |
| `iso` | VARCHAR, the ISO 3166-1 alpha-3 code the CSVs use |
| `iso2` | VARCHAR |
| `name`, `nameOrigin`, `nameLong`, `nameShort`, `nameFormal`, `nationality` | VARCHAR |
| `majorArea`, `region` | VARCHAR |
| `nameFr`, `majorAreaFr`, `regionFr` | VARCHAR |

## Example

```sql
-- DuckDB, straight off the Hub: refugees by country of asylum in 2025
SELECT "Country of asylum", sum("Refugees under UNHCR's mandate") AS refugees
FROM 'hf://datasets/yuiseki/unhcr-refugee-stats/parquet/2026-10-04/population.parquet'
WHERE "Year" = 2025
GROUP BY ALL ORDER BY refugees DESC LIMIT 10;
```

## Things to know

- Small numbers are rounded. UNHCR's data-content page: "Small numbers less
  than five are rounded to the nearest multiple of five. Additionally data
  relating to asylum decisions is rounded between five and ten. Data between
  tables remains additive therefore the totals should be considered
  approximations." No count column here holds a value from 1 to 4.
- Values are revised. The same year can have other figures in a later
  version; compare versions rather than assume a figure is final.
- `-` is not 0. In population, `Other people in need of international
  protection` is `-` (NULL) in 138,738 of 138,893 rows: before 2018, when
  the category did not exist, and wherever no figure was reported after.
  In solutions, the four counts are `-` where there is no flow: the 6,097
  rows with a figure for `Returned refugees` have the same figure in
  population, which writes 0 where solutions writes `-`.
- Definitions change over the years. "Other people in need of international
  protection" was added in 2022 and carried back to 2018. Stateless refugees
  are counted in both categories from 2017 (Rohingya) and 2020 (all
  countries), so adding the two double counts them in those years. Read
  UNHCR's methodology page before building a long series.
- `IDPs of concern to UNHCR` counts only internally displaced people UNHCR
  protects or assists. It is not a count of all internal displacement (that
  is IDMC's series, which is not here).
- In solutions, "Country of asylum" is the country of arrival for
  resettlement and the country of departure for returns.
- Applications and decisions mix cases and persons (`Cases / Persons`). Sum
  them separately.
- In 444 rows of asylum-decisions the four kinds of decision do not add up
  to `Total decisions` (166 above, 278 below, by up to 6,091).
- In demographics the age bands add up to `Female total` and `Male total`
  in every row, but `Total` exceeds `Female total` plus `Male total` in
  66,185 rows, 51,261 of them with no breakdown by sex at all. It is never
  below.
- Two country names carry a trailing space, as served: `Unknown ` and
  `Curacao ` (3,727 rows of population). They are kept.
- The ISO columns use two codes outside ISO 3166: `UNK` for unknown
  (the country list's `code` for it is `UKN`) and `XXA` for stateless.
- UNHCR's own codes (`code` in countries) collide with ISO codes of other
  countries: UNHCR's `AUS` is Austria (ISO `AUT`), while ISO `AUS` is
  Australia (UNHCR `AUL`); UNHCR's `ARE` is Egypt, ISO `ARE` the United Arab
  Emirates. Join on `iso`, not `code`.
- In countries, the French names stop at their first non-ASCII letter as the
  API serves them: `Am` for Amérique, `Oc` for Océanie, `Cura` for Curaçao.
  Two items (`CRB`, id 290, and `CUR`, id 390) have only their code as `name` and
  every other name NULL.
- The files were requested for 1951 to 2027, the range of the API's year
  list; the data ends in 2025.
- There are no coordinates. Places are countries, so join on the ISO codes
  to map them.

## Checked before upload

`scripts/02_verify.py` in the source repository checks each version:

- every raw file has the size and sha256 in `MANIFEST.json`, every zip is
  intact, and each data CSV has the row count the API stated
- every table is in the Parquet and none from `third-party/`
- the Parquet has as many rows as the raw file counted with Python's csv
  module (or the items of `countries.json`) and the API's stated count
- a sha256 over every value of every row, in order, equals the one taken
  from the raw file, `-` standing for NULL in a count column, so no value was
  lost, changed or moved
- the column sums equal the totals the API stated: `applied` 40,727,399;
  decisions 7,924,994 recognized, 3,263,685 complementary protection,
  12,977,328 rejected, 11,315,163 otherwise closed, 35,497,749 in total;
  solutions 53,976,271 returned refugees, 5,708,274 resettlement arrivals,
  2,799,379 naturalisations, 83,575,541 returned IDPs
- every column has the type the rule gives
- the five zips carry the same `footnotes.csv`
- a DuckDB without extensions opens every file, and no row group has a
  bloom filter

## Licence

UNHCR's methodology page
(https://www.unhcr.org/refugee-statistics/methodology/), "Data terms and
conditions of usage":

> Except where otherwise indicated, the datasets made available by UNHCR on
> UNHCR Refugee Population Statistics Database are licensed under the
> Creative Commons Attribution 4.0 International Public License.
> Please refer to the Terms of Use for Datasets

UNHCR's Terms of Use for Datasets
(https://www.unhcr.org/what-we-do/data-and-publications/data-and-statistics/terms-use-datasets):

> 1. Except where otherwise provided, the datasets made available by UNHCR
> on the UNHCR Refugee Population Statistics Database (the "Datasets") are
> licensed under a Creative Commons Attribution International License 4.0
> (the "CC BY License") and the provision thereof is subject to the
> supplemental terms contained below in these Terms of Use for Datasets.

> 3. You shall provide attribution to UNHCR and its data providers in the
> following format:"UNHCR Refugee Population Statistics Database".

> 4. When sharing or facilitating access to the Datasets, the URI or
> hyperlink to the Datasets shall also provide the uniform resource locator
> (URL) of these Terms of Use for Datasets.

> 5. You may not publicly represent or otherwise assert or imply that UNHCR,
> in the past, currently or in the future, participates, sponsors, approves
> or endorsed the manner or purpose of your use or reproduction of the
> Datasets.

> 8. You may use UNHCR application programming interfaces ("APIs") to
> facilitate access to the Datasets, whether through a separate Web site or
> through another type of software application.

Both pages were read on 2026-10-04 in the Internet Archive's copies (the
methodology page of 2026-07-30, the Terms of Use of 2026-09-21), because
www.unhcr.org answers scripted requests with a bot challenge. Item 7 of the
Terms forbids using UNHCR's name and emblem; item 14 lets UNHCR change the
terms at any time, so read the current ones before you reuse the data.

What this means for you:

- Attribute as "UNHCR Refugee Population Statistics Database", give the URL
  of the Terms of Use for Datasets, and name the licence, CC BY 4.0
  (https://creativecommons.org/licenses/by/4.0/).
- Do not suggest that UNHCR made, sponsored, approved or endorsed your work,
  and do not use UNHCR's name or emblem beyond naming the source. This
  dataset uses no UNHCR logo or emblem; the name appears only to say where
  the data comes from.
- HDX lists UNHCR's copies of the same data as `cc-by-igo`. This dataset
  follows UNHCR's own pages, which say CC BY 4.0.

What was changed: the raw files are UNHCR's, unchanged. The Parquet was made
from them, with the count columns and `Year` typed and `-` read as NULL, as
described above and in `LICENSE`; no other value was changed.

## Citation

UNHCR Refugee Population Statistics Database, https://www.unhcr.org/refugee-statistics/,
retrieved 2026-10-04 through https://api.unhcr.org/population/v1/. Terms of
Use for Datasets:
https://www.unhcr.org/what-we-do/data-and-publications/data-and-statistics/terms-use-datasets
