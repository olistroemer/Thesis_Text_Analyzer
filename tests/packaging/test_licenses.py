"""THIRD_PARTY_LICENSES.txt: the licence-compliance build gate (#4).

A --onefile binary redistributes every library frozen into it. The MIT /
BSD / Apache-2.0 / PSF licences in this dependency set all require their
notice to accompany a binary, and PyMuPDF's AGPL-3.0 section 4 requires its
full text. These tests pin the generator's output and the gate that refuses
to ship a binary whose notices are incomplete.

The asymmetry that shapes all of it: over-reporting a notice is harmless,
omitting one is the violation.
"""

import ast
import os
import re
import subprocess
import sys

import pytest

from tests.packaging.conftest import AGPL_PATH, GENERATOR_PATH, REPO_ROOT, SPEC_PATH

CEILING = 150 * 1024 * 1024


def pkg(name, version="1.0", license_name="MIT", text="THE MIT LICENSE...", **extra):
    package = {
        "Name": name,
        "Version": version,
        "License": license_name,
        "LicenseText": text,
        "URL": "https://example.invalid/%s" % name,
        "Author": "Somebody",
    }
    package.update(extra)
    return package


def render(generator, packages, **overrides):
    kwargs = dict(
        app_version="0.1.0",
        source_url="https://github.com/olistroemer/Thesis_Text_Analyzer",
        source_ref="v9.9.9",
        agpl_text="GNU AFFERO GENERAL PUBLIC LICENSE\nVersion 3\n...body...",
        generated_at="2026-08-26 00:00:00 UTC",
    )
    kwargs.update(overrides)
    return generator.render(packages, **kwargs)


# ---------------------------------------------------- the committed AGPL text


def test_the_agpl_text_is_committed_and_is_the_real_thing():
    """PyMuPDF's own dist-info ships a 64-char COPYING, not the licence.

    So the text cannot be harvested at build time; it has to be in the repo,
    which also keeps the build offline (QA-REPRO).
    """
    assert AGPL_PATH.is_file(), "packaging/licenses/AGPL-3.0.txt is missing"
    text = AGPL_PATH.read_text(encoding="utf-8")
    assert "GNU AFFERO GENERAL PUBLIC LICENSE" in text
    assert "Version 3, 19 November 2007" in text
    # Section 13 is the whole difference between AGPL-3.0 and GPL-3.0.
    assert "13. Remote Network Interaction" in text
    assert "END OF TERMS AND CONDITIONS" in text
    assert "How to Apply These Terms" in text
    # A truncated copy would satisfy the greps above but not the length.
    assert len(text) > 30000, "AGPL text looks truncated (%d chars)" % len(text)


def test_the_agpl_text_is_not_the_gpl_text():
    """A copy-paste of the project's own LICENSE would be wrong here."""
    text = AGPL_PATH.read_text(encoding="utf-8")
    assert "GNU GENERAL PUBLIC LICENSE\n" not in text.split("TERMS AND CONDITIONS")[0]
    gpl = (REPO_ROOT / "LICENSE").read_text(encoding="utf-8")
    assert text != gpl


# ------------------------------------------------------- the rendered manifest


def test_manifest_names_every_component(generator):
    packages = [pkg("click"), pkg("nltk"), pkg("pypdf")]
    out = render(generator, packages)
    for name in ("click", "nltk", "pypdf"):
        assert name in out


def test_manifest_carries_the_corresponding_source_pointer(generator):
    """GPL-3.0-or-later obliges us to convey the source (ADR-0017 s.3)."""
    out = render(generator, [pkg("click")])
    assert "CORRESPONDING SOURCE" in out
    assert "https://github.com/olistroemer/Thesis_Text_Analyzer" in out
    assert "v9.9.9" in out
    assert "GPL-3.0-or-later" in out


def test_manifest_carries_the_full_agpl_text_and_a_pymupdf_notice(generator):
    out = render(generator, [pkg("PyMuPDF", license_name="AGPL/commercial")])
    assert "GNU AFFERO GENERAL PUBLIC LICENSE" in out
    assert "APPENDIX A" in out
    assert "AGPL-3.0 OPTION" in out
    assert "https://github.com/pymupdf/pymupdf" in out


def test_manifest_reproduces_per_package_licence_texts(generator):
    out = render(generator, [pkg("click", text="BSD 3-CLAUSE, VERBATIM BODY")])
    assert "BSD 3-CLAUSE, VERBATIM BODY" in out


def test_manifest_says_so_when_a_licence_text_is_absent(generator):
    """Silence would read as "no licence"; say where to get it instead."""
    out = render(generator, [pkg("mystery", text="")])
    assert "No licence text" in out


def test_manifest_is_deterministic_for_the_same_inputs(generator):
    packages = [pkg("b"), pkg("a")]
    assert render(generator, packages) == render(generator, packages)


def test_manifest_marks_components_outside_the_declared_closure(generator):
    """A manifest built in a dirty env must not silently claim scipy ships."""
    out = render(
        generator,
        [pkg("click"), pkg("scipy")],
        closure={"click"},
    )
    assert "[undeclared]" in out
    scipy_row = [ln for ln in out.splitlines() if ln.startswith("scipy ")]
    click_row = [ln for ln in out.splitlines() if ln.startswith("click ")]
    assert scipy_row and "[undeclared]" in scipy_row[0]
    assert click_row and "[undeclared]" not in click_row[0]


def test_no_undeclared_note_when_everything_is_declared(generator):
    out = render(generator, [pkg("click")], closure={"click"})
    assert "[undeclared]" not in out


def test_component_count_in_the_header_matches_the_inventory(generator):
    out = render(generator, [pkg("a"), pkg("b"), pkg("c")])
    assert "BUNDLED COMPONENTS (3)" in out


# ---------------------------------------------------------- the deny list


def test_build_only_tooling_is_not_reported(generator):
    kept = generator.redistributed(
        [pkg("click"), pkg("pip-licenses"), pkg("prettytable"), pkg("pytest")]
    )
    assert [p["Name"] for p in kept] == ["click"]


def test_this_program_is_not_listed_as_a_third_party(generator):
    kept = generator.redistributed([pkg("tta"), pkg("click")])
    assert [p["Name"] for p in kept] == ["click"]


def test_packages_that_really_are_bundled_are_kept(generator):
    """Regression: these were denylisted, but a real build's TOC shows
    setuptools, wheel, packaging and pyinstaller contributing files to the
    binary. Denylisting them under-reports, which is the violating direction.
    """
    names = ["setuptools", "wheel", "packaging", "pyinstaller",
             "pyinstaller-hooks-contrib"]
    kept = generator.redistributed([pkg(n) for n in names])
    assert sorted(p["Name"] for p in kept) == sorted(names)


def test_denylist_matching_is_normalised(generator):
    kept = generator.redistributed([pkg("pip_licenses"), pkg("PrettyTable")])
    assert kept == []


def test_inventory_is_sorted_case_insensitively(generator):
    kept = generator.redistributed([pkg("Zope"), pkg("apple"), pkg("Banana")])
    assert [p["Name"] for p in kept] == ["apple", "Banana", "Zope"]


# ------------------------------------------------------ requirement parsing


def test_parse_requirement_extracts_names_and_extra_markers(generator):
    cases = {
        "click>=8.1": ("click", []),
        "nltk >= 3.9": ("nltk", []),
        "tta[pymupdf]": ("tta", []),
        'pymupdf>=1.24; extra == "pymupdf"': ("pymupdf", ["pymupdf"]),
        "numpy>=1.23; python_version < '3.12'": ("numpy", []),
        'pytest>=8; extra == "dev"': ("pytest", ["dev"]),
    }
    for spec, expected in cases.items():
        assert generator.parse_requirement(spec) == expected, spec


def test_declared_closure_covers_the_declared_dependencies(generator):
    """Reads installed metadata, i.e. pyproject.toml's dependency table."""
    closure = generator.declared_closure()
    for name in ("click", "nltk", "textstat", "pypdf", "rich", "tksheet",
                 "matplotlib", "langdetect"):
        assert name in closure, name
    assert "tta" not in closure


def test_declared_closure_honours_the_pymupdf_extra(generator):
    assert "pymupdf" in generator.declared_closure(extras=("pymupdf",))
    assert "pymupdf" not in generator.declared_closure(extras=())


def test_declared_closure_is_transitive(generator):
    """numpy is nobody's direct dependency here - it arrives via matplotlib."""
    assert "numpy" in generator.declared_closure()


# ------------------------------------------------- the generator's hard stops


def _run_generator(args, env_extra=None):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, str(GENERATOR_PATH)] + args,
        capture_output=True, text=True, cwd=str(REPO_ROOT), env=env,
    )


def test_generator_refuses_without_the_agpl_text(tmp_path):
    """Better no build than a binary shipping PyMuPDF with no AGPL text."""
    proc = _run_generator(
        ["--output", str(tmp_path / "out.txt"),
         "--agpl-text", str(tmp_path / "nope.txt")]
    )
    assert proc.returncode != 0
    assert "missing AGPL-3.0 text" in proc.stdout + proc.stderr
    assert not (tmp_path / "out.txt").exists()


def test_generator_rejects_an_agpl_file_that_is_not_the_licence(tmp_path):
    decoy = tmp_path / "decoy.txt"
    decoy.write_text("this is not a licence", encoding="utf-8")
    proc = _run_generator(
        ["--output", str(tmp_path / "out.txt"), "--agpl-text", str(decoy)]
    )
    assert proc.returncode != 0
    assert "does not look like the AGPL-3.0 text" in proc.stdout + proc.stderr


def test_generator_asks_pip_licenses_for_system_packages(generator):
    """Regression: setuptools/wheel are hidden without --with-system, and
    they are genuinely bundled, so the manifest lost their notices."""
    source = GENERATOR_PATH.read_text(encoding="utf-8")
    assert "--with-system" in source


def test_generator_produces_a_real_manifest_end_to_end(tmp_path):
    """Runs pip-licenses for real; proves the whole path, not just render().

    pip-licenses comes from the ``build`` extra, which the ``dev`` extra
    pulls in. Skipped rather than failed in a minimal environment.
    """
    pytest.importorskip(
        "piplicenses", reason="pip-licenses not installed (pip install -e '.[build]')"
    )
    out = tmp_path / "THIRD_PARTY_LICENSES.txt"
    proc = _run_generator(["--output", str(out), "--source-ref", "v0.0.0-test"])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    text = out.read_text(encoding="utf-8")
    assert "GNU AFFERO GENERAL PUBLIC LICENSE" in text
    assert "CORRESPONDING SOURCE" in text
    assert "v0.0.0-test" in text
    # The declared dependencies must all be accounted for.
    for name in ("click", "nltk", "textstat", "pypdf", "rich", "tksheet"):
        assert re.search(re.escape(name), text, re.I), name


# ----------------------------------------------- the coverage gate (checker)


def _toc_entries(names, site="/opt/env/lib/python3.12/site-packages"):
    return [(n, "%s/%s/__init__.py" % (site, n), "PYMODULE") for n in names]


def test_gate_flags_a_bundled_package_with_no_notice(check_build):
    missing, _unattributed = check_build.manifest_gaps(
        _toc_entries(["click", "yaml"]),
        "inventory: click 8.3.3 MIT",
        mapping={"click": ["click"], "yaml": ["PyYAML"]},
    )
    assert missing == ["pyyaml"]


def test_gate_passes_when_every_bundled_package_has_a_notice(check_build):
    missing, _ = check_build.manifest_gaps(
        _toc_entries(["click", "yaml"]),
        "click 8.3.3 MIT\nPyYAML 6.0.3 MIT",
        mapping={"click": ["click"], "yaml": ["PyYAML"]},
    )
    assert missing == []


def test_gate_maps_import_names_to_distribution_names(check_build):
    """fitz -> PyMuPDF, dateutil -> python-dateutil, PIL -> pillow."""
    missing, _ = check_build.manifest_gaps(
        _toc_entries(["fitz", "dateutil", "PIL"]),
        "PyMuPDF 1.27\npython-dateutil 2.9\npillow 12.2",
        mapping={
            "fitz": ["PyMuPDF"],
            "dateutil": ["python-dateutil"],
            "PIL": ["pillow"],
        },
    )
    assert missing == []


def test_gate_ignores_files_outside_site_packages(check_build):
    """Stdlib and the app's own modules need no third-party notice."""
    missing, unattributed = check_build.manifest_gaps(
        [
            ("subprocess", "/usr/lib/python3.12/subprocess.py", "PYMODULE"),
            ("tta.core", "/repo/tta/core/__init__.py", "PYMODULE"),
        ],
        "",
        mapping={},
    )
    assert missing == [] and unattributed == []


def test_gate_reports_but_does_not_fail_on_unattributable_names(check_build):
    """PyInstaller's own bootstrap modules map to no distribution."""
    missing, unattributed = check_build.manifest_gaps(
        _toc_entries(["_distutils_hack", "click"]),
        "click 8.3.3",
        mapping={"click": ["click"]},
    )
    assert missing == []
    assert unattributed == ["_distutils_hack"]


def test_gate_skips_dist_info_and_libs_directories(check_build):
    site = "/opt/env/lib/python3.12/site-packages"
    entries = [
        ("x", site + "/numpy-2.4.4.dist-info/METADATA", "DATA"),
        ("y", site + "/numpy.libs/libopenblas.so", "BINARY"),
        ("z", site + "/__pycache__/x.pyc", "DATA"),
    ]
    missing, unattributed = check_build.manifest_gaps(entries, "", mapping={})
    assert missing == [] and unattributed == []


def test_missing_manifest_file_fails_the_build(check_build, tmp_path):
    from tests.packaging.test_build_gates import make_tree

    dist, build = make_tree(tmp_path)
    failures = check_build.check(
        str(dist), str(build), CEILING,
        manifest=str(tmp_path / "absent.txt"), mapping={},
    )
    assert any("licence manifest not found" in f for f in failures)


def test_a_manifest_that_is_not_bundled_fails_the_build(
    check_build, tmp_path
):
    """It has to be inside the binary, not merely on the build machine."""
    from tests.packaging.test_build_gates import make_tree

    dist, build = make_tree(tmp_path)
    manifest = tmp_path / "THIRD_PARTY_LICENSES.txt"
    manifest.write_text("nltk\nfitz\npypdf\nlangdetect\ntextstat", encoding="utf-8")
    failures = check_build.check(
        str(dist), str(build), CEILING, manifest=str(manifest), mapping={}
    )
    assert len(failures) == 2, failures
    assert all("does not bundle THIRD_PARTY_LICENSES.txt" in f for f in failures)


def test_a_bundled_manifest_passes(check_build, tmp_path):
    from tests.packaging.conftest import write_toc
    from tests.packaging.test_build_gates import (
        CLI_SCRIPT, GUI_SCRIPT, GUI_EXTRA, clean_entries,
    )

    dist = tmp_path / "dist"
    build = tmp_path / "build" / "tta"
    dist.mkdir(parents=True)
    build.mkdir(parents=True)
    (dist / "tta").write_bytes(b"")
    (dist / "tta-gui").write_bytes(b"")
    bundled = ("THIRD_PARTY_LICENSES.txt", "/repo/build/licenses/x.txt", "DATA")
    write_toc(
        build / "Analysis-00.toc",
        clean_entries([bundled]),
        scripts=[CLI_SCRIPT],
    )
    write_toc(
        build / "Analysis-01.toc",
        clean_entries(list(GUI_EXTRA) + [bundled]),
        scripts=[GUI_SCRIPT],
    )
    manifest = tmp_path / "THIRD_PARTY_LICENSES.txt"
    manifest.write_text("everything is listed here", encoding="utf-8")
    failures = check_build.check(
        str(dist), str(build), CEILING, manifest=str(manifest), mapping={}
    )
    assert failures == []


def test_the_gate_is_skipped_when_no_manifest_is_passed(check_build, tmp_path):
    """So the size/purity gates remain usable on their own."""
    from tests.packaging.test_build_gates import make_tree

    dist, build = make_tree(tmp_path)
    assert check_build.check(str(dist), str(build), CEILING) == []


# --------------------------------------------- spec and workflow wiring


def test_spec_bundles_the_manifest(spec_source):
    tree = ast.parse(spec_source)
    datas = None
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "datas"
        ):
            datas = node.value
    assert datas is not None, "the spec has no datas list"
    assert "_licenses" in ast.dump(datas), (
        "the licence manifest is not in the spec's datas"
    )


def test_spec_refuses_to_build_without_the_manifest(spec_source):
    """A release must not be producible with no notices attached."""
    assert "TTA_THIRD_PARTY_LICENSES" in spec_source
    assert "os.path.isfile(_licenses)" in spec_source
    guard = spec_source.split("if not os.path.isfile(_licenses):", 1)[1][:400]
    assert "SystemExit" in guard
    assert "gen_third_party_licenses" in guard


def test_workflow_generates_the_manifest_before_freezing(workflow_source):
    generate = workflow_source.index("gen_third_party_licenses.py")
    freeze = workflow_source.index("pyinstaller packaging/tta.spec")
    assert generate < freeze, "the manifest must exist before PyInstaller runs"


def test_workflow_gate_checks_licence_coverage(workflow_source):
    assert "--manifest build/licenses/THIRD_PARTY_LICENSES.txt" in workflow_source


def test_workflow_proves_the_manifest_is_inside_the_binaries(workflow_source):
    assert "pyi-archive_viewer" in workflow_source
    assert "THIRD_PARTY_LICENSES.txt" in workflow_source


def test_workflow_ships_the_manifest_with_the_artifact(workflow_source):
    upload = workflow_source.split("upload-artifact", 1)[1]
    assert "THIRD_PARTY_LICENSES.txt" in upload


def test_build_extra_declares_pip_licenses():
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    build_line = [
        ln for ln in pyproject.splitlines() if ln.startswith("build = ")
    ]
    assert build_line, "no build extra in pyproject.toml"
    assert "pip-licenses" in build_line[0]
    assert "pyinstaller" in build_line[0]
