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

Scope is modules/ metrics/ concepts/. `help/privacy/` holds the two reviewed
legal stubs of ADR-0009 Sec. 6-7 - fragments appended to a generated
statement, with no front matter and one HTML review comment. They are not
help pages and the viewer's topic tree excludes them.

This module reads the `.md` files directly rather than through
`ui/tk/help_view.py`: a content gate over `core` must not depend on the Tk
adapter, and it needs the list-valued front-matter fields the viewer's flat
parser deliberately skips.

Assertions stay ASCII (ADR-0018) although the corpus is German (SDD Sec. 9.6):
they key on slugs, URIs and BibTeX keys, never on rendered prose.
"""

import pathlib
import re
from importlib import resources

import pytest

from tta.core.modules.registry import default_registry

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
BIBLIOGRAPHY = REPO_ROOT / "docs" / "references.bib"
HELP_ROOT = pathlib.Path(str(resources.files("tta.core") / "help"))

#: Corpus sections and the `kind` each one's pages must declare (ADR-0012).
SECTIONS = {"modules": "module", "metrics": "metric", "concepts": "concept"}

#: Front-matter schema. Required per kind, then the fields shared by all.
REQUIRED = {
    "module": ("consumes", "produces_artefacts", "produces_metrics", "applicability"),
    "metric": ("produced_by", "applicability"),
    "concept": (),
}
ALWAYS_REQUIRED = ("slug", "title", "kind")
OPTIONAL = ("references", "see_also")
#: Fields that must be a list when present; every other field is a scalar.
LIST_FIELDS = frozenset(
    {"consumes", "produces_artefacts", "produces_metrics", "references", "see_also"}
)

CROSS_REF = re.compile(r"\A(module|metric|concept):([A-Za-z0-9_.-]+)\Z")
#: A markdown link whose target is a cross-reference URI.
BODY_REF = re.compile(r"\]\(((?:module|metric|concept):[^)\s]*)\)")
#: A pandoc citation, `[@key]` or `[@a; @b]`.
CITATION = re.compile(r"\[@([A-Za-z0-9_:.#$%&+?<>~/-]+)(?:[^\]]*)\]")
#: An HTML tag or comment. Deliberately tag-shaped so prose may write
#: "< 0.10" or "a -> b" without tripping the gate.
RAW_HTML = re.compile(r"<!--|</?[A-Za-z][A-Za-z0-9]*(?:\s[^>]*)?/?>")
#: A markdown image whose target is an external URL.
EXTERNAL_IMAGE = re.compile(r"!\[[^\]]*\]\(\s*(https?://[^)\s]*)")
FRONT_MATTER = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)


def parse_front_matter(text):
    """Flat front-matter fields plus the body.

    Scalars stay strings; a value in brackets becomes a list of stripped
    items. Enough for the ADR-0012 schema, which is flat by design, and it
    keeps the gate free of a YAML dependency (there is none in the project).
    """
    match = FRONT_MATTER.match(text)
    if not match:
        return None, text
    fields = {}
    for line in match.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, value = line.partition(":")
        assert separator and not key[:1].isspace(), (
            f"front-matter line is neither a scalar nor a list item: {line!r}"
        )
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            items = [item.strip().strip("\"'") for item in value[1:-1].split(",")]
            fields[key.strip()] = [item for item in items if item]
        else:
            fields[key.strip()] = value.strip("\"'")
    return fields, text[match.end() :]


class Page:
    """One help page: its section, its front matter and its body."""

    def __init__(self, section, path):
        self.section = section
        self.path = path
        self.slug = path.name[:-3]
        self.uri = f"{SECTIONS[section]}:{self.slug}"
        self.fields, self.body = parse_front_matter(path.read_text(encoding="utf-8"))

    def __repr__(self):
        return f"help/{self.section}/{self.path.name}"


def load_pages():
    return [
        Page(section, path)
        for section in SECTIONS
        for path in sorted((HELP_ROOT / section).iterdir())
        if path.name.endswith(".md")
    ]


@pytest.fixture(scope="module")
def pages():
    return load_pages()


@pytest.fixture(scope="module")
def slugs(pages):
    return {page.uri for page in pages}


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
    """SDD Sec. 7 / ADR-0011 rev. 4 and ADR-0012 rev. 3 all say 13 and 31."""
    modules, metrics = catalogue
    assert (len(modules), len(metrics)) == (13, 31)


# -- check 3: cross-references ------------------------------------------------


def test_every_cross_reference_resolves(pages, slugs):
    dangling = [
        (repr(page), target)
        for page in pages
        for target in BODY_REF.findall(page.body) + list(page.fields.get("see_also", ()))
        if target not in slugs
    ]
    assert dangling == [], "cross-references with no installed target"


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
    assert [repr(page) for page in pages if page.fields is None] == []


def test_front_matter_declares_its_own_slug_and_kind(pages):
    assert [
        (repr(page), page.fields.get("slug"), page.fields.get("kind"))
        for page in pages
        if page.fields.get("slug") != page.slug
        or page.fields.get("kind") != SECTIONS[page.section]
    ] == []


def test_front_matter_has_every_required_field(pages):
    missing = [
        (repr(page), field)
        for page in pages
        for field in ALWAYS_REQUIRED + REQUIRED[SECTIONS[page.section]]
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
        if field not in allowed[SECTIONS[page.section]]
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
    """SDD Sec. 9.4: 13 module + 31 metric + 4 concept pages."""
    counts = {section: 0 for section in SECTIONS}
    for page in pages:
        counts[page.section] += 1
    assert counts == {"modules": 13, "metrics": 31, "concepts": 4}


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
