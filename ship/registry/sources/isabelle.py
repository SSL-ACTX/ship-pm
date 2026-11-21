"""ManifestRecipe for Isabelle theorem prover (cl.cam.ac.uk dist index)."""

from ship.api.sources import HtmlDistIndex, ManifestRecipe

_DIST_URL = "https://www.cl.cam.ac.uk/research/hvg/Isabelle/dist/index.html"
_BASE_URL = "https://www.cl.cam.ac.uk/research/hvg/Isabelle/dist/"

# Group 1 → version (e.g. "2026" or "2025_RC1")
# Group 2 → platform suffix (e.g. "linux_arm", "linux", "macos_arm", "macos") or absent
_FILENAME_PATTERN = (
    r"^Isabelle(\d{4}(?:_RC\d+)?)(?:_(linux_arm|linux|macos_arm|macos))?\.tar\.gz$"
)

_TRIPLE_MAP: dict[str, list[str]] = {
    "linux": ["x86_64-linux-gnu"],
    "linux_arm": ["aarch64-linux-gnu"],
    "macos": ["x86_64-apple-darwin"],
    "macos_arm": ["aarch64-apple-darwin"],
}


def _make_index() -> HtmlDistIndex:
    return HtmlDistIndex(
        url=_DIST_URL,
        base_url=_BASE_URL,
        filename_pattern=_FILENAME_PATTERN,
    )


RECIPE = (
    ManifestRecipe("isabelle")
    .description("Isabelle \u2014 a generic proof assistant")
    .author("Lawrence C. Paulson et al.")
    .homepage("https://isabelle.in.tum.de/")
    .repository("https://isabelle.sketis.net/repos/isabelle")
    .license("BSD-3-Clause")
    .versions_from(lambda: _make_index().list_versions())
    .resolve_targets(
        lambda version: {
            triple: asset.to_dict()
            for triple, asset in _make_index()
            .resolve_targets(
                version=version,
                pkg_name="isabelle",
                triple_map=_TRIPLE_MAP,
                binaries={"isabelle": "bin/isabelle"},
            )
            .items()
        }
    )
)
