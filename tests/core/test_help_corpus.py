"""Help-corpus coverage gate (ADR-0012 "CI checks"): this test IS the check.

Mirrors tests/core/test_privacy.py. A module or metric added without a help
page, a cross-reference that points nowhere, an unknown BibTeX key, or front
matter that does not validate fails here - so adding a module stays a
two-step change (code + help) and the corpus cannot silently rot.

The seven checks of ADR-0012, and where each one lives:

    1. every module in the catalogue has help/modules/<name>.md
    2. every metric in the catalogue has help/metrics/<name>.md
    3. every cross-reference resolves to an installed slug
    4. every cited BibTeX key exists in docs/references.bib
    5. front matter validates against the ADR-0012 schema
    6. no raw HTML
    7. no external http(s) image links

The metric catalogue is `ModuleSpec.produces_metrics` over
`default_registry()`, not `core/privacy_metadata.py` - that registry holds no
metric names (ADR-0012 rev. 3 corrects the check's wording). The bibliography
is `docs/references.bib`, also per rev. 3: the only render target that
resolves `[@key]` is the pandoc pipeline, which runs over the repository.

Scope is modules/ metrics/ concepts/, plus the guide pages of ADR-0012
rev. 6 (#92) in every locale, `help/guide/<locale>/<slug>.md` - the help
viewer's cover page. The other guide page, `guide:privacy`, is generated at
view time and has no file: it counts as a link target here, and its content
is gated by tests/core/test_privacy.py. `help/privacy/<locale>/` holds the
legal stubs of ADR-0009 Sec. 6-7 - fragments appended to a generated
statement, with no front matter and one HTML status comment. They are not
help pages and the viewer's topic tree excludes them.

This module reads the `.md` files directly rather than through
`ui/tk/help_view.py`: a content gate over `core` must not depend on the Tk
adapter. It parses their front matter with `core.help_corpus`, the one
parser every consumer shares (ADR-0012 rev. 5, #78), in strict mode: a line
the flat schema cannot express fails here instead of being skipped.

Assertions stay ASCII (ADR-0018) although the corpus is German (SDD Sec. 9.6):
they key on slugs, URIs and BibTeX keys, never on rendered prose.
"""

import pathlib
import re
from importlib import resources

import pytest

from tta.core.help_corpus import (
    COVER_URI,
    GENERATED_GUIDE_SLUGS,
    GUIDE_DIRECTORY,
    GUIDE_KIND,
    PRIVACY_URI,
    split_front_matter,
)
from tta.core.i18n import SUPPORTED_LOCALES
from tta.core.modules.registry import default_registry
from tta.core.third_party_licenses import LICENSES_URI

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
BIBLIOGRAPHY = REPO_ROOT / "docs" / "references.bib"
README = REPO_ROOT / "README.md"
HELP_ROOT = pathlib.Path(str(resources.files("tta.core") / "help"))

#: Corpus sections and the `kind` each one's pages must declare (ADR-0012).
SECTIONS = {"modules": "module", "metrics": "metric", "concepts": "concept"}
#: Every page directory and its kind: the sections plus the per-locale guide
#: pages (ADR-0012 rev. 6, #92).
KINDS = {**SECTIONS, GUIDE_DIRECTORY: GUIDE_KIND}
#: Guide pages with no file, generated at view time - valid link targets.
GENERATED_URIS = {f"{GUIDE_KIND}:{slug}" for slug in GENERATED_GUIDE_SLUGS}

#: Front-matter schema. Required per kind, then the fields shared by all.
REQUIRED = {
    "module": ("consumes", "produces_artefacts", "produces_metrics", "applicability"),
    "metric": ("produced_by", "applicability"),
    "concept": (),
    "guide": (),
}
ALWAYS_REQUIRED = ("slug", "title", "kind")
OPTIONAL = ("references", "see_also")
#: Fields that must be a list when present; every other field is a scalar.
LIST_FIELDS = frozenset(
    {"consumes", "produces_artefacts", "produces_metrics", "references", "see_also"}
)

CROSS_REF = re.compile(r"\A(module|metric|concept|guide):([A-Za-z0-9_.-]+)\Z")
#: A markdown link whose target is a cross-reference URI.
BODY_REF = re.compile(r"\]\(((?:module|metric|concept|guide):[^)\s]*)\)")
#: A markdown link to an in-app target (ADR-0012 rev. 4) - not a page.
APP_REF = re.compile(r"\]\((app:[^)\s]*)\)")
#: A pandoc citation, `[@key]` or `[@a; @b]`.
CITATION = re.compile(r"\[@([A-Za-z0-9_:.#$%&+?<>~/-]+)(?:[^\]]*)\]")
#: An HTML tag or comment. Deliberately tag-shaped so prose may write
#: "< 0.10" or "a -> b" without tripping the gate.
RAW_HTML = re.compile(r"<!--|</?[A-Za-z][A-Za-z0-9]*(?:\s[^>]*)?/?>")
#: A markdown image whose target is an external URL.
EXTERNAL_IMAGE = re.compile(r"!\[[^\]]*\]\(\s*(https?://[^)\s]*)")


class Page:
    """One help page: its section, its front matter and its body. A guide
    page also has a locale (its directory under guide/)."""

    def __init__(self, section, path, locale=""):
        self.section = section
        self.locale = locale
        self.path = path
        self.slug = path.name[:-3]
        self.kind = KINDS[section]
        self.uri = f"{self.kind}:{self.slug}"
        self.fields, self.body = split_front_matter(
            path.read_text(encoding="utf-8"), strict=True
        )

    def __repr__(self):
        where = f"{self.section}/{self.locale}" if self.locale else self.section
        return f"help/{where}/{self.path.name}"


def load_pages():
    pages = [
        Page(section, path)
        for section in SECTIONS
        for path in sorted((HELP_ROOT / section).iterdir())
        if path.name.endswith(".md")
    ]
    guide = HELP_ROOT / GUIDE_DIRECTORY
    for locale in sorted(entry.name for entry in guide.iterdir() if entry.is_dir()):
        pages += [
            Page(GUIDE_DIRECTORY, path, locale)
            for path in sorted((guide / locale).iterdir())
            if path.name.endswith(".md")
        ]
    return pages


@pytest.fixture(scope="module")
def pages():
    return load_pages()


@pytest.fixture(scope="module")
def slugs(pages):
    """Every resolvable page URI: the files, plus the generated guide pages."""
    return {page.uri for page in pages} | GENERATED_URIS


@pytest.fixture(scope="module")
def catalogue():
    """(module names, metric names) from the registry - the coverage target."""
    registry = default_registry()
    modules = registry.in_topological_order()
    metrics = {m for module in modules for m in module.spec.produces_metrics}
    return {module.spec.name for module in modules}, metrics


# -- check 1: module coverage --------------------------------------------------


def test_every_module_has_a_help_page(pages, catalogue):
    modules, _metrics = catalogue
    authored = {page.slug for page in pages if page.section == "modules"}
    assert modules - authored == set(), "registered modules without a help page"
    assert authored - modules == set(), "help pages for modules that are not registered"


# -- check 2: metric coverage -------------------------------------------------


def test_every_metric_has_a_help_page(pages, catalogue):
    _modules, metrics = catalogue
    authored = {page.slug for page in pages if page.section == "metrics"}
    assert metrics - authored == set(), "catalogue metrics without a help page"
    assert authored - metrics == set(), "help pages for metrics no module produces"


def test_the_catalogue_is_the_size_the_documentation_claims(catalogue):
    """SDD Sec. 7 / ADR-0011 rev. 7 and ADR-0012 rev. 3 all say 13 and 34."""
    modules, metrics = catalogue
    assert (len(modules), len(metrics)) == (13, 34)


# -- check 3: cross-references ------------------------------------------------


def test_every_cross_reference_resolves(pages, slugs):
    dangling = [
        (repr(page), target)
        for page in pages
        for target in BODY_REF.findall(page.body) + list(page.fields.get("see_also", ()))
        if target not in slugs
    ]
    assert dangling == [], "cross-references with no installed target"


def test_every_in_app_link_is_one_the_viewer_handles(pages):
    """ADR-0012 rev. 4: `app:third_party_licenses` is the only in-app
    target. It is no slug, so check 3 cannot see a typo in it - this does."""
    unknown = [
        (repr(page), target)
        for page in pages
        for target in APP_REF.findall(page.body)
        if target != LICENSES_URI
    ]
    assert unknown == []


def test_the_licence_page_links_to_the_licence_window(pages):
    """#36: the plain-language page and the legal text are one click apart."""
    page = next(page for page in pages if page.uri == "concept:bundled_components")
    assert LICENSES_URI in APP_REF.findall(page.body)


def test_every_see_also_entry_is_a_well_formed_uri(pages):
    malformed = [
        (repr(page), uri)
        for page in pages
        for uri in page.fields.get("see_also", ())
        if not CROSS_REF.match(uri)
    ]
    assert malformed == [], "see_also entries that are not <kind>:<slug>"


def test_no_page_cross_references_itself(pages):
    self_referential = [
        repr(page)
        for page in pages
        if page.uri in BODY_REF.findall(page.body)
        or page.uri in page.fields.get("see_also", ())
    ]
    assert self_referential == []


def test_every_concept_page_is_linked_from_somewhere(pages, slugs):
    """ADR-0012 has no orphan concepts: a concept nobody links to is
    unreachable except by browsing the tree, so it is not carrying a caveat
    for any metric."""
    incoming = {
        target
        for page in pages
        for target in BODY_REF.findall(page.body) + list(page.fields.get("see_also", ()))
    }
    orphans = [
        page.uri
        for page in pages
        if page.section == "concepts" and page.uri not in incoming
    ]
    assert orphans == []


# -- check 4: bibliography ----------------------------------------------------


@pytest.fixture(scope="module")
def bibtex_keys():
    assert BIBLIOGRAPHY.is_file(), f"no bibliography at {BIBLIOGRAPHY}"
    source = BIBLIOGRAPHY.read_text(encoding="utf-8")
    return set(re.findall(r"^@\w+\s*\{\s*([^,\s]+)\s*,", source, re.M))


def test_every_cited_key_exists_in_the_bibliography(pages, bibtex_keys):
    unknown = [
        (repr(page), key)
        for page in pages
        for key in CITATION.findall(page.body) + list(page.fields.get("references", ()))
        if key not in bibtex_keys
    ]
    assert unknown == [], "citations with no entry in docs/references.bib"


def test_front_matter_references_are_actually_cited_in_the_body(pages):
    """The `references` list is the page's bibliography, so it must not
    promise a source the prose never uses."""
    uncited = [
        (repr(page), key)
        for page in pages
        for key in page.fields.get("references", ())
        if key not in CITATION.findall(page.body)
    ]
    assert uncited == []


# -- check 5: front-matter schema ---------------------------------------------


def test_every_page_has_front_matter(pages):
    assert [repr(page) for page in pages if not page.fields] == []


def test_front_matter_declares_its_own_slug_and_kind(pages):
    assert [
        (repr(page), page.fields.get("slug"), page.fields.get("kind"))
        for page in pages
        if page.fields.get("slug") != page.slug
        or page.fields.get("kind") != page.kind
    ] == []


def test_front_matter_has_every_required_field(pages):
    missing = [
        (repr(page), field)
        for page in pages
        for field in ALWAYS_REQUIRED + REQUIRED[page.kind]
        if not page.fields.get(field) and page.fields.get(field) != []
    ]
    assert missing == []


def test_front_matter_has_no_field_outside_the_schema(pages):
    allowed = {
        kind: set(ALWAYS_REQUIRED) | set(REQUIRED[kind]) | set(OPTIONAL)
        for kind in REQUIRED
    }
    extra = [
        (repr(page), field)
        for page in pages
        for field in page.fields
        if field not in allowed[page.kind]
    ]
    assert extra == [], "front-matter fields ADR-0012's schema does not define"


def test_list_valued_fields_are_lists_and_scalars_are_not(pages):
    wrong = [
        (repr(page), field)
        for page in pages
        for field, value in page.fields.items()
        if isinstance(value, list) is not (field in LIST_FIELDS)
    ]
    assert wrong == [], "list field written as a scalar, or a scalar as a list"


def test_metric_pages_name_a_registered_producing_module(pages, catalogue):
    modules, _metrics = catalogue
    wrong = [
        (repr(page), page.fields["produced_by"])
        for page in pages
        if page.section == "metrics" and page.fields["produced_by"] not in modules
    ]
    assert wrong == []


def test_metric_pages_name_the_module_that_actually_produces_them():
    """`produced_by` is checked against the ModuleSpec, not just spelled
    right: a metric moved between modules must move its page's front matter."""
    producer = {
        metric: module.spec.name
        for module in default_registry().in_topological_order()
        for metric in module.spec.produces_metrics
    }
    wrong = [
        (repr(page), page.fields["produced_by"], producer[page.slug])
        for page in load_pages()
        if page.section == "metrics" and page.fields["produced_by"] != producer[page.slug]
    ]
    assert wrong == []


def test_module_pages_mirror_their_module_spec():
    """ADR-0012: a module page's consumes/produces fields mirror the spec."""
    registry = default_registry()
    mismatched = []
    for page in load_pages():
        if page.section != "modules":
            continue
        spec = registry.get(page.slug).spec
        for field, declared in (
            ("consumes", spec.consumes),
            ("produces_artefacts", spec.produces_artefacts),
            ("produces_metrics", spec.produces_metrics),
        ):
            if page.fields[field] != list(declared):
                mismatched.append((repr(page), field, page.fields[field], list(declared)))
    assert mismatched == []


def test_every_page_has_a_body(pages):
    assert [repr(page) for page in pages if not page.body.strip()] == []


# -- checks 6 and 7: no raw HTML, no external images --------------------------


def test_no_raw_html_in_any_help_page(pages):
    found = [
        (repr(page), match.group(0))
        for page in pages
        for match in RAW_HTML.finditer(page.body)
    ]
    assert found == [], "raw HTML: not every render target can carry it"


def test_no_external_image_links(pages):
    """QA-PRIV: the application makes no network calls, so a remote image
    would render as a broken reference in every target."""
    found = [
        (repr(page), match.group(1))
        for page in pages
        for match in EXTERNAL_IMAGE.finditer(page.body)
    ]
    assert found == []


# -- corpus-wide invariants ---------------------------------------------------


def test_the_privacy_stubs_are_not_part_of_the_corpus(pages):
    """They are ADR-0009 legal fragments, not help pages, and the viewer's
    topic tree excludes them - so the gates above must not see them either."""
    assert (HELP_ROOT / "privacy").is_dir()
    assert "privacy" not in SECTIONS
    assert not [page for page in pages if "stub" in page.slug]


def test_the_corpus_is_the_size_the_sdd_claims(pages):
    """SDD Sec. 9.4: 13 module + 34 metric + 5 concept pages."""
    counts = {section: 0 for section in SECTIONS}
    for page in pages:
        if page.section in counts:
            counts[page.section] += 1
    assert counts == {"modules": 13, "metrics": 34, "concepts": 5}


# --- guide pages (ADR-0012 rev. 6, #92) ----------------------------------------


def test_every_locale_has_a_cover_page_and_nothing_else_is_a_guide_page(pages):
    """The cover page follows the UI language, so each supported locale
    carries one; the generated privacy page must not exist as a file."""
    guide = sorted((page.locale, page.uri) for page in pages if page.kind == GUIDE_KIND)
    assert guide == sorted((locale, COVER_URI) for locale in SUPPORTED_LOCALES)


def test_no_generated_guide_page_is_shadowed_by_a_file():
    stray = [
        path
        for slug in GENERATED_GUIDE_SLUGS
        for path in (HELP_ROOT / GUIDE_DIRECTORY).glob(f"*/{slug}.md")
    ]
    assert stray == []


def test_the_cover_page_links_to_the_privacy_page_in_every_locale(pages):
    """#92: the cover page's privacy paragraph ends in a direct link, not a
    menu path."""
    covers = [page for page in pages if page.uri == COVER_URI]
    assert covers
    assert [repr(page) for page in covers if PRIVACY_URI not in BODY_REF.findall(page.body)] == []


def _readme_section(source, heading):
    """The body of one ``## heading`` section of the README."""
    match = re.search(rf"^## {heading}\n(.*?)(?=^## |\Z)", source, re.M | re.S)
    assert match, f"README.md has no '## {heading}' section"
    return match.group(1)


#: The README facts a reworded cover page must keep: acronyms (KIWIT, BMFTR)
#: and years (funding start, availability of generative AI).
_FACT = re.compile(r"\b(?:[A-Z]{3,}|(?:19|20)\d\d)\b")


def test_the_cover_page_keeps_the_readme_facts(pages):
    """README and cover page share their substance (#92): the cover page is
    the README's opening, "Hintergrund" and "Datenschutz" retold for a
    professor. Prose may differ, facts may not - every acronym and year of
    those README sections must appear on every locale's cover page. A
    changed funding body or date then fails here until both say the same."""
    source = README.read_text(encoding="utf-8").replace("\r\n", "\n")
    facts = set()
    for heading in ("Hintergrund", "Datenschutz"):
        facts |= set(_FACT.findall(_readme_section(source, heading)))
    assert {"KIWIT", "BMFTR"} <= facts, "the README lost its background facts"
    missing = [
        (repr(page), fact)
        for page in pages
        if page.uri == COVER_URI
        for fact in sorted(facts)
        if fact not in page.body
    ]
    assert missing == []


# --- the label/title gate (#79) ---------------------------------------------
#
# A column's friendly label lives in the gettext catalogue (COLUMN_LABELS plus
# its translation); its German form is repeated as the help page's front-matter
# `title:`. ADR-0012 wanted the page to be the single source. It cannot be: the
# corpus is German-only, so a page carries one title, while the catalogue holds
# a string per locale (ADR-0020 Sec. 8). The catalogue is therefore canonical
# and this gate keeps the second copy honest - "worded to match" had already
# failed once, file_size_bytes diverging the day both copies first existed.


@pytest.fixture(scope="module")
def german_labels():
    """`{column: German label}` straight out of the catalogue."""
    from tta.core.i18n import _ as translate
    from tta.core.i18n import install
    from tta.ui.tk.columns import COLUMN_LABELS

    install("de")
    return {key: translate(msgid) for key, msgid in COLUMN_LABELS.items()}


def test_every_page_title_matches_the_german_label(pages, german_labels):
    """The page `title:` must equal the catalogue's German label."""
    titles = {page.slug: page.fields["title"] for page in pages}
    shared = sorted(set(german_labels) & set(titles))
    assert shared, "no column has both a label and a page - the gate is vacuous"
    mismatched = {
        slug: {"catalogue": german_labels[slug], "page": titles[slug]}
        for slug in shared
        if german_labels[slug] != titles[slug]
    }
    assert not mismatched, (
        "page title and German label disagree; the catalogue is canonical "
        f"(ADR-0020 Sec. 8): {mismatched}"
    )


def test_the_label_gate_covers_every_metric_page(pages, german_labels):
    """A metric page with no label would be silently skipped by the gate."""
    metric_slugs = {page.slug for page in pages if page.section == "metrics"}
    uncovered = sorted(metric_slugs - set(german_labels))
    assert not uncovered, (
        f"metric pages with no COLUMN_LABELS entry, so nothing checks their title: {uncovered}"
    )
