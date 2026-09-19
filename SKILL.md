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

**PMC download playbook (verified in production, 192 papers downloaded)**:

The PMC route is the most reliable batch in the entire workflow (~95% success rate, 20–30 s/paper). Use the **bu plane** exclusively — PMC is open access, no institutional cookies needed, and bu is faster with no coordinate guessing.

*Correct per-paper flow (bu plane):*
```python
import seed_browser_use as bu, os, shutil, time

DST = r"C:\...\target"
for pmid, pmcid in pmc_queue:
    dst = os.path.join(DST, f"PMID_{pmid}.pdf")
    if os.path.exists(dst):
        continue  # skip already downloaded
    article_url = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"
    bu.navigate(article_url)
    bu.wait_for_load(timeout=15)
    time.sleep(5)
    # Find and click "Download PDF" button on the article page
    refs = bu.find("Download PDF")
    if refs:
        bu.click(refs[0])
        rec = bu.wait_for_download(timeout=30)
        path = rec.get("path", "")
        if path and os.path.exists(path):
            with open(path, "rb") as f:
                if f.read(5) == b"%PDF-":  # ALWAYS verify magic bytes
                    shutil.move(path, dst)
                    continue
    # If no Download PDF button or download failed, mark and move on
    print(f"  SKIP {pmid} ({pmcid}): no Download PDF button or download failed")
```

*Key pitfalls learned in production:*
1. **Never `bu.download(pmc_pdf_url)` directly** — returns HTML bot-wall (403). Must navigate the article page first, then click the "Download PDF" button.
2. **Always verify `%PDF-` magic bytes** — HTML error pages can have a `.pdf` extension. Bad files must be deleted, not saved.
3. **11 papers had no "Download PDF" button** — these are typically author manuscripts (Blood/JAMA records) or records with only HTML. Skip them and fall back to the publisher route.
4. **Old PMC records load slowly** — occasionally need 40 s or a second attempt on first hit. If `wait_for_download` times out, retry once.
5. **Use bu plane, not cu plane** — cu is slower, requires coordinate guessing, and is unnecessary for open-access PMC. Reserve cu for paywalled publishers.
6. **PMC is the first batch to run** — process all PMC papers before any paywalled publisher. They build momentum and don't trigger anti-bot systems.

*PMC vs paywalled publisher comparison (updated):*

| Dimension | PMC (bu plane) | ScienceDirect (cu plane) |
|-----------|-----------------|--------------------------|
| Success rate | ~95% | ~85% (after institutional login) |
| Speed | 20–30 s/paper | 40–60 s/paper |
| Institutional access | Not needed | Required (Zhengzhou Univ CARSI) |
| Anti-bot | Essentially none | Cloudflare (1 pass per domain) + occasional rate limiting |
| Save method | `bu.download()` direct | Ctrl+S "另存为" (preferred) |
| Plane | bu (fast, no coords) | cu (real Edge, coords needed) |
| Papers downloaded | 192 | ~100+ (Cytokine Growth Factor Rev, Int Immunopharmacol, Pancreatology, etc.) |

**ScienceDirect fast path (cu plane, verified):**
- **Recommended flow**: PubMed article page → click "ELSEVIER FULL-TEXT ARTICLE" link → confirm "Brought to you by: Zhengzhou University" → click "View PDF" → wait for PDF viewer to fully load (page counter "1 / N" visible) → Ctrl+S → save as `tmp_{pmid}.pdf`.
- **Gray button workaround**: when "View PDF" button is grayed out (rate limiting), navigate directly to `https://www.sciencedirect.com/science/article/pii/{PII}/pdf`. This bypasses the button and opens the PDF viewer directly.
- **Save method**: Ctrl+S in the PDF viewer opens "另存为" dialog with pre-filled filename like `1-s2.0-{PII}-main.pdf`. Rename to `tmp_{pmid}.pdf` and click 保存. Verify "保存类型" shows "WPS PDF 文档 (*.pdf)" before clicking save.
- **Fallback save**: if Ctrl+S fails (saves HTML or shows network error), use Ctrl+P → "Microsoft Print to PDF" → enter filename → save. This is slower but more reliable. User prefers Ctrl+S; only use Ctrl+P as fallback.
- **Direct `pdfft` URL is unreliable** — often stalls on "Preparing to download" or hits Cloudflare. Do not rely on it.

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

**Fully automated batch download principles (user requirement):**
- **Process PMC papers first, then other journals.** PMC is open access, fastest, highest success rate (~95%). Process all PMC papers before moving to paywalled publishers.
- **Fully automated, no stopping.** The agent should run continuously through the entire queue without pausing to ask the user for decisions. Make all reasonable decisions autonomously.
- **Skip paywalled/non-OA papers immediately.** If a paper shows "Purchase PDF", "Get Access", "Subscribe", "No Access", or any paywall indicator → skip immediately and move to the next paper. Do not waste time trying to bypass paywalls or ask the user.
- **Self-resolve all issues.** Handle cookies popups, Cloudflare checks, login redirects, and minor UI changes autonomously. Only request user takeover for CAPTCHAs or institutional logins that require credentials.
- **Final summary report.** After processing all PMIDs, output a summary report with: (1) total papers in queue, (2) successfully downloaded count, (3) failed/skipped count, (4) breakdown by reason (no access, no PDF button, download error, etc.).
- **Resumable by design.** Always check `os.path.exists(dst)` before each paper. If interrupted, restarting the batch will automatically skip already-downloaded papers and continue where it left off.
- **Pacing and anti-bot.** Process papers one at a time, wait for each download to complete before starting the next. Group papers by publisher domain to amortize anti-bot passes (one Cloudflare check unlocks all papers on that domain).

**Non-PMC publisher download playbook (verified in production, 100+ papers downloaded):**

The PubMed → publisher → Ctrl+S route is the most reliable for paywalled non-PMC papers. Use the **cu plane** exclusively — it carries the user's real Edge profile + institutional cookies (Zhengzhou University CARSI).

**Recommended workflow order:**
1. Process all PMC papers first (bu plane, fastest, highest success rate)
2. Then process non-PMC papers by publisher, grouping by domain to amortize Cloudflare passes
3. Start with ScienceDirect/Elsevier papers (largest batch, ~85% success after institutional login)
4. Then process other publishers (Wiley, Springer, ACS, OUP, etc.)
5. Skip no-access papers immediately (see access triage section)

*Correct per-paper flow (cu plane):*
```python
import seed_computer_use as cu, os, shutil, time

DST = r"C:\...\target"
DL = os.path.join(os.environ["USERPROFILE"], "Downloads")
for pmid in queue:
    dst = os.path.join(DST, f"PMID_{pmid}.pdf")
    if os.path.exists(dst):
        continue  # skip already downloaded

    # 1. Navigate to PubMed article page in the SAME tab
    cu.click(300, 60); cu.hotkey("ctrl", "a")
    cu.type(f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/")
    cu.hotkey("enter"); time.sleep(12)
    cu.screenshot()

    # 2. Click the publisher full-text link on the right sidebar
    #    (ELSEVIER FULL-TEXT ARTICLE / WILEY Full Text / SPRINGERLINK / etc.)
    cu.click(750, 560); time.sleep(15)  # adjust based on screenshot
    cu.screenshot()

    # 3. Handle Cloudflare Turnstile if it appears
    if "请验证您是真人" in page_text:
        cu.click(225, 455); time.sleep(15)  # CF checkbox ~(225, 455)

    # 4. For ScienceDirect: confirm "Brought to you by: Zhengzhou University"
    #    Then click "View PDF" OR navigate directly to PDF URL:
    #    https://www.sciencedirect.com/science/article/pii/{PII}/pdf
    cu.click(315, 445); time.sleep(20)  # View PDF button
    cu.screenshot()

    # 5. Once PDF is open in Edge viewer, Ctrl+S to save
    cu.hotkey("ctrl", "s"); time.sleep(5)
    cu.screenshot()  # confirm "另存为" dialog appeared

    # 6. Rename file in dialog: tmp_{pmid}.pdf, then click 保存(S)
    cu.click(150, 495); cu.hotkey("ctrl", "a")
    cu.type(f"tmp_{pmid}.pdf")
    cu.click(660, 585); time.sleep(15)  # 保存 button ~(660, 585)

    # 7. Verify %PDF- magic bytes, then move to destination
    pdf_file = os.path.join(DL, f"tmp_{pmid}.pdf")
    if os.path.exists(pdf_file):
        with open(pdf_file, "rb") as f:
            if f.read(5) == b"%PDF-":
                shutil.move(pdf_file, dst)
                print(f"  OK: {pmid} ({os.path.getsize(dst)//1024} KB)")
                continue
    print(f"  SKIP {pmid}: no valid PDF")
```

*Key pitfalls learned in production:*
1. **PubMed entry point is preferred** — navigate to PubMed first, click the publisher link, rather than going directly to the publisher URL. This carries the correct referrer and avoids rate-limiting.
2. **Always use the same tab** — do not open new tabs for each paper. This preserves the session and avoids Scholarscope-style extension redirects.
3. **ScienceDirect rate limiting**: after ~10 consecutive SD papers, the "View PDF" button turns gray. Solution: refresh the page, or navigate directly to `https://www.sciencedirect.com/science/article/pii/{PII}/pdf` to bypass.
4. **JACC (jacc.org) special case**: Ctrl+S saves HTML, not PDF. Must click the download icon in the top-right toolbar instead.
5. **Cloudflare verification**: click the checkbox at ~(225, 455), wait 10-15 seconds. One pass per domain sets the cookie for subsequent papers.
6. **No-access triage**: if the page shows "Purchase PDF", "Get Access", "Subscribe", or only "Article preview" → skip immediately. Do not waste time trying.
7. **PMCID papers go through PMC route** (section 3.5) — they are more reliable and faster.
8. **Save dialog filename**: the pre-filled name varies by publisher. Always overwrite it with `tmp_{pmid}.pdf` before clicking save.
9. **CRITICAL: PDF must be fully loaded before Ctrl+S** — confirm the page shows a PDF viewer (page counter "1 / N" + toolbar) before saving. Saving from the article page produces HTML. This is the #1 cause of failed SD downloads.
10. **Verify file extension**: the save dialog's "保存类型" must show "WPS PDF 文档 (*.pdf)" or "PDF (*.pdf)". If it says "网页，全部 (*.htm;*.html)", you're on an article page, not a PDF viewer.
11. **"Save to Zotero (PDF)" is NOT a download button** — it saves to the Zotero reference manager, not to your local disk. Do not click it.
12. **Right-click "Save link as" also saves HTML** — for ScienceDirect's "View PDF" button, right-clicking and choosing "Save link as" saves the article HTML (filename pdfft.htm), not the actual PDF. Must open the PDF viewer first.
13. **Direct PDF URL bypass** — when the "View PDF" button is gray (rate limiting), navigate directly to `https://www.sciencedirect.com/science/article/pii/{PII}/pdf`. This often bypasses the gray button and opens the PDF viewer directly.
14. **DNS resolution failure** — occasionally ScienceDirect shows `DNS_PROBE_FINISHED_NXDOMAIN`. This is usually a proxy/network issue, not permanent. Retry after 30-60 seconds.
15. **WPS Office auto-opens PDFs** — after downloading, WPS may automatically open the PDF file. This is harmless but may steal focus.
16. **User preference: Ctrl+S first, Ctrl+P only as fallback** — the user prefers Ctrl+S "Save As" over Ctrl+P "Print to PDF". Only use Ctrl+P when Ctrl+S consistently fails (e.g., on certain PDF viewers where Ctrl+S saves HTML).
17. **Scholarscope extension interferes** — the Scholarscope browser extension redirects PubMed to its own login page. Disable it before starting bulk downloads, or the PubMed → publisher route will fail.
18. **ScienceDirect custom PDF viewer quirks** — Ctrl+S on the SD custom viewer (pdf.sciencedirectassets.com) sometimes saves as HTML or shows "network error". When this happens, refresh the PDF page and try again, or fall back to Ctrl+P → Microsoft Print to PDF.
19. **Page timeout handling** — if the publisher page takes too long to load (ERR_TIMED_OUT / ERR_CONNECTION_TIMED_OUT), refresh the page once. If it still times out after refresh, skip to the next paper immediately. Do not waste time waiting indefinitely.
20. **Pre-screen paywalled/non-OA journals before clicking** — based on historical experience, if you already know a journal is paywalled and your institution has no access (e.g., AACR, SAGE Publications, certain OUP journals), DO NOT click the full-text link from PubMed. Skip directly to the next paper. This saves significant time by avoiding repeated failed attempts on known inaccessible journals.
21. **SAGE Publications connection timeout** — journals.sagepub.com consistently times out (ERR_CONNECTION_TIMED_OUT). Skip SAGE journals without attempting to click the link.
22. **silverchair.com PDF viewer timeout** — OUP's silverchair.com PDF viewer (watermark02.silverchair.com) frequently times out. If the PDF page takes more than 20 seconds to load after Cloudflare verification, skip to the next paper.
23. **MUST process ALL PMIDs before stopping** — the user explicitly requires that every PMID in the batch must be attempted before stopping. Do NOT auto-stop early after processing a few papers and reporting progress. Do NOT stop because you think "most are inaccessible" or "we've covered the easy ones". Continue processing every PMID in the queue until all have been attempted. Only stop when the user explicitly gives a "停止" / "stop" command.

*Verified journal access patterns (Zhengzhou University, expanded):*

| Journal | Access | Download method |
|---|---|---|
| J Ethnopharmacol | Institutional ✓ | View PDF button → Ctrl+S |
| Biochem Pharmacol | Institutional ✓ | View PDF button → Ctrl+S |
| Cell Signal | OA ✓ | View PDF button → Ctrl+S |
| Curr Opin Immunol | Institutional ✓ | View PDF button → Ctrl+S |
| Brain Behav Immun | Institutional ✓ | View PDF button → Ctrl+S |
| Autoimmun Rev | Institutional ✓ | View PDF button → Ctrl+S |
| J Invest Dermatol | OA ✓ | Download PDF button → Ctrl+S |
| Int Immunopharmacol | Institutional ✓ | View PDF button → Ctrl+S |
| Pancreatology | Institutional ✓ | View PDF button → Ctrl+S |
| Cytokine Growth Factor Rev | Institutional ✓ | View PDF button → Ctrl+S |
| Gynecol Obstet Fertil Senol | Institutional ✓ | View PDF button → Ctrl+S |
| Aesthet Surg J (OUP) | Institutional ✓ | PDF button → Ctrl+S |
| JACI (jacionline.org) | Institutional ✓ | Download PDF button → Ctrl+S |
| JAAD (jaad.org) | Institutional ✓ | Download PDF button → Ctrl+S |
| J Hepatol | Institutional ✓ | View PDF button → Ctrl+S |
| Matrix Biology | Institutional ✓ | View PDF button → Ctrl+S |
| Cancer Letters | Institutional ✓ | View PDF button → Ctrl+S |
| Free Radic Biol Med | Institutional ✓ | View PDF button → Ctrl+S |
| Antiviral Res | Institutional ✓ | View PDF button → Ctrl+S |
| Mol Cell Endocrinol | Institutional ✓ | View PDF button → Ctrl+S |
| Neuropharmacology | OA ✓ | View PDF button → Ctrl+S |
| Semin Cancer Biol | Institutional ✓ | View PDF button → Ctrl+S |
| Pharmacol Res | OA ✓ | View PDF button → Ctrl+S |
| Bone | Institutional ✓ | View PDF button → Ctrl+S |
| Gastrointest Endosc | Complimentary ✓ | View PDF button → Ctrl+S |
| Cell Metabolism / Cell Reports | OA ✓ | Download PDF dropdown → Standard PDF → Ctrl+S |
| Am J Pathol | OA ✓ | Download PDF button → Ctrl+S |
| J Mol Cell Cardiol | OA ✓ | Download PDF button → Ctrl+S |
| J Med Chem | PMC ✓ | PMC route → Ctrl+S |
| Biodivers Data J | PMC ✓ | PMC route → Ctrl+S |
| Clin Exp Otorhinolaryngol | PMC ✓ | PMC route → Ctrl+S |
| JACC Cardiovasc Interv | OA ✓ | PDF button → **download icon** (not Ctrl+S) |
| Toxins (MDPI) | OA ✓ | PMC route → Ctrl+S |
| Pediatr Radiol | OA ✓ | PMC route → Ctrl+S |
| Nurs Open | OA ✓ | PMC route → Ctrl+S |
| JMIR | OA ✓ | PMC route → Ctrl+S |
| Free Radic Biol Med (2024+) | ✗ No access | Only "Article preview" → skip |
| J Urol | ✗ No access | "No Access" → skip |
| Int J Cardiol | ✗ No access | "Get Access" → skip |
| Curr Protoc (Wiley) | ✗ No access | "Get access to full version" → skip |
| Radiol Technol | ✗ No full text | No full-text links on PubMed → skip |
| J Heart Lung Transplant | ✗ No access | Only "Article preview" → skip |
| AJO (ajo.com) | ✗ No access | "Get full text access" → skip |
| JHLT (jhltonline.org) | ✗ No access | "Get Access" → skip |
| AACR (aacrjournals.org) | ✗ No access | Redirects to abstract → skip |
| Military Medicine (OUP) | ✗ No access | "Get access" → skip |
| J Appl Microbiol (OUP) | ✗ No access | "Get access" → skip |
| PM R (Wiley) | ✗ No access | "Zhengzhou University does not provide access" → skip |
| SAGE Publications | ✗ Connection timeout | Unreachable → skip |
| J-STAGE | ✗ Page load failure | Unreachable → skip |

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
