# Publish this repository to GitHub

This project is prepared as a local Git repository with an initial commit. It has **not** been pushed to GitHub.

Suggested remote name: `mfat/gtkghostty`.

## GitHub CLI

1. Extract the full archive preserving its `.git` directory.
2. Install and authenticate [GitHub CLI](https://cli.github.com/): `gh auth login`.
3. Change into the `gtkghostty` directory and run:

```sh
gh repo create mfat/gtkghostty --private --source=. --remote=origin --push --description "Reusable GTK4 terminal widget powered by libghostty-vt"
```

The command creates a **private** repository by default. Replace `--private` with `--public` only if you intend to publish it openly.

If a repository already exists, do **not** run `gh repo create`; instead add its remote URL and push after checking the existing repository's branches.

## GitHub web UI alternative

Create an empty repository at https://github.com/new, named `gtkghostty`, **without** initializing it with README or other files. Then, from the extracted project:

```sh
git remote add origin https://github.com/mfat/gtkghostty.git
git push -u origin main
```

Confirm the owner, repository URL, and visibility before pushing. Do not include any credentials in the repository.
