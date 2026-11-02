"""Release numbering must remain unique without version-bump commits."""
from scripts.release_version import next_release_version


def test_next_patch_uses_latest_release_even_when_source_version_is_older():
    assert next_release_version("0.4.1", ["v0.4.1", "v0.4.9", "v0.4.10"]) == "0.4.11"


def test_explicit_minor_bump_is_respected():
    assert next_release_version("0.5.0", ["v0.4.10"]) == "0.5.0"


def test_prerelease_and_unrelated_tags_do_not_affect_numbering():
    assert next_release_version("0.4.1", ["nightly", "v9.0.0-rc1"]) == "0.4.1"


def test_rerun_reuses_release_for_same_commit():
    assert next_release_version("0.4.1", ["v0.4.2", "v0.4.3"], ["v0.4.2"]) == "0.4.2"
