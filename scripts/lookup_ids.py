#!/usr/bin/env python3
"""Resolve PMIDs / DOIs into a download queue: PMCID, DOI, Elsevier PII,
Unpaywall mirrors, and best-guess direct PDF / article URLs.

Usage:
  python3 lookup_ids.py --pmids 33108101,25029335 --out queue.json
  python3 lookup_ids.py --dois 10.1038/s41586-020-2649-2,10.1016/j.cell.2020.01.001
  python3 lookup_ids.py --ids 33108101,10.1038/s41586-020-2649-2   # auto-detect
      [--map-file papers.txt]   # optional: "folder|name|pmid" lines for folder/name

Auto-detection (--ids): pure digits → PMID; strings containing "/" and
starting with "10." → DOI.  Anything else is skipped with a warning.

Queue JSON fields per paper:
  folder, name, pmid, doi, pmcid, pii, url, article_url, alt_pdfs
"""
import argparse, json, re, time, urllib.parse, urllib.request

UA = {"User-Agent": "paper-fetch/1.0 (research use)"}


def _get(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def idconv(ids):
    """NCBI idconv: accepts PMIDs or DOIs, returns {pmid: {pmcid, doi}}."""
    url = ("https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/?"
           + urllib.parse.urlencode({"ids": ",".join(ids), "format": "json"}))
    recs = _get(url).get("records", [])
    out = {}
    for r in recs:
        pmid = str(r.get("pmid", ""))
        if pmid:
            out[pmid] = {"pmcid": r.get("pmcid", ""), "doi": r.get("doi", "")}
    return out


def esummary_dois(pmids):
    """Fill DOIs idconv missed (older journals)."""
    url = ("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id="
           + ",".join(pmids) + "&retmode=json")
    data = _get(url)
    out = {}
    for pmid in pmids:
        try:
            doc = data["result"][pmid]
            doi = next((i["value"] for i in doc.get("articleids", [])
                        if i["idtype"] == "doi"), "")
            out[pmid] = {"doi": doi, "journal": doc.get("source", "")}
        except KeyError:
            continue
    return out


def crossref_pii(doi):
    """Elsevier PII from CrossRef alternative-id (strip dashes/brackets)."""
    try:
        msg = _get(f"https://api.crossref.org/works/{urllib.parse.quote(doi)}")["message"]
        alts = msg.get("alternative-id", [])
        pii = alts[0].replace("-", "").replace("(", "").replace(")", "") if alts else ""
        primary = msg.get("resource", {}).get("primary", {}).get("URL", "")
        return pii, primary
    except Exception:
        return "", ""


def unpaywall(doi):
    try:
        d = _get(f"https://api.unpaywall.org/v2/{urllib.parse.quote(doi)}?email=research@example.org")
        pdfs = [l["url_for_pdf"] for l in d.get("oa_locations", []) if l.get("url_for_pdf")]
        return pdfs
    except Exception:
        return []


def direct_url(doi, pmcid, pii):
    if pmcid:
        return f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/pdf/"
    if doi.startswith("10.1016/") and pii:
        return (f"https://www.sciencedirect.com/science/article/pii/{pii}"
                "/pdfft?isDTMRedir=true&download=true")
    if doi.startswith("10.1038/"):
        return f"https://www.nature.com/articles/{doi.split('/', 1)[1]}.pdf"
    if doi.startswith("10.1056/"):
        return f"https://www.nejm.org/doi/pdf/{doi}?download=true"
    if doi.startswith(("10.1002/", "10.1111/")):
        return f"https://onlinelibrary.wiley.com/doi/pdfdirect/{doi}"
    if doi.startswith("10.1007/"):
        return f"https://link.springer.com/content/pdf/{doi}.pdf"
    return ""  # ASH / JAMA / LWW / OUP: see references/publisher_patterns.md


def is_pmid(s):
    """PMID: 1-8 digits (PMIDs are currently up to 9 digits, but keep it loose)."""
    return bool(re.fullmatch(r"\d{1,9}", s.strip()))


def is_doi(s):
    """DOI: starts with '10.' and contains a '/'."""
    s = s.strip()
    return s.startswith("10.") and "/" in s


def auto_detect(raw_ids):
    """Split a mixed list into (pmids, dois). Unknown items are warned and skipped."""
    pmids, dois = [], []
    for raw in raw_ids:
        s = raw.strip()
        if not s:
            continue
        if is_pmid(s):
            pmids.append(s)
        elif is_doi(s):
            dois.append(s)
        else:
            print(f"  WARNING: cannot classify '{s}' (not a PMID or DOI), skipped")
    return pmids, dois


def build_queue(pmids, dois, label, out_path):
    """Core queue builder.  dois are resolved to PMIDs via idconv first."""
    # 1. Resolve DOIs → PMIDs (idconv accepts DOIs and returns pmid in each record)
    if dois:
        doi_conv = idconv(dois)
        time.sleep(0.5)
        # doi_conv is keyed by pmid; collect the pmids that came back
        resolved_pmids = list(doi_conv.keys())
        # Also build a doi→pmid map for DOIs that idconv couldn't resolve
        doi_to_pmid = {}
        for pmid, info in doi_conv.items():
            if info.get("doi"):
                doi_to_pmid[info["doi"].lower()] = pmid
        pmids = pmids + resolved_pmids
        # Report DOIs that failed to resolve
        resolved_dois = {info.get("doi", "").lower() for info in doi_conv.values() if info.get("doi")}
        for d in dois:
            if d.lower() not in resolved_dois:
                print(f"  WARNING: DOI {d} could not be resolved to a PMID")
    else:
        doi_to_pmid = {}

    if not pmids:
        print("No valid PMIDs to process.")
        return

    # 2. idconv for all PMIDs (get pmcid + doi)
    conv = idconv(pmids)
    time.sleep(0.5)

    # 3. esummary for PMIDs missing a DOI
    missing_doi = [p for p in pmids if not conv.get(p, {}).get("doi")]
    extra = esummary_dois(missing_doi) if missing_doi else {}

    # 4. Build queue
    queue = []
    for pmid in pmids:
        c = conv.get(pmid, {})
        doi = c.get("doi") or extra.get(pmid, {}).get("doi", "")
        pmcid = c.get("pmcid", "")
        pii, article_url = ("", "")
        if doi.startswith("10.1016/"):
            pii, article_url = crossref_pii(doi)
            time.sleep(0.3)
        alt_pdfs = unpaywall(doi) if doi else []
        folder, name = label.get(pmid, ("", f"PMID_{pmid}"))
        q = {"folder": folder, "name": name, "pmid": pmid, "doi": doi,
             "pmcid": pmcid, "pii": pii, "article_url": article_url,
             "alt_pdfs": alt_pdfs, "url": direct_url(doi, pmcid, pii)}
        # prefer OA mirrors when the publisher is hard-walled
        if not q["url"] and alt_pdfs:
            q["url"] = alt_pdfs[0].replace("http://", "https://")
        queue.append(q)
        print(f"{pmid}: pmcid={pmcid or '-'} doi={doi or '-'} pii={pii or '-'} "
              f"url={'Y' if q['url'] else 'N'} oa_mirrors={len(alt_pdfs)}")

    json.dump(queue, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nWrote {len(queue)} papers to {out_path}")


def main():
    ap = argparse.ArgumentParser(
        description="Build a paper download queue from PMIDs and/or DOIs.")
    ap.add_argument("--pmids", help="comma-separated PMIDs")
    ap.add_argument("--dois", help="comma-separated DOIs")
    ap.add_argument("--ids", help="comma-separated mixed IDs (auto-detect PMID vs DOI)")
    ap.add_argument("--map-file", help="optional 'folder|name|pmid' lines")
    ap.add_argument("--out", default="queue.json")
    args = ap.parse_args()

    # Collect inputs
    pmids = [p.strip() for p in args.pmids.split(",") if p.strip()] if args.pmids else []
    dois = [d.strip() for d in args.dois.split(",") if d.strip()] if args.dois else []

    if args.ids:
        raw = [x.strip() for x in args.ids.split(",") if x.strip()]
        auto_pmids, auto_dois = auto_detect(raw)
        pmids.extend(auto_pmids)
        dois.extend(auto_dois)

    if not pmids and not dois:
        ap.error("at least one of --pmids, --dois, or --ids is required")

    # Parse optional map file
    label = {}
    if args.map_file:
        for line in open(args.map_file, encoding="utf-8"):
            parts = [p.strip() for p in line.strip().split("|")]
            if len(parts) == 3:
                label[parts[2]] = (parts[0], parts[1])

    print(f"Inputs: {len(pmids)} PMID(s), {len(dois)} DOI(s)")
    build_queue(pmids, dois, label, args.out)


if __name__ == "__main__":
    main()
