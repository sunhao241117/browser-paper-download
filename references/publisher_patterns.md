# Publisher URL patterns & quirks

All patterns verified in practice. `{doi}` = DOI, `{pmcid}` = PMC ID, `{pii}` = Elsevier PII
(uppercase, dashes/brackets stripped — get it from CrossRef `alternative-id`).

Construct per-paper `url` in this order: PMCID (if it will actually serve a PDF) →
publisher direct URL → Unpaywall mirror. Group the queue by publisher so one
Cloudflare pass covers the whole domain batch.

## Route table

| Publisher | Direct PDF URL | Quirks |
|---|---|---|
| PMC (free) | `https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/pdf/` | Works via Chrome. **Blood/JAMA records in PMC are author manuscripts with no PDF** → NO_DOWNLOAD, use publisher. Old PMC records occasionally need a second attempt (~40 s) on first hit. In an automation browser the `/pdf/` URL may return only the "Preparing to download…" HTML interstitial — navigate the page first so it redirects to the real `.../{pmcid}.pdf`, then download the resolved URL. |
| Nature / Nat Genet / Nat Immunol … | `https://www.nature.com/articles/{doi_suffix}.pdf` (suffix = DOI minus `10.1038/`) | Most reliable direct download; no CF challenge observed. **Old `10.1038/labinvest.*` DOIs 404 on nature.com** — resolve `https://doi.org/10.1038/labinvest.3780294` in the browser: it lands on a ScienceDirect PII (`S0023683722...`) that serves the PDF via the SD flow. |
| Wiley | `https://onlinelibrary.wiley.com/doi/pdfdirect/{doi}` | `pdfdirect` downloads; `/doi/pdf/` only opens their reader. Cloudflare challenge once per domain; cookie then covers the batch. **In the user's real Edge the challenge does not appear** — pdfdirect opens the PDF directly with institutional access. |
| Wiley (ACR subdomain) | `https://acrjournals.onlinelibrary.wiley.com/doi/pdfdirect/{doi}` | Separate domain = separate Cloudflare pass. |
| Springer | `https://link.springer.com/content/pdf/{doi}.pdf` | Needs entitlement; old journals (e.g., Pediatric Radiology 1973) may have none — article page then shows no PDF link at all → skip as no-access. **With institution access the content/pdf URL opens directly in the real browser** (no CF). |
| NEJM | `https://www.nejm.org/doi/pdf/{doi}?download=true` | Cloudflare challenge once per domain. After pass, direct URL works. `?download=true` matters. **In the real browser the direct URL may render the article page instead of a PDF** — if it says "This content is available to subscribers" even with the institutional banner shown, the institution's package lacks the article (old archive) → mark no-access, never sign in. |
| ScienceDirect (Elsevier) | Article page → click "View PDF" (do NOT rely on `pdfft` direct nav) | `pdfft` direct navigation hits a "Preparing to download" interstitial that stalls, or a Cloudflare "Are you a robot?" page, or an error (CPE00001). Correct flow: load `https://www.sciencedirect.com/science/article/pii/{pii}` (institutional banner "Brought to you by: <Institution>" and/or "Full text access" should show; "Open access / Open archive" needs no entitlement) → click the "View PDF" button (its position moves as the page re-lays-out — re-screenshot) → `pdf.sciencedirectassets.com` Security-verification Turnstile (~(152,302) or ~(380,357)) → click checkbox → PDF opens (`1-s2.0-{PII}-main.pdf`). **The clearance cookie persists per domain: subsequent SD papers skip the gate.** |
| ASH (Blood) | `https://ashpublications.org/blood/article-pdf/{vol}/{issue}/{page}/{fileid}/{file}.pdf` | fileid/file NOT derivable — get from Unpaywall `oa_locations` (older Blood is free) or click the article page's "Open the PDF … in another window" link. Direct article URLs are fine; **doi.org redirects trigger a crawl-prevention reCAPTCHA** — avoid. **Real-browser attempt hit the "crawlprevention/governor" loop: every redirect mangles the article ID in the URL, the numeric captcha repeats, and solving it returns 401.** Treat ASH as effectively impassable by automation; prefer the ScienceDirect mirror of the same Blood article (`S0006-4971...` PII). |
| JAMA | `https://jamanetwork.com/journals/{j}/articlepdf/{article_id}` | Cloudflare once; then `articlepdf` STILL redirects to fullarticle and the "Download PDF" button opens a **sign-in modal** (personal or Shibboleth) → stop, needs user login. |
| OUP | `https://academic.oup.com/{journal}/article-pdf/{vol}/{issue}/{page}/{fileid}/{file}.pdf` | Direct article-pdf URLs work in the real browser with institutional access (redirects to `watermark02.silverchair.com` with a token, then opens in the viewer). Article-page flow: if the URL reroutes `fulltext` → `article-abstract` or shows "Get access" instead of a PDF link, the institution lacks the journal → no access, skip. |
| Karger | `https://karger.com/doi/pdf/{doi}` 404s — go via `https://doi.org/{doi}` | Article page shows only the abstract when the institution lacks the journal (`?redirectedFrom=fulltext` → article-abstract, "Tools" menu has no PDF) → no access, skip. |
| Taylor & Francis | `https://www.tandfonline.com/doi/pdf/{doi}` and `/doi/epdf/{doi}` both render the article page | No "Download PDF" button and "Read this article" leads to a purchase page (e.g. USD 68) or "Access through your institution" (Shibboleth) → login wall, skip; never enter credentials. |
| RSC | `https://pubs.rsc.org/en/content/articlepdf/{year}/{journal}/{id}` (e.g. `2025/fo/d4fo04271a`) | Opens the PDF at `rscj.silverchair-cdn.com` with institutional access. The articlelanding page also works (institution name shows top-right). |
| 中华医学期刊全文数据库 (yiigle.com, Chinese journals) | Article page `https://rs.yiigle.com/cmaid/{id}` | Shows "PDF下载" button → click → left side panel → click "下载PDF" → file downloads. Institution name (e.g. 郑州大学) is shown top-right when access applies. |
| LWW / Ovid | via `https://doi.org/{doi}` | Lands on ovid.com abstract; PDF usually pay-per-view → typically no access. |
| cell.com (Cell Press legacy) | `https://www.cell.com/article/{pii}/pdf` | Aggressive Cloudflare loop possible; may never pass. Old Cell articles are free — try the ScienceDirect mirror of the same article (search the title + ScienceDirect; PII like `S0006497120468119`) which usually works with the SD flow. |

## Useful crosswalks

- **Old Blood (ASH) ↔ ScienceDirect**: Blood articles also live on ScienceDirect with a
  `S0006-4971...` PII; when ASH blocks, search `title site:sciencedirect.com` and use the SD flow.
- **Unpaywall** `https://api.unpaywall.org/v2/{doi}?email=...` → `oa_locations[].url_for_pdf`
  gives legal OA mirrors (repository PDFs, publisher OA copies). Prefer https versions.
- **NCBI idconv** does not return DOIs for some older records — fall back to esummary `articleids`.
