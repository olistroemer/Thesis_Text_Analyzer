"""ADR-0014 build gates: the checker's logic (#52).

The release build is the one artefact no application test observes. #52
shipped a 212 MB binary in which ~288 MB of 533 MB uncompressed came from
llvmlite, scipy, pandas and numba - none of them declared dependencies, two
of them collected from the builder's ~/.local. These tests pin the checker
that now makes such a build fail in CI.
"""

import pathlib

from tests.packaging.conftest import write_toc

CLI_SCRIPT = "/repo/tta/cli/main.py"
GUI_SCRIPT = "/repo/tta/ui/tk/app.py"
SITE = "/opt/env/lib/python3.12/site-packages"

CEILING = 150 * 1024 * 1024


def clean_entries(extra=()):
    """A minimal, honest dependency graph: stdlib + declared deps only."""
    entries = [
        ("subprocess", "/usr/lib/python3.12/subprocess.py", "PYMODULE"),
        ("nltk", SITE + "/nltk/__init__.py", "PYMODULE"),
        ("nltk.tokenize", SITE + "/nltk/tokenize/__init__.py", "PYMODULE"),
        ("fitz", SITE + "/fitz/__init__.py", "PYMODULE"),
        ("pypdf", SITE + "/pypdf/__init__.py", "PYMODULE"),
        ("langdetect", SITE + "/langdetect/__init__.py", "PYMODULE"),
        ("textstat", SITE + "/textstat/__init__.py", "PYMODULE"),
        ("libpython3.12.so.1.0", "/usr/lib/libpython3.12.so.1.0", "BINARY"),
        (
            "nltk_data/tokenizers/punkt_tab/README",
            "/home/u/nltk_data/tokenizers/punkt_tab/README",
            "DATA",
        ),
    ]
    entries.extend(extra)
    return entries


# #53 removed matplotlib from the dependency set, so the GUI's own stack is
# just Tk plus the grid widget.
GUI_EXTRA = [
    ("tkinter", "/usr/lib/python3.12/tkinter/__init__.py", "PYMODULE"),
    ("tksheet", SITE + "/tksheet/__init__.py", "PYMODULE"),
]


def make_tree(tmp_path, cli_extra=(), gui_extra=GUI_EXTRA, sizes=(1000, 1000)):
    """A fake finished build tree: dist/ executables + build/tta/ TOCs."""
    dist = tmp_path / "dist"
    build = tmp_path / "build" / "tta"
    dist.mkdir(parents=True)
    build.mkdir(parents=True)
    (dist / "tta").write_bytes(b"\0" * sizes[0])
    (dist / "tta-gui").write_bytes(b"\0" * sizes[1])
    write_toc(
        build / "Analysis-00.toc",
        clean_entries(cli_extra),
        scripts=[CLI_SCRIPT],
    )
    write_toc(
        build / "Analysis-01.toc",
        clean_entries(gui_extra),
        scripts=[GUI_SCRIPT],
    )
    return dist, build


# ---------------------------------------------------------------- happy path


def test_clean_build_tree_passes_every_gate(check_build, tmp_path):
    dist, build = make_tree(tmp_path)
    assert check_build.check(str(dist), str(build), CEILING) == []


def test_main_exits_zero_on_a_clean_tree(check_build, tmp_path, capsys):
    dist, build = make_tree(tmp_path)
    rc = check_build.main(
        ["--dist", str(dist), "--build", str(build), "--max-bytes", str(CEILING)]
    )
    assert rc == 0
    assert "OK" in capsys.readouterr().out


# ------------------------------------------------------------ the size gate


def test_oversize_executable_fails_the_gate(check_build, tmp_path):
    dist, build = make_tree(tmp_path, sizes=(CEILING + 1, 1000))
    failures = check_build.check(str(dist), str(build), CEILING)
    assert len(failures) == 1
    assert "over the ADR-0014 ceiling" in failures[0]
    assert failures[0].endswith("(150.0 MiB)")


def test_executable_exactly_at_the_ceiling_passes(check_build, tmp_path):
    dist, build = make_tree(tmp_path, sizes=(CEILING, CEILING))
    assert check_build.check(str(dist), str(build), CEILING) == []


def test_both_executables_are_size_checked(check_build, tmp_path):
    dist, build = make_tree(tmp_path, sizes=(CEILING + 1, CEILING + 1))
    failures = check_build.check(str(dist), str(build), CEILING)
    assert len(failures) == 2


def test_missing_executable_is_a_failure_not_a_pass(check_build, tmp_path):
    """A build that produced nothing must not sail through the size gate."""
    dist, build = make_tree(tmp_path)
    (dist / "tta-gui").unlink()
    failures = check_build.check(str(dist), str(build), CEILING)
    assert len(failures) == 1
    assert "missing executable" in failures[0]


def test_main_exits_nonzero_when_a_gate_fails(check_build, tmp_path):
    dist, build = make_tree(tmp_path, sizes=(CEILING + 1, 1000))
    rc = check_build.main(
        ["--dist", str(dist), "--build", str(build), "--max-bytes", str(CEILING)]
    )
    assert rc == 1


# --------------------------------------------------- the contamination gate


def test_the_exact_regression_from_52_is_caught(check_build, tmp_path):
    """llvmlite + numba + pandas + scipy in the graph: one failure each."""
    contamination = [
        ("pandas", SITE + "/pandas/__init__.py", "PYMODULE"),
        ("pandas.core.frame", SITE + "/pandas/core/frame.py", "PYMODULE"),
        ("scipy.interpolate", SITE + "/scipy/interpolate/__init__.py", "PYMODULE"),
        ("numba", "/home/u/.local/lib/python3.12/site-packages/numba/__init__.py",
         "PYMODULE"),
        ("llvmlite", "/home/u/.local/lib/python3.12/site-packages/llvmlite/__init__.py",
         "PYMODULE"),
    ]
    dist, build = make_tree(tmp_path, cli_extra=contamination)
    failures = check_build.check(str(dist), str(build), CEILING)
    blob = "\n".join(failures)
    for package in ("pandas", "scipy", "numba", "llvmlite"):
        assert "excluded package %r" % package in blob
    # ...and the ~/.local provenance is reported separately, because the
    # excludes alone would not tell you the build environment was dirty.
    assert "user site directory" in blob


def test_forbidden_package_is_caught_in_the_gui_graph_too(check_build, tmp_path):
    """Both Analysis objects are checked - #52 affected both binaries."""
    dist, build = make_tree(
        tmp_path,
        gui_extra=GUI_EXTRA + [("scipy", SITE + "/scipy/__init__.py", "PYMODULE")],
    )
    failures = check_build.check(str(dist), str(build), CEILING)
    assert len(failures) == 1
    assert "Analysis-01.toc" in failures[0]
    assert "'scipy'" in failures[0]


def test_shared_library_directories_are_attributed(check_build, tmp_path):
    """scipy.libs/*.so is a bundled path, not a module name."""
    dist, build = make_tree(
        tmp_path,
        cli_extra=[
            (
                "scipy.libs/libopenblasp-r0-01191904.so",
                SITE + "/scipy.libs/libopenblasp-r0-01191904.so",
                "BINARY",
            )
        ],
    )
    failures = check_build.check(str(dist), str(build), CEILING)
    assert any("'scipy'" in f for f in failures)


def test_a_lookalike_package_name_is_not_a_false_positive(check_build, tmp_path):
    """'pandas' must match the package, not any name starting with it."""
    dist, build = make_tree(
        tmp_path,
        cli_extra=[
            ("pandasql_lookalike", SITE + "/pandasql_lookalike.py", "PYMODULE"),
            ("scipython", SITE + "/scipython/__init__.py", "PYMODULE"),
        ],
    )
    assert check_build.check(str(dist), str(build), CEILING) == []


def test_a_source_path_containing_pandas_is_not_enough(check_build, tmp_path):
    """Attribution is by bundled destination, not by the build machine path."""
    dist, build = make_tree(
        tmp_path,
        cli_extra=[("mymod", "/home/u/src/pandas-notes/mymod.py", "PYMODULE")],
    )
    assert check_build.check(str(dist), str(build), CEILING) == []


def test_the_user_site_gate_covers_all_three_matrix_platforms(check_build):
    """A POSIX-only marker would make this gate green on 3 of 4 targets.

    ADR-0014's build matrix freezes on Windows and macOS too, and each puts
    the per-user site somewhere else. The gate exists to catch a build that
    drew files from the builder's own home; if it only recognised
    ~/.local/lib it would silently pass exactly there.
    """
    entries = [
        ("numpy", "/home/u/.local/lib/python3.12/site-packages/numpy/a.py",
         "PYMODULE"),
        ("numba",
         "C:\\Users\\u\\AppData\\Roaming\\Python\\Python312"
         "\\site-packages\\numba\\a.py", "PYMODULE"),
        ("llvmlite",
         "/Users/u/Library/Python/3.12/lib/python/site-packages/llvmlite/a.py",
         "PYMODULE"),
        ("nltk", SITE + "/nltk/__init__.py", "PYMODULE"),
    ]
    leaked = check_build.user_site_sources(entries)
    assert len(leaked) == 3, leaked
    assert not any(SITE in source for source in leaked)


def test_user_site_markers_include_the_running_interpreters_own(check_build):
    import site as _site

    markers = check_build.user_site_markers()
    own = _site.getusersitepackages().replace("\\", "/").rstrip("/").lower()
    assert own + "/" in markers


def test_a_windows_user_site_leak_fails_the_gate(check_build, tmp_path):
    """The same failure #52 hit, on the target that ADR-0014 added later."""
    dist, build = make_tree(
        tmp_path,
        cli_extra=[
            ("scipy",
             "C:\\Users\\u\\AppData\\Roaming\\Python\\Python312"
             "\\site-packages\\scipy\\__init__.py", "PYMODULE")
        ],
    )
    failures = check_build.check(str(dist), str(build), CEILING)
    assert any("PYTHONNOUSERSITE=1" in f for f in failures)


def test_user_site_provenance_is_reported_on_its_own(check_build, tmp_path):
    """A file from ~/.local fails even if the package is otherwise allowed.

    This is the gate that would have caught #52 at the source: the numpy in
    that build was itself resolved from the user site.
    """
    dist, build = make_tree(
        tmp_path,
        cli_extra=[
            ("numpy", "/home/u/.local/lib/python3.12/site-packages/numpy/__init__.py",
             "PYMODULE")
        ],
    )
    failures = check_build.check(str(dist), str(build), CEILING)
    assert len(failures) == 1
    assert "PYTHONNOUSERSITE=1" in failures[0]


# ------------------------------------------------- the per-binary split gate


def test_gui_only_packages_in_the_cli_graph_fail(check_build, tmp_path):
    """The #52 symptom that made the CLI binary larger than the GUI."""
    dist, build = make_tree(tmp_path, cli_extra=GUI_EXTRA)
    failures = check_build.check(str(dist), str(build), CEILING)
    assert len(failures) == 1
    assert "the CLI graph" in failures[0]
    assert "tksheet" in failures[0]


def test_gui_only_packages_in_the_gui_graph_are_fine(check_build, tmp_path):
    dist, build = make_tree(tmp_path)
    assert check_build.check(str(dist), str(build), CEILING) == []


def test_a_gui_graph_stripped_of_its_own_stack_fails(check_build, tmp_path):
    """The mirror image of the CLI gate, and a smaller binary either way.

    Applying CLI_EXCLUDES to both Analysis objects would shrink the GUI
    binary and pass every size gate, then die the moment the window opens.
    """
    dist, build = make_tree(tmp_path, gui_extra=())
    failures = check_build.check(str(dist), str(build), CEILING)
    assert len(failures) == 1
    assert "the GUI graph" in failures[0] and "MISSING" in failures[0]
    for package in ("tksheet", "tkinter"):
        assert package in failures[0]


def test_a_gui_graph_missing_only_one_package_still_fails(check_build, tmp_path):
    dist, build = make_tree(
        tmp_path,
        gui_extra=[e for e in GUI_EXTRA if e[0] != "tksheet"],
    )
    failures = check_build.check(str(dist), str(build), CEILING)
    assert len(failures) == 1
    assert "tksheet" in failures[0]
    assert "matplotlib" not in failures[0]


def test_gui_required_and_gui_only_agree_about_the_gui_stack(check_build):
    """A package cannot be required in the GUI and unnamed as GUI-only."""
    assert set(check_build.GUI_REQUIRED) <= set(check_build.GUI_ONLY) | {"tkinter"}
    assert not set(check_build.GUI_REQUIRED) & set(check_build.FORBIDDEN)


def test_classification_does_not_depend_on_analysis_numbering(
    check_build, tmp_path
):
    """Swap the file names: the GUI stack must still be judged by entry point.

    Analysis-00 happens to be the CLI today only because the spec declares
    cli_a first; the gate must not silently invert if that order changes.
    """
    dist = tmp_path / "dist"
    build = tmp_path / "build" / "tta"
    dist.mkdir(parents=True)
    build.mkdir(parents=True)
    (dist / "tta").write_bytes(b"")
    (dist / "tta-gui").write_bytes(b"")
    # GUI first this time.
    write_toc(
        build / "Analysis-00.toc", clean_entries(GUI_EXTRA), scripts=[GUI_SCRIPT]
    )
    write_toc(
        build / "Analysis-01.toc", clean_entries(), scripts=[CLI_SCRIPT]
    )
    assert check_build.check(str(dist), str(build), CEILING) == []


def test_a_build_tree_with_no_tocs_fails(check_build, tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "tta").write_bytes(b"")
    (dist / "tta-gui").write_bytes(b"")
    failures = check_build.check(str(dist), str(tmp_path / "nope"), CEILING)
    assert any("Analysis-*.toc" in f for f in failures)


def test_only_one_analysis_toc_is_a_failure(check_build, tmp_path):
    """Losing a binary's graph must not read as 'nothing to complain about'."""
    dist, build = make_tree(tmp_path)
    (build / "Analysis-01.toc").unlink()
    failures = check_build.check(str(dist), str(build), CEILING)
    assert any("expected one CLI and one GUI" in f for f in failures)


# ------------------------------------------------------------- unit-level bits


def test_top_level_handles_modules_paths_and_windows_separators(check_build):
    cases = {
        "scipy": "scipy",
        "scipy.interpolate": "scipy",
        "scipy.libs/libopenblas.so": "scipy",
        "matplotlib/mpl-data/fonts/x.ttf": "matplotlib",
        "matplotlib\\mpl-data\\fonts\\x.ttf": "matplotlib",
        "nltk_data/tokenizers/punkt_tab/README": "nltk_data",
        "libpython3.12.so.1.0": "libpython3",
    }
    for dest, expected in cases.items():
        assert check_build.top_level(dest) == expected, dest


def test_read_toc_finds_entries_at_any_nesting_depth(check_build, tmp_path):
    path = tmp_path / "Analysis-00.toc"
    path.write_text(
        repr(([], [[("a", "/a.py", "PYMODULE")]], (("b", "/b.so", "BINARY"),))),
        encoding="utf-8",
    )
    entries = check_build.read_toc(path)
    assert sorted(e[0] for e in entries) == ["a", "b"]


def test_read_toc_ignores_non_toc_triples(check_build, tmp_path):
    """The Analysis tuple also holds plain 3-element data (e.g. hookspath)."""
    path = tmp_path / "Analysis-00.toc"
    path.write_text(
        repr((["x", "y", "z"], [("/hooks", 0)], [("m", "/m.py", "PYMODULE")])),
        encoding="utf-8",
    )
    assert [e[0] for e in check_build.read_toc(path)] == ["m"]


def test_forbidden_and_gui_only_lists_do_not_overlap(check_build):
    """A package cannot be both required by the GUI and banned outright."""
    assert not set(check_build.FORBIDDEN) & set(check_build.GUI_ONLY)


def test_pillow_is_forbidden_outright(check_build):
    """#85: no binary decodes images any more (ADR-0021), so PIL is banned."""
    assert "PIL" in check_build.FORBIDDEN
    assert "PIL" not in check_build.GUI_ONLY
    assert "PIL" not in check_build.GUI_REQUIRED
    found = check_build.offenders(
        [("PIL/Image.py", "src", "PYMODULE"), ("pillow.libs/libjpeg.so.62", "src", "BINARY"),
         ("PIL.Image", "src", "PYMODULE")],
        check_build.FORBIDDEN,
    )
    assert set(found) == {"PIL", "pillow"}


def test_matplotlib_is_forbidden_outright(check_build):
    """#53 moved it from GUI-only to forbidden: the report is inline SVG now
    (ADR-0016 rev. 2), so no binary has any use for the plotting stack."""
    assert "matplotlib" in check_build.FORBIDDEN
    assert "matplotlib" not in check_build.GUI_ONLY
    assert "matplotlib" not in check_build.GUI_REQUIRED
