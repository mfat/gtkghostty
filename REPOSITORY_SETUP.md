# Repository status and development bootstrap

The repository has already been created at [`mfat/gtkghostty`](https://github.com/mfat/gtkghostty). The previous repository-creation instructions are obsolete.

Clone the existing repository:

~~~sh
git clone https://github.com/mfat/gtkghostty.git
cd gtkghostty
~~~

Follow [README.md](README.md), [docs/ADR-0001-extraction-first.md](docs/ADR-0001-extraction-first.md), and [docs/EXTRACTION_FEASIBILITY.md](docs/EXTRACTION_FEASIBILITY.md). This is a research/documentation repository; no widget binary or tested extraction is included.

To fetch upstream reference snapshots, run:

~~~sh
python3 tools/fetch_reference_sources.py --list
python3 tools/fetch_reference_sources.py --only ghostty-app
~~~

Reference checkouts remain ignored and are not vendored into this repository.
