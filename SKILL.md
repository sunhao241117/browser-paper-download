---
name: browser-paper-download
description: Batch-download academic paper PDFs through the user's own browser (real Chrome on macOS via AppleScript, or real Microsoft Edge on Windows via desktop automation) so their institutional/subscription access applies, then rename them to the user's preferred pattern (年份_期刊_第一作者_标题.pdf). Use when the user asks to download paper PDFs (e.g., "download the key references", "用我的浏览器下载这些文献"), when papers are paywalled and the user has institutional access, when given a list of PMIDs/DOIs/citations, or when extracting and downloading key/classic references from review documents. Covers PMID→DOI/PMC lookup, publisher direct-PDF URL construction, browser-driven tab navigation (AppleScript on macOS / desktop automation on Windows), anti-bot (Cloudflare/Turnstile/reCAPTCHA) handling via computer-use, PubMed-metadata renaming, and archiving PDFs into organized folders.
---

# Browser Paper Download

Download paper PDFs through the user's real browser (their cookies = institutional access), navigating tabs via AppleScript (macOS Chrome) or desktop automation (Windows Edge) and watching `~/Downloads`. Direct `curl` fails on PMC, ASH, JAMA, Wiley, Elsevier etc. (403/bot walls), so the browser is mandatory.

**Harness compatibility**: works in any agent that loads Agent Skills (`SKILL.md`) — ZCode, Claude Code, Codex CLI, opencode, Goose, Amp. Install into a harness with `./install.sh <target>` (or `--dest <dir>`) from the repo. The `scripts/` are plain Python 3 and run standalone; only the interactive anti-bot fallback needs a computer-use / GUI-automation tool, and it must drive the user's **real browser** — headless or fresh-profile automation has no institutional cookies.

## Windows harness: drive the user's real Edge (verified)

No AppleScript on Windows. Use a desktop-automation plane (e.g. `seed_computer_use`, "cu" plane: `cu.list_apps()` → `cu.launch_app("<Microsoft Edge#...>")` → click/type/press, all coordinates normalized 0–1000 on the whole screen). The user's Edge carries their profile cookies, so institutional access (e.g. "Brought to you by: Zhengzhou University") applies exactly like Chrome on macOS. Real Edge also passes Cloudflare checks that a fresh automation browser fails (Springer/Wiley/OUP/NEJM/SD open directly; see route table).

**Per-paper batch flow on Windows:**
1. Focus Edge: `cu.launch_app(edge_name)` from `cu.list_apps()`; dismiss any browser popup (privacy consent etc.) by clicking its button.
2. Navigate: click the address bar (~(300,60)), `ctrl+a`, `type(url)`, press Enter, wait ~10–15 s (longer for SD/OUP).
3. Screenshot and read the page state: PDF viewer (page counter "1 / N" + toolbar) / article page / paywall / challenge.
4. **Universal save trick for ANY PDF in Edge's viewer**: `Ctrl+S` opens the native "另存为" dialog with the URL slug pre-filled → click 保存 (~(530,475) at 1920×1080) → file lands in `C:\Users\sunhao\Downloads`. This replaces any reliance on "download PDFs" browser settings.
5. For an **article page**, find and click its "View PDF"/"PDF下载" button (positions shift; re-screenshot to locate), then handle any Turnstile (see antibot_playbook) or save from the viewer.
6. Between papers, list `Downloads` with a file tool (not inside the browser cell) to confirm `%PDF-` files; move each into the dest folder with `PMID_<id>.pdf` naming, then run `rename_papers.py` once at the end.

Desktop-coordinate notes (1920×1080): address bar ~(300,60); Edge viewer page counter ~(500,95); Save dialog 保存 ~(650,585); SD article "View PDF" button moves as the page re-lays-out — always re-screenshot before clicking.

**cu-plane hard rules (learned in production):**
- `cu.click()` / `cu.type()` MUST be preceded by `cu.screenshot()` in the same call chain, otherwise `CU_INVALID_ACTION`. Every cell that sends pointer input must first observe the screen.
- Coordinates are 0–1000 normalized over the WHOLE screen, not the viewport. Re-derive from a fresh screenshot after any scroll, navigation, or dialog.
- The "另存为" dialog's 保存 button drifts per paper (~650,585 ±20); always screenshot-OCR before clicking, never hardcode.
- `cu` state does NOT survive between calls — anything needed later (file path, count) must be written to disk or printed to stdout.
- `wayf.springernature.com` institution autocomplete input: `cu.type()` works intermittently (sometimes succeeds, sometimes the input silently rejects keystrokes). If it fails twice, try `bu` plane for that one step, then return to `cu` for the rest.
- **CARSI SSO login (e.g. Zhengzhou University `cas.s.zzu.edu.cn`)**: saved credentials may auto-fill; clicking 登录 completes institutional auth. BUT — SSO login success ≠ subscription entitlement. Always return to the article page and confirm a PDF button appears; Springer MIMB chapters often show "Log in via an institution" even after successful SSO because the institution doesn't subscribe to that book.

## Workflow

### 1. Build the download queue

From the user's list (PMIDs, DOIs, or citations extracted from documents), resolve IDs with the bundled script. It accepts PMIDs, DOIs, or a mixed list with auto-detection:

```bash
# PMIDs only
python3 scripts/lookup_ids.py --pmids 33108101,25029335 --out queue.json

# DOIs only (resolved to PMIDs via NCBI idconv)
python3 scripts/lookup_ids.py --dois 10.1038/s41586-020-2649-2,10.1016/j.cell.2020.01.001

# Mixed — auto-detects pure digits as PMID, "10.*/..." as DOI
python3 scripts/lookup_ids.py --ids 33108101,10.1038/s41586-020-2649-2 --out queue.json
```

It fills per paper: `pmcid`, `doi`, Elsevier `pii` (via CrossRef alternative-id), Unpaywall OA mirror URLs, and a best-guess direct `url` + `article_url`. Review the queue JSON (fields: `folder`, `name`, `pmid`, `doi`, `pmcid`, `pii`, `url`, `article_url`, `alt_pdfs`).

**DOI→PMID resolution note**: `lookup_ids.py --dois` uses NCBI idconv for reverse DOI→PMID lookup, which has a low success rate (~25% in practice — many DOIs silently fail). For a DOI-only input list, prefer the **NCBI esearch** route which achieves near-100%:
```python
url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term={doi}[doi]&retmode=json"
# data["esearchresult"]["idlist"][0] = PMID
```
Then feed the resolved PMIDs into `lookup_ids.py --pmids`. This avoids the idconv gap and ensures every paper gets a PMID (needed for `rename_papers.py` metadata).

### 2. One-time browser setup (macOS Chrome only)

- Toggle **chrome://settings/content/pdfDocuments → 下载 PDF 文件** (Download PDFs). AXPress on the radio often reports "mismatched"; a raw event click on the label text works, then re-observe to confirm `radio 下载 PDF 文件 = 1`.
- Do NOT bother enabling "Allow JavaScript from Apple Events" — tab navigation via `set URL of ...` works without it.
- If the Chrome window is invisible (stuck on another Space after display sleep): quitting and reopening Chrome fixes it; cookies persist. Start `caffeinate` for long batches.
- **Windows: no setup needed** — use Edge's PDF viewer + `Ctrl+S` (see "Windows harness" above).

### 3. Batch download

```bash
python3 scripts/download_papers.py queue.json --dest /path/to/PaperFolder
```

The script opens ONE reusable tab, per paper: snapshots `~/Downloads` → sets tab URL → polls for a new non-`.crdownload` file with stable size → checks `%PDF-` magic → moves/renames to `dest/<folder>/<name>.pdf`. Failures are logged (`NO_DOWNLOAD`, `BAD` files kept in `/tmp`) and safe to re-run (existing files skipped).

**Order the queue by route** to amortize anti-bot passes: all PMC first, then group by publisher domain.

### 3.5 Fast batch download on Windows (bu + cu planes, verified)

**Route selection: direct publisher URL > PubMed→DOI link.** Prefer navigating straight to the publisher article page (`onlinelibrary.wiley.com/doi/{doi}`, `iopscience.iop.org/article/{doi}`, `journals.sagepub.com/doi/{doi}`, etc.). The PubMed→DOI route adds a redirect and is only useful when you do not know the publisher URL pattern. Edge carries institutional cookies regardless of entry point, so referrer from PubMed is not required for access detection.

**Plane selection:**
- `bu` plane (`seed_browser_use`): faster, no coordinate guessing, but has NO institutional cookies — ScienceDirect will always hit Cloudflare. Use for PMC (open access) and publishers without CF.
- `cu` plane (`seed_computer_use`, real Edge): carries the user full profile + institutional cookies. Required for SD, Wiley, Springer, ACS, IOP, JoVE — any paywalled publisher.
- Fall back to `cu` whenever `bu` hits a wall it cannot pass (CF, WPS-handled save dialogs, institutional auth).

**Subdomain redirect trap (critical):** A `pdfdirect` or direct-PDF URL may redirect to a *different subdomain* that lacks the institutional entitlement cookie, falsely showing no access. Example: Wiley `pdfdirect/10.1002/jat.4510` redirects to `analyticalsciencejournals.onlinelibrary.wiley.com` which shows Get access — but the canonical article page `onlinelibrary.wiley.com/doi/10.1002/jat.4510` correctly shows Full Access. **Always judge institutional access from the article homepage, never from a redirect landing page.** If a direct-PDF link appears to fail, navigate to the article page and check for a PDF button before declaring no-access.

**Per-paper fast loop (bu plane, ~20–30 s/paper after CF pass):**
```python
import seed_browser_use as bu, os, shutil, time

DST = r"C:\...\target"
for pmid, article_url, pdf_url in queue:
    dst = os.path.join(DST, f"PMID_{pmid}.pdf")
    if os.path.exists(dst):
        continue  # skip already downloaded — critical for resumability
    bu.navigate(article_url)
    bu.wait_for_load(timeout=15)
    time.sleep(6)
    # Find and click "View PDF" / "PDF" link
    refs = bu.find("View PDF") or bu.find("PDF")
    if refs:
        bu.click(refs[0])
        time.sleep(8)
        # PDF opens in a new tab on pdf.<publisher>.com — find it by URL
        pdf_tabs = [t for t in bu.list_tabs() if "sciencedirectassets" in t["url"]
                    or "/pdf" in t["url"]]
        if pdf_tabs:
            bu.switch_tab(pdf_tabs[-1])
            time.sleep(3)
            rec = bu.download(bu.current_tab()["url"], filename=f"tmp_{pmid}.pdf")
            path = rec.get("path", "")
            if path and os.path.exists(path):
                with open(path, "rb") as f:
                    if f.read(5) == b"%PDF-":   # ALWAYS verify magic bytes
                        shutil.move(path, dst)
                        continue
    # If we reach here, mark failed and move on — don't loop forever
```

**PMC fast path**: direct `bu.download(pmc_pdf_url)` returns HTML (bot wall). Must **navigate first, then download the same URL**:
```python
bu.navigate("https://pmc.ncbi.nlm.nih.gov/articles/PMC1234567/pdf/")
bu.wait_for_load(timeout=15); time.sleep(5)
rec = bu.download(bu.current_tab()["url"], filename="x.pdf")  # now works
```

**ScienceDirect fast path** (after one CF pass): `pdfft` direct URL is unreliable (stalls on "Preparing to download"). Always go article page → click "View PDF" → switch to `pdf.sciencedirectassets.com` tab → `bu.download(current_url)`. The signed S3 URL is valid for 300 s; download immediately.

**Cloudflare strategy for speed**:
- One CF pass per **domain** sets `cf_clearance` cookie — batch ALL papers of that domain right after passing.
- `bu` plane Turnstile checkbox click works at viewport coords ~(47, 342) but only ~50% of the time. If two clicks fail, **immediately request user takeover** (`interaction.request_action`, type=browserControl) — do not burn 5+ minutes retrying. The user passing SD CF once unlocks the entire SD batch.
- Domains that commonly need CF: `sciencedirect.com`, `onlinelibrary.wiley.com` (and subdomains like `faseb.onlinelibrary.wiley.com`), `ahajournals.org`, `aacrjournals.org`, `aspetjournals.org`.

**Institutional-access triage (skip fast, don't waste time)**:
- Page shows "Purchase PDF", "Get Access", "Subscribe", or a 🔒 lock icon on the PDF button → institution has no access → skip immediately, report to user.
- **Oxford Academic** (academic.oup.com): red banner "You do not currently have access to this article." + "Sign in through your institution" / "Purchase" options → no access → fall back to Scholarscope+Sci-Hub.
- **Taylor & Francis** (tandfonline.com): "Purchase options" panel with "PDF download + Online access — USD XX.00" → no access → fall back to Scholarscope+Sci-Hub.
- **Karger** (karger.com): article page has no PDF/download button at all, only "Get Permissions" → no open PDF → fall back to Scholarscope+Sci-Hub.
- **NEJM**: "This content is available to subscribers. Subscribe now. Already have an account? Sign in." → paywalled → fall back to Scholarscope+Sci-Hub.
- Known no-access patterns for Zhengzhou University: Wiley ChemMedChem, ASPET Drug Metab Dispos, AHA Hypertension (some), FASEB Journal (some), Oxford EJE (some), T&F Fetal Pediatr Pathol, **Springer Methods in Molecular Biology (MIMB) book chapters**, **F&S Science (xfss journal)**, **OUP Endocrinology (2026+ issues)**, **SAGE Int J Surg Pathol**, **CSIRO Reprod Fertil Dev**.
- Springer articles with no PDF/download control at all → no entitlement → skip. **CARSI SSO login success does NOT mean access** — after logging in via `cas.s.zzu.edu.cn`, return to the article page; if it still shows `Log in via an institution` / `Subscribe and save`, the institution does not subscribe to that title. MIMB chapters are the most common false-positive (SSO works, no PDF button).
- **When no-access is confirmed, immediately try Scholarscope+Sci-Hub (section 3.6) before giving up** — this recovers ~50% of otherwise-unavailable papers. Note: Sci-Hub has not updated since 2021; papers published 2022+ are usually not available there.

**File hygiene for speed**:
- Before a batch, clear `C:\Users\sunhao\Downloads\` and `C:\Users\sunhao\Downloads\BrowserUse\` of old PDFs — prevents the watcher from confusing files between papers.
- Name temp downloads `tmp_<pmid>.pdf`, move to `PMID_<pmid>.pdf` only after `%PDF-` verification. Bad HTML files (header `<!DOC` or `\n\n\n\n<`) must be deleted, not saved.
- Close extra browser tabs every ~20 papers to keep the browser responsive.

**Batch processing best practices:**
- **Group by publisher and process in batches.** One Cloudflare/hCaptcha pass sets a cookie that covers all papers on that domain. IOP: pass hCaptcha once, then all IOP papers open directly. ScienceDirect: pass CF once, then all SD papers work.
- **Always verify %PDF- magic bytes before moving to target.** Downloaded HTML error pages (403, bot walls) often have .pdf extension but start with <!DOCTYPE.
- **Skip already-downloaded papers.** Check os.path.exists(dst) before each paper — critical for resumability after interruptions.
- **DOI list may have BOM on first line.** Strip \ufeff when reading the input file.
- **NCBI esearch is near-100% for DOI→PMID; idconv is ~25%.** Always use esearch for DOI-only inputs (see section 1).

### 3.6 Fallback: Scholarscope + Sci-Hub route (cu plane, verified)

When the publisher site shows no institutional access (purchase wall, "Get Access", etc.), the **Scholarscope browser extension + Sci-Hub** route can often retrieve the PDF for free. This is the single most effective fallback for paywalled papers that the institution does not subscribe to.

**Prerequisites (one-time, user-side)**:
- Scholarscope extension installed in the user's real Edge (Chrome extension, works in Edge via "允许来自其他应用商店的扩展").
- User logged in to Scholarscope (微信登录). Login state can be flaky — if the page redirects to `account.scholarscope.online/Login.php`, ask the user to re-login.

**Correct flow (per paper)**:
1. **Navigate to PubMed** for the paper: `https://pubmed.ncbi.nlm.nih.gov/{pmid}/`. Do NOT go directly to the publisher URL or use Scholarscope's download button first.
2. **Click the journal name or "View full text" link** on the right side of the PubMed page → this opens the publisher's site (with CF if needed). This is the user's preferred route — it carries the institutional referrer and avoids Scholarscope login redirect loops.
3. If the publisher page shows access (PDF button visible) → download via the normal route (section 3.5 or cu Ctrl+S).
4. If the publisher page shows **no access** (purchase wall, "You do not currently have access", "Purchase options" with price) → go back to the PubMed tab and use Scholarscope:
   - The Scholarscope extension injects a panel on PubMed pages. Click the **DOI link** in the Scholarscope panel (or the microscope icon) → it resolves to a Sci-Hub mirror.
   - Alternatively, in the Scholarscope panel's "Web Link" section, click **scihubWebpage**.
5. **Sci-Hub page opens with the PDF in Edge's viewer** → `Ctrl+S` → "另存为" dialog → click 保存 → file lands in `Downloads` → verify `%PDF-` → move to `PMID_<pmid>.pdf`.

**cu-plane CF Turnstile coordinates (real Edge, 1920×1080)**:
- The CF "请验证您是真人" checkbox is at approximately **(222, 455)** in full-screen coordinates. This is more reliable than the bu-plane (47, 342) because real Edge has the user's full browser reputation.
- After one click, wait 10–12 s for the challenge to resolve. If it fails, click once more; if still failing, request user takeover.

**cu-plane PDF save (real Edge)**:
- When PDF opens in Edge's built-in viewer, `Ctrl+S` opens the native "另存为" dialog with the filename pre-filled (e.g. `murad2017.pdf`).
- Click 保存 (button at ~(650, 585) at 1920×1080). Do NOT change the filename — rename later after verification.
- File lands in `C:\Users\sunhao\Downloads\`. Move it immediately to the target directory as `PMID_<pmid>.pdf`.

**Sci-Hub mirror availability**:
- `sci-hub.red` — often works, but may return 502 Bad Gateway under load.
- `sci-hub.se` — often returns ERR_CONNECTION_CLOSED from China networks.
- **Let Scholarscope pick the mirror** — it auto-rotates. Do not hardcode a Sci-Hub domain in the URL.

**Deduplication before batch**:
- If a previous download directory exists (e.g. `代谢` folder with 30+ renamed PDFs), match new papers by **title keywords** (journal abbreviation + first author surname + title fragment) and copy already-downloaded files instead of re-downloading. This can save 30–50% of batch time for related topic sets.

### 4. Interactive fallback (computer-use on the real browser)

For papers the direct URL misses, see [references/antibot_playbook.md](references/antibot_playbook.md) for the full click-through procedures. On Windows the same ladder applies through the cu plane — observe with `cu.screenshot()` (OCR the text blocks for element positions), click raster coordinates, `Ctrl+S` to save any PDF that opens. Summary ladder:

1. **Article-page warmup**: navigate to `article_url`, wait ~10 s, then retry the direct `url`.
2. **Article page + PDF link**: observe with `get_app_state`, find the "View PDF"/"Download PDF"/"Open the PDF" link/button, `left_click` the element (AXPress works on links even when it reports "mismatched"). Watch for the resulting tab/verification.
3. **Cloudflare Turnstile** ("正在安全验证 / 请验证您是真人"): the checkbox is usually an AX `checkbox 请验证您是真人 = 0` element; if AXPress fails, `mouse_move` + `left_mouse_down`/`left_mouse_up` at its raster coordinates (commonly ~(243, 402) at default window size). One pass per domain sets the cookie; then batch the rest of that domain.
4. **ScienceDirect PDF gate**: View PDF → `pdf.sciencedirectassets.com/.../cfts/init` "Security verification" page → click Turnstile → PDF auto-downloads. Verification may recur per paper; just repeat.
5. **ASH crawl-prevention** (reCAPTCHA "I'm not a robot" + "Take me to my Content"): triggers on doi.org redirects, NOT on direct article URLs — always navigate to the full `ashpublications.org/blood/article/...` URL. If an image challenge appears, zoom the grid, identify the target objects, click tiles, VERIFY; challenges can expire — redo if needed.
6. **STOP on login walls**: Shibboleth/personal logins (JAMA "Access through your institution" → sign-in form, NEJM sign-in) — never enter credentials. Skip and report to the user.

### 5. Rename to the user's preferred pattern

After downloading, rename PDFs to **`年份_期刊缩写_第一作者姓_标题.pdf`**
(the user's stated preference, e.g. `2020_N Engl J Med_Beck_Somatic Mutations in UBA1 and Severe Adult-Onset Autoinflammatory Disease.pdf`):

```bash
python3 scripts/rename_papers.py queue.json --dest /path/to/PaperFolder [--dry-run]
```

Metadata (year / journal / first-author surname / title) comes from PubMed esummary
by PMID. It sanitizes filesystem-illegal characters (`/` → `-`, strips e-pub tags),
truncates over-long titles at a word boundary, and disambiguates collisions with
" (2)" suffixes. Always `--dry-run` first when unsure. If the user specifies a
different pattern, adapt `build_name()` in the script.

### 6. Verify and report

Check each archived file is a real PDF (`%PDF-` magic, page count). Report per paper: downloaded (with route used), skipped-no-access (e.g., Springer 1973 journal with no institutional entitlement), needs-user-login (JAMA/NEJM Shibboleth), or unavailable.

## Key route rules

- **PMCID exists** → `https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/pdf/`. Exception: Blood/JAMA records in PMC are author manuscripts with no PDF (NO_DOWNLOAD) — use the publisher instead. **Must navigate first in browser, then download same URL** (direct `bu.download` returns HTML bot-wall).
- **Per-publisher direct URL patterns** (Nature `.pdf`, Wiley `pdfdirect`, Springer `content/pdf`, NEJM `pdf?download=true`, ScienceDirect `pdfft`, ASH `article-pdf`, JAMA `articlepdf`): see [references/publisher_patterns.md](references/publisher_patterns.md). Read it before constructing URLs; several publishers need the cookie from a passed challenge first.
- **Unpaywall mirrors** (`alt_pdfs`) often carry direct PDFs (e.g., ASH `article-pdf` links) usable after the domain's challenge is passed.

### Publisher DOI-prefix quick reference (batch triage)

| DOI prefix | Publisher | Typical access | Fast route |
|---|---|---|---|
| `10.1016/` | ScienceDirect (Elsevier) | Often institutional | article page → View PDF → download from `sciencedirectassets.com` tab |
| `10.1038/` | Nature | Often OA / institutional | direct `nature.com/articles/{suffix}.pdf` |
| `10.1002/`, `10.1111/` | Wiley | Mixed; subdomains separate | article page first (see subdomain trap), then `pdfdirect/{doi}`; J Appl Toxicol HAS access (Zhengzhou Univ) |
| `10.1088/` | IOP Publishing (Biomed Mater, Biofabrication, etc.) | Often institutional | `iopscience.iop.org/article/{doi}` → PDF button → Ctrl+S; hCaptcha (image grid, e.g. click plants for spray bottle) one pass unlocks all IOP |
| `10.3791/` | JoVE (Journal of Visualized Experiments) | Often institutional | `jove.com/video/{id}` → 全文 → 下载PDF; institutional access shown as `Zhengzhou University` banner |
| `10.1021/` | ACS (ACS Biomater Sci Eng, etc.) | Often institutional | article page → `Open PDF` button → Ctrl+S; page shows `Subscribed` when institution has access |
| `10.1177/` | SAGE (Int J Surg Pathol, etc.) | Often no institutional | `journals.sagepub.com/doi/{doi}`; `未订阅` lock icon = no access |
| `10.1071/` | CSIRO Publishing (Reprod Fertil Dev, etc.) | Paywall | `connectsci.au` article page; `Pay-Per-View USD ` = no institutional access |
| `10.1080/` | Taylor & Francis | Often no institutional | PubMed → "View full text" → CF → "Purchase options" = no access → Scholarscope+Sci-Hub |
| `10.1007/` | Springer | Mixed; old journals may have none | `link.springer.com/content/pdf/{doi}.pdf`; no PDF button = no entitlement |
| `10.1161/` | AHA (Hypertension, ATVBA, etc.) | Often no institutional | `ahajournals.org/doi/pdf/{doi}`; "Get Access" = skip |
| `10.1124/` | ASPET (DMD, Mol Pharmacol, etc.) | Often no institutional | `aspetjournals.org`; "Get Access"/"Purchase PDF" = skip |
| `10.1093/` | OUP (Brain, EJE, etc.) | Mixed; many have PMC | Check PMCID first; "You do not currently have access" = no access → Scholarscope+Sci-Hub |
| `10.1530/` | Bioscientifica / EJE | Often no institutional | Bioscientifica SSL may fail from China; use PubMed → Oxford Academic mirror |
| `10.4158/` | Endocrine Practice (AACE/Elsevier) | Often no institutional | AACE site may be unreachable (ERR_CONNECTION_CLOSED); Scholarscope+Sci-Hub works |
| `10.1159/` | Karger (Pathobiology, etc.) | Often no open PDF | Karger page has no PDF button → Scholarscope+Sci-Hub |
| `10.3760/` | 中华医学系列 (Chinese) | Often OA via CNKI | Direct CNKI link; may need Chinese platform access |
| `10.5980/` | Japanese journals (Nihon Hinyokika, etc.) | Often OA | Direct publisher site; usually no CF |
| `10.1073/` | PNAS | OA (PMC available) | PMC direct |
| `10.1056/` | NEJM | Often paywalled | `nejm.org/doi/pdf/{doi}?download=true`; sign-in wall = Scholarscope+Sci-Hub |
| `10.3390/` | MDPI | OA | direct PDF or PMC |
| `10.18632/` | Oncotarget | OA | direct PDF or PMC |
| `10.23812/` | J Biol Regul Homeost Agents | OA but OJS platform | `article/download/{id}`; may lack PDF galley |

## Resources

### scripts/
- `lookup_ids.py` — PMID → PMCID/DOI/Elsevier-PII/Unpaywall resolution; emits queue JSON.
- `download_papers.py` — sequential Chrome-tab downloader with Downloads watcher, PDF validation, archiving, logging.
- `rename_papers.py` — post-download rename to `年份_期刊_第一作者_标题.pdf` via PubMed metadata.

### references/
- `publisher_patterns.md` — per-publisher direct-PDF URL patterns and known quirks (tested in practice).
- `antibot_playbook.md` — Cloudflare/Turnstile/reCAPTCHA/ScienceDirect-verification click procedures and failure modes.
