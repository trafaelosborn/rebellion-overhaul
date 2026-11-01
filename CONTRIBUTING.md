# Contributing

Keep changes small and explain the gameplay problem they are intended to solve. Separate a measured result from a hypothesis.

Run `python -m unittest discover -s tests -v` before submitting code changes. Add a regression test for a patching or restoration bug using synthetic bytes only. For a new preset, include expected original hashes, per-field original values, replacement values, and reasons.

For balance reports, include the preset, game distribution/version, side, difficulty, galaxy size, approximate game day, expected outcome, and observed outcome. A short reproducible example is more useful than a broad claim that one faction is stronger.

Never commit game binaries, full data exports, saves, images, audio, credentials, or local installation paths. Keep extraction output in `exports/` or `data/`, and backups in `backups/`; these directories are ignored. Do not use `git add -f` to bypass those exclusions.
