#!/usr/bin/env python3
"""
Eexample-facing bilingual site generator.

Renders dist/ (output of build.py) into site/ with parallel language trees:

    site/en/<folder>/<article>.html      ← from  <article>.md   (canonical)
    site/sv/<folder>/<article>.html      ← from  <article>.sv.md (derived)
    site/en/index.html, site/sv/index.html, site/index.html (→ en)

Reader features per language: question search (from `answers`), task-based
entry points, In-short/Kort-svar answer boxes, EN⇄SV toggle on every page
(links to the counterpart article when it exists, otherwise to the other
language's home). Swedish pages whose canonical changed since translation
get a visible "being updated" notice — driven by the translated_from hash.

Usage: python3 scripts/build_site.py   (run after build.py)

Review mode (HANDBOOK_SITE_MODE=review) writes dist/review-site/ for the
password-protected HR review site: a review bar and noindex on every page, and
on each unapproved article its ID, content version (the English reader hash
that one approval covers in both languages) and a feedback button. The button
uses local read-only review metadata; external forms are disabled. The
literal values ARTICLE and VERSION are replaced per article.
"""

import html
import json
import os
import pathlib
import re
import shutil
import sys
import posixpath
from urllib.parse import urlsplit, unquote

import markdown
import yaml
from bs4 import BeautifulSoup
import authoring
import questions

from source_loader import (body_of, counterpart_status, load_registry,
                           local_path, split_frontmatter)

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROJECT = yaml.safe_load((ROOT / "project.yaml").read_text()) if (ROOT / "project.yaml").exists() else {}
DISPLAY_NAME = PROJECT.get("display_name", "Synthetic publishing demo")
DIST, SITE, CONTENT = ROOT / "dist", ROOT / "site", ROOT / "content"
ASSETS = ROOT / "web" / "assets"
REVIEW = os.environ.get("HANDBOOK_SITE_MODE") == "review"

if REVIEW:
    SITE = DIST / "review-site"

STR = {
    "en": dict(hero="What do you need to know?",
               sub="Type your question the way you'd ask a colleague.",
               placeholder="e.g. what if I get sick during my vacation?",
               browse="Or browse by topic", soon="Coming soon",
               draft="⚠️ Draft — under review, details may change. When in doubt, ask HR.",
               stale="🔄 The English original was updated recently — this Swedish "
                     "version is being refreshed. The English page is the current one.",
               reviewed="reviewed by", notyet="not yet reviewed",
               sources="sources", toggle="Svenska", home="Handbook",
               search="Search the handbook", results="Search results",
               header_search="Header search", hero_search="Find an answer",
               empty="No matching answers. Try another word or browse by topic.",
               search_error="Search is unavailable. You can still browse by topic.",
               result_count="{count} results", skip="Skip to content",
               topics="Browse topics", shortcuts="Quick ways to get started",
               breadcrumb="You are here", table="Scrollable table",
               tagline="salary · leave · travel · everything employment",
               review_bar="Review copy for HR — not the published handbook. Do not share outside the review.",
               review_ready="Ready for your approval. One approval covers the English and Swedish versions.",
               review_wait="Not ready for approval yet: open company questions or figure checks remain. "
                           "Reading it is still useful.",
               review_button="Approve or request a change", review_noform="feedback form not configured",
               review_id="Article", review_version="Version"),
    "sv": dict(hero="Vad vill du veta?",
               sub="Skriv din fråga som du skulle ställa den till en kollega.",
               placeholder="t.ex. vad händer om jag blir sjuk under semestern?",
               browse="Eller bläddra per ämne", soon="Kommer snart",
               draft="⚠️ Utkast — under granskning, detaljer kan ändras. Fråga HR om du är osäker.",
               stale="🔄 Det engelska originalet har uppdaterats — den här svenska "
                     "versionen håller på att uppdateras. Den engelska sidan gäller.",
               reviewed="granskad av", notyet="ännu inte granskad",
               sources="källor", toggle="English", home="Handboken",
               search="Sök i handboken", results="Sökresultat",
               header_search="Sök i sidhuvudet", hero_search="Hitta ett svar",
               empty="Inga svar hittades. Prova ett annat ord eller bläddra per ämne.",
               search_error="Sökningen är inte tillgänglig. Du kan fortfarande bläddra per ämne.",
               result_count="{count} resultat", skip="Hoppa till innehållet",
               topics="Bläddra per ämne", shortcuts="Hitta rätt direkt",
               breadcrumb="Du är här", table="Rullningsbar tabell",
               tagline="lön · ledighet · resor · allt om din anställning",
               review_bar="Granskningskopia för HR — inte den publicerade handboken. Dela inte utanför granskningen.",
               review_ready="Klar för godkännande. Ett godkännande gäller både den svenska och den engelska versionen.",
               review_wait="Inte klar för godkännande än: öppna frågor eller sifferkontroller återstår. "
                           "Läs gärna ändå.",
               review_button="Godkänn eller begär ändring", review_noform="formuläret är inte inställt",
               review_id="Artikel", review_version="Version"),
}

TASKS = {
    "en": [("I'm going on a business trip", "what you get paid and how to claim it",
            "business-trips/03-subsistence-allowance.html"),
           ("I drove my own car for work", "mileage compensation and the driving log",
            "business-trips/02-car-compensation.html"),
           ("I paid for something myself", "getting reimbursed for outlays",
            "business-trips/04-expenses.html"),
           ("I need money up front for a trip", "travel advances",
            "business-trips/06-travel-advances.html")],
    "sv": [("Jag ska ut på tjänsteresa", "vad du får och hur du redovisar",
            "business-trips/03-subsistence-allowance.html"),
           ("Jag behöver pengar i förskott", "reseförskott",
            "business-trips/06-travel-advances.html")],
}

def search_html(lang, prefix, name="header"):
    """One independent search control, sharing the language's existing index."""
    s = STR[lang]
    identifier = "q" if name == "hero" else "header-q"
    attributes = {
        "data-index": prefix + "search-index.json",
        "data-empty": s["empty"],
        "data-error": s["search_error"],
        "data-count": s["result_count"],
    }
    data = " ".join(f'{key}="{html.escape(value, quote=True)}"'
                    for key, value in attributes.items())
    return f"""<div class="searchbox search-{name}" role="search" aria-label="{s[name + '_search']}" {data}>
<label for="{identifier}">{s['search']}</label>
<input id="{identifier}" type="search" autocomplete="off"
 placeholder="{html.escape(s['placeholder'], quote=True)}" aria-controls="{name}-results">
<div id="{name}-results" class="search-results" role="region" aria-label="{s['results']}" hidden></div>
<p class="sr-only search-status" role="status" aria-live="polite" aria-atomic="true"></p>
</div>"""


def topic_navigation(folder_lists, lang, url):
    """Use actual language-specific pages; expand the current article's topic."""
    groups = []
    directory = posixpath.dirname(url)
    for title, articles in sorted(folder_lists.items()):
        current_group = any(target == url for _, target in articles)
        links = []
        for label, target in articles:
            current = ' aria-current="page"' if target == url else ""
            href = posixpath.relpath(target, directory)
            links.append(f'<li><a href="{html.escape(href, quote=True)}"{current}>'
                         f'{html.escape(label)}</a></li>')
        opened = " open" if current_group else ""
        groups.append(f'<details class="topic-group"{opened}><summary>{html.escape(title)}</summary>'
                      + '<ul>' + "".join(links) + '</ul></details>')
    label = STR[lang]["topics"]
    # Open by default so all topics remain available if JavaScript is disabled.
    # The shared script manages only the outer mobile disclosure at breakpoints.
    return (f'<aside class="sidebar"><details class="topic-menu" open>'
            f'<summary>{label}</summary><nav aria-label="{label}">'
            + "".join(groups) + '</nav></details></aside>')


def page(title, body_html, lang, toggle_href, url="index.html", sidebar=""):
    s = STR[lang]
    directory = posixpath.dirname(url)
    prefix = posixpath.relpath(".", directory)
    prefix = "" if prefix == "." else prefix + "/"
    assets = prefix + "../assets/"
    layout = "article-layout" if sidebar else "home-layout"
    robots = '\n<meta name="robots" content="noindex,nofollow">' if REVIEW else ""
    review_bar = '<div role="note" class="draftnote">Synthetic demonstration — fixture replay, no real approval.</div>'
    return f"""<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">{robots}
<title>{html.escape(title)} · {html.escape(DISPLAY_NAME)} · {s['home']}</title>
<link rel="stylesheet" href="{assets}handbook.css">
<script src="{assets}handbook.js" defer></script></head>
<body><a class="skip-link" href="#main">{s['skip']}</a>{review_bar}
<header class="site"><div class="shell header-inner">
<a class="brand" href="{prefix}index.html" aria-label="{html.escape(DISPLAY_NAME)} · {s['home']}">
<span aria-hidden="true">◈</span>
<span class="brand-title">{s['home']}</span></a>
{search_html(lang, prefix)}
<a class="lang" href="{html.escape(toggle_href, quote=True)}" lang="{'sv' if lang == 'en' else 'en'}">{s['toggle']}</a>
</div></header>
<div class="shell {layout}">{sidebar}<main id="main" tabindex="-1">{body_html}</main></div>
<footer class="site-footer shell"><span>{html.escape(DISPLAY_NAME)}</span><span>{s['home']}</span></footer>
</body></html>"""


def scrollable_tables(rendered, lang):
    """Preserve table semantics while confining overflow to a keyboard-accessible region."""
    soup = BeautifulSoup(rendered, "html.parser")
    for number, table in enumerate(soup.find_all("table"), 1):
        wrapper = soup.new_tag("div", attrs={"class": "table-scroll", "tabindex": "0",
                                            "role": "region", "aria-label": f'{STR[lang]["table"]} {number}'})
        table.wrap(wrapper)
    return str(soup)


def canonical_hash(rel_md, mode=None):
    """sha256[:12] of the English canonical content file for staleness check."""
    p = CONTENT / rel_md
    return authoring.translation_hash(p.read_text(encoding="utf-8"), mode) if p.exists() else None


def review_panel(rel, lang, ready):
    """Article ID, approved-content version and feedback button for the review site."""
    s = STR[lang]
    en_rel = rel.as_posix().replace(".sv.md", ".md")
    article = en_rel.removesuffix(".md")
    version = canonical_hash(en_rel, "reader-v1") or ""
    if en_rel not in ready:
        action = f"<p>{s['review_wait']}</p>"
    else:
        action = f"<p>{s['review_ready']} ({s['review_noform']})</p>"
    return (f'<aside class="reviewpanel">{action}<p class="reviewmeta">{s["review_id"]}: <code>{html.escape(article)}</code> · '
            f'{s["review_version"]}: <code>{html.escape(version)}</code></p></aside>')


def folder_label(key, entry, lang, registry, root):
    if entry.get('title_' + lang):
        return entry['title_' + lang]
    if lang == 'sv':
        company = registry.get('company_' + key.replace('-', '_'), {})
        try:
            path = local_path(root, company['paths']['sv'])
            fm, _ = split_frontmatter(path.read_text(encoding='utf-8'))
            return fm['title']
        except (KeyError, ValueError, FileNotFoundError):
            pass
    return entry.get('title', key)


def source_panel(fm, relative_article, lang, registry, root):
    label = "Sources and rules" if lang == "en" else "Källor och regler"
    record = authoring.load_review(root, relative_article)
    items = []
    for sid in fm.get("sources", []):
        source = registry.get(sid, {})
        name = html.escape(source.get("title", sid))
        url = source.get("url")
        if url and urlsplit(str(url)).scheme in ("https", "http"):
            name = f'<a href="{html.escape(url, quote=True)}">{name}</a>'
        # Claim descriptions, questions and internal workflow never enter this panel.
        provisions = sorted({str(c["provision"]) for c in record.get("claims", [])
                             if c.get("source") == sid and c.get("provision")})
        # Exact primary-source headings/provisions remain authentic identifiers
        # in both views, not translated claim descriptions or HR instructions.
        if provisions:
            name += ": " + html.escape("; ".join(provisions))
        items.append(f"<li>{name}</li>")
    return (f'<details class="sources"><summary>{label}</summary><ul>'
            + "".join(items) + "</ul></details>") if items else ""


def article_links(rendered, lang, url, pages):
    """Resolve content Markdown links against actual generated pages."""
    soup = BeautifulSoup(rendered, "html.parser")
    for link in soup.find_all("a", href=True):
        parsed = urlsplit(link["href"])
        if parsed.scheme or parsed.netloc or not parsed.path:
            continue
        if not parsed.path.endswith((".md", ".html")):
            continue
        target = posixpath.normpath(posixpath.join(posixpath.dirname(url), unquote(parsed.path)))
        explicit_sv = target.endswith(".sv.md")
        target = target.removesuffix(".md").removesuffix(".sv") + ".html" if target.endswith(".md") else target
        target_lang = "sv" if explicit_sv else lang
        if (target_lang, target) not in pages and target_lang == "sv" and ("en", target) in pages:
            target_lang = "en"
            link.append(" (English)")
        if (target_lang, target) in pages:
            actual = f"{target_lang}/{target}"
            current = f"{lang}/{posixpath.dirname(url)}"
            link["href"] = posixpath.relpath(actual, current) + ("?" + parsed.query if parsed.query else "") + ("#" + parsed.fragment if parsed.fragment else "")
    return str(soup)


def check_links(site, strict_pages):
    """All local targets are checked; legacy failures stay visible as warnings."""
    errors, warnings = [], []
    for path in sorted(site.rglob("*.html")):
        soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
        for link in soup.find_all("a", href=True):
            href = link["href"]
            parsed = urlsplit(href)
            if parsed.scheme or parsed.netloc:
                continue
            target = (path.parent / unquote(parsed.path)).resolve() if parsed.path else path.resolve()
            problem = None
            if not target.is_relative_to(site.resolve()) or not target.is_file():
                problem = "missing local target"
            elif parsed.fragment and target.suffix == ".html":
                target_soup = soup if target == path.resolve() else BeautifulSoup(target.read_text(encoding="utf-8"), "html.parser")
                if target_soup.find(id=unquote(parsed.fragment)) is None:
                    problem = "missing anchor"
            if problem:
                message = f"{path.relative_to(site)}: {problem}: {href}"
                (errors if path in strict_pages else warnings).append(message)
    return errors, warnings


def introduction_html(lang, root=ROOT):
    """Render only maintained introduction material; report unavailable translations."""
    entry = load_registry(root).get(PROJECT.get("introduction_source", "company_introduction"))
    if entry is None:
        return '<article class="introduction"><h2>Synthetic demonstration</h2><p>Fictional rules and illustrative evidence only.</p></article>'
    unavailable = {
        "en": "The introduction is being updated. Read the Swedish introduction.",
        "sv": "Introduktionen är inte tillgänglig just nu.",
    }
    try:
        if not entry:
            raise ValueError("company_introduction is not registered")
        path = local_path(root, entry["paths"][lang])
        if lang != entry["maintained_language"]:
            _, current, reason = counterpart_status(entry, root, lang)
            if not current:
                raise ValueError(reason)
        body = body_of(path.read_text(encoding="utf-8"))
    except (ValueError, FileNotFoundError, KeyError) as exc:
        print(f"⚠️  Introduction {lang}: {exc}", file=sys.stderr)
        link = '<a href="../sv/index.html">Svenska</a>' if lang == "en" else ""
        return f'<div class="stalenote">{unavailable[lang]} {link}</div>'
    if "legacy system" in body:
        print(f"⚠️  Introduction {lang}: obsolete legacy system maintenance claim; "
              "editorial decision tracked as 00-Q1 in migration notes", file=sys.stderr)
    # The source's title is the homepage introduction title, below the search heading.
    rendered = markdown.markdown(body, extensions=["tables"])
    rendered = re.sub(r"<h1>(.*?)</h1>", r"<h2>\1</h2>", rendered, flags=re.S)
    return f'<article class="introduction">{rendered}</article>'


def main():
    schema = yaml.safe_load((ROOT / "schema.yaml").read_text(encoding="utf-8"))["folders"]
    registry = load_registry(ROOT)
    records = questions.load_questions(ROOT)
    SITE.mkdir(exist_ok=True)
    (SITE / "assets").mkdir(exist_ok=True)
    for name in ("handbook.css", "handbook.js"):
        shutil.copyfile(ASSETS / name, SITE / "assets" / name)
    indexes = {"en": [], "sv": []}
    folder_lists = {"en": {}, "sv": {}}
    rendered_folders = {"en": set(), "sv": set()}
    pages = {}  # (lang, url) → exists, for toggle targets
    strict_pages = set()
    if REVIEW:
        from export_signoff import ready_articles
        ready = set(ready_articles(ROOT))

    articles = []
    for src in sorted(DIST.rglob("*.md")):
        rel = src.relative_to(DIST)
        # dist/ also holds sanitized extracts, prompts and reviewer artifacts.
        # Only article output in schema folders belongs on the employee site.
        if len(rel.parts) != 2 or rel.parts[0] not in schema:
            continue
        lang = "sv" if rel.name.endswith(".sv.md") else "en"
        raw = src.read_text(encoding="utf-8")
        unverified_figures = raw.startswith("> ⚠️ **DRAFT — NOT FOR PUBLICATION.")
        if raw.startswith(">"):
            _, _, raw = raw.partition("\n\n")
        fm, body = (None, raw)
        if raw.startswith("---"):
            parts = raw.split("---", 2)
            fm, body = yaml.safe_load(parts[1]), parts[2]
        fm = fm or {}
        fm = authoring.effective_metadata(ROOT, rel, fm)
        status = str(fm.get("status", "draft"))
        if status in ("spec", "not_started", "retired"):
            continue
        url = str(rel.with_suffix("").as_posix()).replace(".sv", "") + ".html"
        articles.append((lang, url, rel, fm, body, status, unverified_figures))
        pages[(lang, url)] = True

    # Collect navigation before rendering so every article gets the complete tree.
    for lang, url, rel, fm, body, status, unverified_figures in articles:
        title = fm.get("title", rel.stem)
        folder_title = folder_label(rel.parent.name, schema.get(rel.parent.name, {}), lang, registry, ROOT)
        folder_lists[lang].setdefault(folder_title, []).append((title, url))
        rendered_folders[lang].add(rel.parent.name)

    for lang, url, rel, fm, body, status, unverified_figures in articles:
        s = STR[lang]
        title = fm.get("title", rel.stem)
        folder_title = folder_label(rel.parent.name, schema.get(rel.parent.name, {}), lang, registry, ROOT)

        body_html = markdown.markdown(body, extensions=["tables", "footnotes", "toc"])
        body_html = article_links(body_html, lang, url, pages)
        body_html = scrollable_tables(body_html, lang)
        answer_h2 = "Kort svar" if lang == "sv" else "In short"
        body_html = re.sub(
            rf'(<h2(?: id="[^"]*")?>{answer_h2}</h2>.*?)(?=<h2|\Z)',
            r'<div class="inshort">\1</div>', body_html, count=1, flags=re.S)

        notes = ""
        pending = bool(questions.referenced(fm, records, open_only=True))
        if status != "live":
            draft_notice = s["draft"]
            if unverified_figures:
                draft_notice = ("Draft — some amounts or rates are still awaiting verification."
                                if lang == "en" else "Utkast — vissa belopp eller nivåer behöver fortfarande verifieras.")
            if pending:
                if not unverified_figures:
                    draft_notice = "Draft — under review." if lang == "en" else "Utkast — under granskning."
                draft_notice += (" Some company details are awaiting confirmation; follow the qualifications in the text."
                                 if lang == "en" else " Vissa företagsuppgifter behöver bekräftas; följ villkoren i texten.")
            notes += f'<div class="draftnote">{draft_notice}</div>'
        if pending and status == "live":
            notice = ("Some company details on this page are awaiting confirmation. Follow the specific qualifications in the text."
                      if lang == "en" else "Vissa företagsuppgifter på sidan behöver bekräftas. Följ de särskilda villkoren i texten.")
            notes += f'<p class="questionnote">{notice}</p>'
        if REVIEW and status != "live":
            notes = review_panel(rel, lang, ready) + notes
        if lang == "sv":
            en_rel = str(rel.as_posix()).replace(".sv.md", ".md")
            mode = fm.get("translation_hash_mode")
            if fm.get("translated_from") and canonical_hash(en_rel, mode) \
               and fm["translated_from"] != canonical_hash(en_rel, mode):
                notes += f'<div class="stalenote">{s["stale"]}</div>'

        other = "sv" if lang == "en" else "en"
        counterpart = url if (other, url) in pages else "index.html"
        toggle = posixpath.relpath(f"{other}/{counterpart}", f"{lang}/{posixpath.dirname(url)}")

        badge = "" if status == "live" else f' <span class="badge draft">{html.escape(status.upper())}</span>'
        crumb = (f'<nav class="crumb" aria-label="{s["breadcrumb"]}">'
                 f'<a href="../index.html">{s["home"]}</a><span aria-hidden="true">/</span>'
                 f'<span>{html.escape(folder_title)}</span>{badge}</nav>')

        reviewed = fm.get("reviewed_by") or s["notyet"]
        meta = (source_panel(fm, rel, lang, registry, ROOT)
                + f'<footer class="meta">{s["reviewed"]}: {html.escape(str(reviewed))} · status: {html.escape(status)}</footer>')

        out = SITE / lang / url
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page(title, crumb + f"<article><h1>{html.escape(title)}</h1>{notes}{body_html}{meta}</article>",
                            lang, toggle, url, topic_navigation(folder_lists[lang], lang, url)), encoding="utf-8")
        if fm.get("authoring_version") == authoring.VERSION:
            strict_pages.add(out)

        # Index reader text, excluding source panels and footnote provenance.
        search_soup = BeautifulSoup(body_html, "html.parser")
        for extra in search_soup.select(".footnote, details"):
            extra.decompose()
        excerpt = search_soup.get_text(" ", strip=True)[:400]
        indexes[lang].append({"title": title, "url": url, "folder": folder_title,
                              "questions": fm.get("answers", []), "excerpt": excerpt})

    # ---- landing pages per language ----
    for lang in ("en", "sv"):
        s = STR[lang]
        tasks_html = "".join(
            f'<a href="{u}">{html.escape(t)}<small>{html.escape(d)}</small></a>'
            for t, d, u in TASKS[lang] if (lang, u) in pages)
        folders_html = ""
        for ftitle, arts in sorted(folder_lists[lang].items()):
            lis = "".join(f'<li><a href="{u}">{html.escape(t)}</a></li>' for t, u in arts)
            folders_html += f"<section><h3>{html.escape(ftitle)}</h3><ul>{lis}</ul></section>"
        coming = [folder_label(k, v, lang, registry, ROOT) for k, v in schema.items()
                  if isinstance(v, dict) and k not in rendered_folders[lang] and k != "proposed_additions"]
        if coming:
            folders_html += (f"<section><h3>{s['soon']}</h3><ul>"
                             + "".join(f'<li class="soon">{html.escape(c)}</li>' for c in coming)
                             + "</ul></section>")
        hero = f"""
<section class="hero" aria-labelledby="hero-title"><span class="hero-shape" aria-hidden="true"></span>
<p class="eyebrow">{html.escape(DISPLAY_NAME)} · {s['home']}</p>
<h1 id="hero-title">{s['hero']}</h1><p class="hero-sub">{s['sub']}</p>
{search_html(lang, '', 'hero')}</section>
<section class="quick-start" aria-labelledby="quick-title"><h2 id="quick-title">{s['shortcuts']}</h2>
<div class="tasks">{tasks_html}</div></section>
<section class="browse-section" aria-labelledby="browse-title"><h2 id="browse-title">{s['browse']}</h2>
<div class="folders">{folders_html}</div></section>
{introduction_html(lang)}"""
        landing = page(s['home'], hero, lang, f"../{('sv' if lang=='en' else 'en')}/index.html")
        (SITE / lang / "index.html").write_text(landing, encoding="utf-8")
        (SITE / lang / "search-index.json").write_text(
            json.dumps(indexes[lang], ensure_ascii=False), encoding="utf-8")

    (SITE / "index.html").write_text(
        '<!doctype html><meta charset="utf-8">'
        '<meta http-equiv="refresh" content="0;url=en/index.html">'
        '<a href="en/index.html">English</a> · <a href="sv/index.html">Svenska</a>',
        encoding="utf-8")

    # Preserve old pre-bilingual URLs without serving obsolete copies of policy.
    for lang, url in pages:
        legacy = SITE / url
        if lang == "en" and legacy.is_file():
            target = posixpath.relpath("en/" + url, posixpath.dirname(url))
            legacy.write_text('<!doctype html><html lang="en"><meta charset="utf-8">'
                              + '<meta http-equiv="refresh" content="0;url=' + html.escape(target, quote=True) + '">'
                              + '<a href="' + html.escape(target, quote=True) + '">Open the current handbook page</a></html>', encoding="utf-8")

    n_en, n_sv = len(indexes["en"]), len(indexes["sv"])
    link_errors, link_warnings = check_links(SITE, strict_pages)
    for warning in link_warnings:
        print(f"⚠️  Legacy link: {warning}")
    if link_errors:
        sys.exit("Broken article links:\n" + "\n".join(link_errors))
    print(f"✓ Site built → {SITE}  (en: {n_en} articles / "
          f"{sum(len(e['questions']) for e in indexes['en'])} questions; "
          f"sv: {n_sv} articles / "
          f"{sum(len(e['questions']) for e in indexes['sv'])} questions)")
    print("  Toggle EN⇄SV on every page; Swedish staleness notices are "
          "hash-driven. Publish site/ behind company login.")
    if REVIEW:
        print(f"  Review mode: {len(ready)} article(s) open for approval"
              + "; external forms excluded")


if __name__ == "__main__":
    main()
