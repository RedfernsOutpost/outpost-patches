"""The parts of the site that can't be plain files. .github/workflows/deploy.yml runs this on every push to main,
including every save in the site editor (admin/), and publishes the result. Nothing it makes is committed.

- projects/<id>/index.html: each project's own page, made from project.html, with its own link preview (title,
  summary and a 1200 x 630 share.jpg) that Discord, iMessage and the rest can read without running JavaScript.
  The page's words are written into it ahead of time too (search engines read them without running site.js),
  plus structured data for Google (JSON-LD) and Safari's App Store banner for apps that have an App Store link
- the home page's Games and Projects cards, written in ahead of time for the same reason
- the home page's banner line and About section, from site.json, written into index.html
- assets/img/share.jpg, assets/img/share-patcher.jpg and sitemap.xml

To see the pages locally (needs Pillow):  python tools/build-pages.py
A problem with one project (no page address, a missing picture) is reported and skipped, so the rest still publish.
"""
import html
import json
import pathlib
import re
import urllib.parse

from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).resolve().parent.parent
FONTS = pathlib.Path(__file__).resolve().parent / "fonts"  # Alegreya and Alegreya Sans, OFL (see the OFL files there)
SITE = "https://redfernsoutpost.com/"
NAME = "Redfern's Outpost"
W, H = 1200, 630
BG, TEXT, MUTED, ACCENT = (19, 17, 14), (239, 230, 214), (168, 154, 136), (207, 122, 58)
PAGE_ID = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")


def warn(message):
    # the ::warning:: prefix shows the message on the run's page in GitHub Actions
    print("::warning::" + message)


def title_font(size):
    fnt = ImageFont.truetype(str(FONTS / "Alegreya-Variable.ttf"), size)
    fnt.set_variation_by_axes([700])
    return fnt


def body_font(size, bold=False):
    return ImageFont.truetype(str(FONTS / ("AlegreyaSans-Bold.ttf" if bold else "AlegreyaSans-Regular.ttf")), size)


def fitted_title(draw, text, size, width):
    """The title font at `size`, made smaller until the text fits in `width`."""
    while size > 40 and draw.textlength(text, font=title_font(size)) > width:
        size -= 4
    return title_font(size)


def local(path):
    """A path from the data files ("/projects/x.png") as a file in this repository, or None."""
    if not path:
        return None
    file = (ROOT / str(path).lstrip("/")).resolve()
    return file if file.is_file() and file.is_relative_to(ROOT) else None


def load(name, default=None):
    file = ROOT / name
    if default is not None and not file.exists():
        return default
    return json.loads(file.read_text(encoding="utf-8"))


def cover(im, anchor="center", resample=Image.LANCZOS):
    """Scale to fill W x H, then crop the overflow (anchor "top" keeps the top of the picture)."""
    s = max(W / im.width, H / im.height)
    im = im.convert("RGB").resize((round(im.width * s), round(im.height * s)), resample)
    x = (im.width - W) // 2
    y = 0 if anchor == "top" else (im.height - H) // 2
    return im.crop((x, y, x + W, y + H))


def wrap(draw, text, fnt, width):
    lines, line = [], ""
    for word in text.split():
        test = (line + " " + word).strip()
        if draw.textlength(test, font=fnt) <= width:
            line = test
        else:
            lines.append(line)
            line = word
    return lines + [line] if line else lines


def shadowed(draw, xy, text, fnt, fill):
    draw.text((xy[0] + 3, xy[1] + 3), text, font=fnt, fill=(10, 8, 6))
    draw.text(xy, text, font=fnt, fill=fill)


def banner_image(title, subtitle):
    """The home banner (the cabin at dusk) with a title over the sky."""
    banner = Image.open(ROOT / "assets/img/banner.png")
    crop_w = round(banner.height * W / H)
    im = cover(banner.crop((banner.width - crop_w, 0, banner.width, banner.height)), resample=Image.NEAREST)
    draw = ImageDraw.Draw(im)
    shadowed(draw, (64, 50), title, fitted_title(draw, title, 92, W - 128), TEXT)
    shadowed(draw, (68, 160), subtitle, body_font(40, bold=True), TEXT)
    return im


def icon_image(p, icon_file):
    """An app: its icon beside its name and summary."""
    im = Image.new("RGB", (W, H), BG)
    icon = Image.open(icon_file).convert("RGBA")
    size = 384
    side = min(icon.size)  # a picture that isn't square is cut to its middle, not squashed
    icon = icon.crop(((icon.width - side) // 2, (icon.height - side) // 2,
                      (icon.width - side) // 2 + side, (icon.height - side) // 2 + side))
    # sharp pixels first, then down to size, so pixel-art icons stay crisp without uneven pixels
    if side <= 1024:
        icon = icon.resize((side * 3, side * 3), Image.NEAREST)
    icon = icon.resize((size, size), Image.LANCZOS)
    top = (H - size) // 2
    im.paste(icon, (80, top), icon)
    draw = ImageDraw.Draw(im)
    x, width = 80 + size + 64, W - (80 + size + 64) - 72
    draw.text((x, top), p["title"], font=fitted_title(draw, p["title"], 80, width), fill=TEXT)
    y = top + 112
    body = body_font(34)
    for line in wrap(draw, p.get("summary", ""), body, width)[:5]:
        draw.text((x, y), line, font=body, fill=MUTED)
        y += 44
    draw.text((x, top + size - 36), "redfernsoutpost.com", font=body_font(30, bold=True), fill=ACCENT)
    return im


def project_image(p):
    picture = local(p.get("cover"))
    if not picture:
        if p.get("cover"):
            warn(f"{p['title']}: its main picture {p['cover']} isn't on the site, so its link preview uses the banner")
        return banner_image(p["title"], " · ".join(filter(None, [p.get("kind"), p.get("platform")])))
    if p.get("coverStyle") == "icon":
        return icon_image(p, picture)
    # a website's screenshot keeps its top (the header); a game's keeps its middle
    return cover(Image.open(picture), "top" if p.get("kind") == "Website" else "center")


# ---------------------------------------------------------------- the words of a page, ahead of time
# These mirror site.js (renderProject and projectCard), which redraws the same markup once it runs.
# Change one, change the other.

APP_STORE_BADGE = "https://toolbox.marketingtools.apple.com/api/v2/badges/download-on-the-app-store/black/en-us"
CATEGORIES = {  # the editor's "App category" -> schema.org's names, for Google
    "Entertainment": "EntertainmentApplication", "Utilities": "UtilitiesApplication",
    "Games": "GameApplication", "Lifestyle": "LifestyleApplication", "Food & Drink": "LifestyleApplication",
    "Productivity": "BusinessApplication", "Education": "EducationalApplication", "Reference": "ReferenceApplication",
}


def esc(text):
    return html.escape(str(text or ""), quote=True)


def safe_url(url):
    """Only web addresses and the site's own files, like safeUrl in site.js."""
    url = str(url or "").strip()
    return url if re.match(r"(https?://|/)", url) and not url.startswith("//") else None


def absolute(path):
    return SITE + str(path).lstrip("/") if str(path).startswith("/") else str(path)


def meta_line(parts):
    spans = "".join(f'<span class="{c}">{esc(t)}</span>' if c else f"<span>{esc(t)}</span>" for t, c in parts if t)
    return f'<div class="meta">{spans}</div>'


def store_badge(url):
    href = safe_url(url)
    if not href:
        return ""
    return (f'<a class="store-badge" href="{esc(href)}" target="_blank" rel="noopener">'
            f'<img src="{APP_STORE_BADGE}" alt="Download on the App Store" width="144" height="48"></a>')


def cover_class(p):
    return " smooth" if p.get("smooth") or p.get("coverSmooth") else ""


def card(p):
    """One card on the home page (projectCard in site.js)."""
    href = "projects/" + p["id"] + "/"
    meta_html = meta_line([(p.get("kind"), "kind"), (p.get("platform"), ""), (p.get("status"), "good")])
    if p.get("featured") and p.get("cover") and p.get("coverStyle") != "icon":
        return (f'<a class="feature" href="{esc(href)}"><img class="{cover_class(p).strip()}" src="{esc(p["cover"])}" alt="{esc(p["title"])}">'
                f'<div><div class="eyebrow">The main game</div><h3>{esc(p["title"])}</h3>'
                f'<p class="summary">{esc(p.get("summary"))}</p>{meta_html}<div class="more">Take a look →</div></div></a>')
    if p.get("cover") and p.get("coverStyle") == "icon":
        thumb = f'<img class="thumb icon" src="{esc(p["cover"])}" alt="">'
    elif p.get("cover"):
        thumb = f'<img class="thumb shot{cover_class(p)}" src="{esc(p["cover"])}" alt="">'
    else:
        initials = "".join(w[:1] for w in str(p["title"]).split()[:2]).upper()
        thumb = f'<span class="thumb initials" aria-hidden="true">{esc(initials)}</span>'
    return (f'<a class="item" href="{esc(href)}">{thumb}<div><h3>{esc(p["title"])}</h3>'
            f'<p class="summary">{esc(p.get("summary"))}</p>{meta_html}</div></a>')


def project_body(p):
    """What renderProject in site.js draws into <div id="project">."""
    title = esc(p["title"])
    is_icon = p.get("cover") and p.get("coverStyle") == "icon"
    icon = f'<img class="app-icon" src="{esc(p["cover"])}" alt="{title} icon">' if is_icon else ""
    out = [f'<div class="detail-head">{icon}<div><div class="eyebrow">{esc(p.get("kind") or "Project")}</div>'
           f'<h1>{title}</h1><p class="lede">{esc(p.get("summary"))}</p>'
           f'{meta_line([(p.get("platform"), ""), (p.get("status"), "good")])}{store_badge(p.get("appStore"))}</div></div>']

    shots = list(p.get("screenshots") or [])
    wide = bool(shots) and not re.search(r"\.(jpe?g)$", str(shots[0]), re.I)
    if wide and p.get("cover") and not is_icon:
        out.append(f'<img class="hero-shot{cover_class(p)}" src="{esc(p["cover"])}" alt="{title}">')
        shots = [s for s in shots if s != p["cover"]]

    left = [f'<section class="block"><h2>About</h2>{paragraphs(p.get("description") or p.get("summary"), "")}</section>']
    if p.get("features"):
        items = "".join(f"<li>{esc(f)}</li>" for f in p["features"])
        left.append(f'<section class="block"><h2>Features</h2><ul class="features">{items}</ul></section>')
    if shots:
        imgs = "".join(f'<img src="{esc(s)}" alt="{title} screenshot">' for s in shots)
        note = f'<p class="muted" style="margin-top:14px">{esc(p["screenshotNote"])}</p>' if p.get("screenshotNote") else ""
        classes = "shots" + ("" if wide else " tall") + (" smooth" if p.get("smooth") else "")
        left.append(f'<section class="block"><h2>Screenshots</h2><div class="{classes}">{imgs}</div>{note}</section>')

    right = []
    glance = [(k, v) for k, v in (("Price", p.get("price")), ("Requires", p.get("requires"))) if v]
    if glance:
        rows = "".join(f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in glance)
        right.append(f'<div class="block"><h2>At a glance</h2><dl class="glance">{rows}</dl></div>')
    badge = store_badge(p.get("appStore"))
    links = []
    for i, link in enumerate(p.get("links") or []):
        url = safe_url(link.get("url"))
        if url:
            primary = " primary" if i == 0 and not badge else ""
            links.append(f'<a class="btn block{primary}" href="{esc(url)}" target="_blank" rel="noopener">{esc(link.get("label") or url)}</a>')
    if links:
        right.append(f'<div class="block"><h2>Links</h2>{"".join(links)}</div>')
    downloads = []
    for i, d in enumerate(p.get("downloads") or []):
        url = safe_url(d.get("file"))
        if url:
            name = urllib.parse.unquote(urllib.parse.urlparse(url).path.rsplit("/", 1)[-1])
            primary = " primary" if i == 0 and not links else ""
            downloads.append(f'<div class="download"><a class="btn block{primary}" href="{esc(url)}" download="{esc(name)}">'
                             f'{esc(d.get("label") or "Download")}</a><p class="game">{esc(name)}</p></div>')
    if downloads:
        right.append(f'<div class="block"><h2>Downloads</h2>{"".join(downloads)}</div>')
    if p.get("note"):
        right.append(f'<div class="block note"><p class="muted">{esc(p["note"])}</p></div>')

    if right:
        out.append(f'<div class="layout"><div>{"".join(left)}</div><aside>{"".join(right)}</aside></div>')
    else:
        out.append(f'<div class="layout single"><div>{"".join(left)}</div></div>')
    return "".join(out)


def json_ld(data):
    """A <script type="application/ld+json"> block; "</" is escaped so text can never close the script."""
    text = json.dumps(data, ensure_ascii=False, indent=1).replace("</", "<\\/")
    return f'<script type="application/ld+json">\n{text}\n</script>'


def project_ld(p, url, description):
    """Structured data that tells Google what the page is about: an app or a game."""
    kind = p.get("kind")
    if kind not in ("App", "Game"):
        return ""
    platform = str(p.get("platform") or "")
    mobile = re.search(r"iPhone|iPad|iOS|Android", platform)
    data = {
        "@context": "https://schema.org",
        "@type": "VideoGame" if kind == "Game" else ("MobileApplication" if mobile else "SoftwareApplication"),
        "name": p["title"],
        "description": description,
        "url": url,
        "author": {"@type": "Organization", "name": NAME, "url": SITE},
    }
    if p.get("cover"):
        data["image"] = absolute(p["cover"])
    if p.get("screenshots"):
        data["screenshot"] = [absolute(s) for s in p["screenshots"]]
    data["operatingSystem"] = p.get("requires") or platform
    if kind == "Game":
        data["applicationCategory"] = "GameApplication"
        data["gamePlatform"] = [x.strip() for x in re.split(r"[·,/]", platform) if x.strip()]
    else:
        data["applicationCategory"] = CATEGORIES.get(p.get("appCategory"), "UtilitiesApplication")
    store = safe_url(p.get("appStore"))
    if store:
        data["installUrl"] = data["downloadUrl"] = store
    if str(p.get("price") or "").lower().startswith("free"):
        data["offers"] = {"@type": "Offer", "price": "0", "priceCurrency": "USD"}
        if store:
            data["offers"]["url"] = store
    return json_ld(data)


def save(im, rel):
    im.save(ROOT / rel, "JPEG", quality=88, optimize=True, progressive=True)


def meta(title, desc, url, image):
    e = lambda s: html.escape(s, quote=True)
    return "\n".join([
        f'<meta name="description" content="{e(desc)}">',
        f'<link rel="canonical" href="{e(url)}">',
        '<meta property="og:type" content="website">',
        f'<meta property="og:site_name" content="{e(NAME)}">',
        f'<meta property="og:title" content="{e(title)}">',
        f'<meta property="og:description" content="{e(desc)}">',
        f'<meta property="og:url" content="{e(url)}">',
        f'<meta property="og:image" content="{e(image)}">',
        f'<meta property="og:image:width" content="{W}">',
        f'<meta property="og:image:height" content="{H}">',
        '<meta name="twitter:card" content="summary_large_image">',
    ])


def project_page(template, p):
    url = SITE + "projects/" + p["id"] + "/"
    # the browser tab and Google's headline; searchTitle, when set, carries the words people search for
    name = str(p.get("searchTitle") or "").strip() or p["title"]
    title = name if name == NAME else name + " · " + NAME
    description = str(p.get("searchDescription") or "").strip() or p.get("summary", "")
    extra = project_ld(p, url, description)
    app_id = re.search(r"/id(\d+)", str(p.get("appStore") or ""))
    if app_id:  # Safari on iPhone shows a small "Open in the App Store" banner
        extra += f'\n<meta name="apple-itunes-app" content="app-id={app_id[1]}">'
    page = template
    for old, new in [
        ("<!doctype html>\n", "<!doctype html>\n<!-- Made by tools/build-pages.py from project.html: edit that, then run the script -->\n"),
        # the page sits in projects/<id>/, so every link and file starts from the site root
        ('<meta charset="utf-8">\n', '<meta charset="utf-8">\n<base href="/">\n'),
        ("<title>Project · Redfern's Outpost</title>\n",
         f"<title>{html.escape(title, quote=False)}</title>\n"
         + meta(p["title"], description, url, SITE + "projects/" + p["id"] + "/share.jpg") + "\n"
         + (extra + "\n" if extra else "")),
        ('<div id="project"><div class="empty">Loading…</div></div>', f'<div id="project">{project_body(p)}</div>'),
        ("<script>renderProject();</script>", f"<script>renderProject({json.dumps(p['id'])});</script>"),
    ]:
        assert page.count(old) == 1, old
        page = page.replace(old, new)
    if p.get("kind") == "Game":  # site.js does the same once it runs
        page = page.replace('<a class="back" href="./#projects-section">← All projects</a>',
                            '<a class="back" href="./#games-section">← All games</a>')
        page = page.replace('<a href="./#games-section">Games</a><a href="./#projects-section" aria-current="page">Projects</a>',
                            '<a href="./#games-section" aria-current="page">Games</a><a href="./#projects-section">Projects</a>')
    return page


def paragraphs(text, indent):
    """Plain text with blank lines between paragraphs, as escaped <p> elements."""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", str(text or "")) if b.strip()]
    return "".join(f"{indent}<p>{'<br>'.join(html.escape(line.strip()) for line in b.splitlines())}</p>\n" for b in blocks)


def home_page(page, site, projects=()):
    """index.html with the banner line and the About section from site.json, and the project cards."""
    games = [card(p) for p in projects if p.get("kind") == "Game"]
    others = [card(p) for p in projects if p.get("kind") != "Game"]
    for key, cards in (("games", games), ("projects", others)):
        if cards:
            page = re.sub(rf"(<!-- cards:{key} -->).*?(<!-- /cards -->)", lambda m: m[1] + "".join(cards) + m[2], page, flags=re.S)
    tagline = str(site.get("tagline") or "").strip()
    if tagline:
        page = re.sub(r'(<p data-edit="tagline">).*?(</p>)', lambda m: m[1] + html.escape(tagline) + m[2], page, flags=re.S)

    section = nav = ""
    text = paragraphs(site.get("about"), "        ")
    if text:
        photo = local(site.get("aboutPhoto"))
        if site.get("aboutPhoto") and not photo:
            warn(f"The About picture {site['aboutPhoto']} isn't on the site, so it was left out")
        img = f'      <img src="/{html.escape(photo.relative_to(ROOT).as_posix(), quote=True)}" alt="">\n' if photo else ""
        heading = html.escape(str(site.get("aboutTitle") or "About").strip())
        section = (
            '  <section class="section" id="about-section">\n'
            f'    <div class="section-head"><h2>{heading}</h2></div>\n'
            f'    <div class="about{"" if photo else " text-only"}">\n{img}      <div>\n{text}      </div>\n    </div>\n'
            "  </section>\n")
        nav = f'<a href="#about-section">{heading}</a>'
    page = re.sub(r"(<!-- about-nav -->).*?(<!-- /about-nav -->)", lambda m: m[1] + nav + m[2], page)
    page = re.sub(r"(<!-- about:[^\n]*-->\n).*?(  <!-- /about -->)", lambda m: m[1] + section + m[2], page, flags=re.S)
    return page


def main():
    projects = load("projects.json")
    patches = load("patches.json")
    site = load("site.json", {})
    template = (ROOT / "project.html").read_text(encoding="utf-8").replace("\r\n", "\n")

    save(banner_image(NAME, "Games, apps and ROM patches"), "assets/img/share.jpg")
    save(banner_image("Patch a ROM", "IPS, BPS, UPS, xdelta and more, in your browser"), "assets/img/share-patcher.jpg")

    built, seen, shown = [], set(), []
    for p in projects:
        pid = str(p.get("id") or "")
        p.setdefault("title", pid or "Untitled")
        if not PAGE_ID.fullmatch(pid) or pid in seen:
            warn(f"{p['title']}: its page address ({pid or 'empty'}) is missing, not lowercase-and-dashes, "
                 "or used twice, so it has no page of its own")
            continue
        seen.add(pid)
        folder = ROOT / "projects" / pid
        folder.mkdir(parents=True, exist_ok=True)
        try:
            image = project_image(p)
        except Exception as err:  # a picture Pillow can't open shouldn't stop the whole site
            warn(f"{p['title']}: couldn't make its link preview picture ({err}), so it uses the banner")
            image = banner_image(p["title"], p.get("kind") or "")
        save(image, f"projects/{pid}/share.jpg")
        (folder / "index.html").write_text(project_page(template, p), encoding="utf-8", newline="\n")
        built.append(pid)
        shown.append(p)

    index = ROOT / "index.html"
    index.write_text(home_page(index.read_text(encoding="utf-8").replace("\r\n", "\n"), site, shown), encoding="utf-8", newline="\n")

    # every hand-made page in its own folder (the apps' support and privacy pages), but not the editor
    skip = {"admin", "projects", "patches", "assets", "tools", "rom-patcher-js", "parked", "incoming", "_test"}
    pages = [*ROOT.glob("*/index.html"), *ROOT.glob("*/*/index.html")]
    support = sorted(f.parent.relative_to(ROOT).as_posix() for f in pages
                     if f.relative_to(ROOT).parts[0] not in skip and not f.relative_to(ROOT).parts[0].startswith("."))
    urls = [SITE, SITE + "patches.html"] + [SITE + d + "/" for d in support]
    urls += [SITE + "projects/" + pid + "/" for pid in built]
    urls += [SITE + "patch.html?id=" + str(p["id"]) for p in patches if PAGE_ID.fullmatch(str(p.get("id") or ""))]
    (ROOT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{html.escape(u)}</loc></url>\n" for u in urls)
        + "</urlset>\n", encoding="utf-8", newline="\n")
    print(f"{len(built)} project pages, {len(urls)} sitemap entries")


if __name__ == "__main__":
    main()
