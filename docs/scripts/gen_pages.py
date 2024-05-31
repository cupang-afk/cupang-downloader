"""Generate pages and example"""

from pathlib import Path

import mkdocs_gen_files

nav = mkdocs_gen_files.Nav()

root = Path(__file__).parent.parent.parent

# readme
with mkdocs_gen_files.open("README.md", "w") as readme_file:
    readme_file.writelines((root / "README.md").read_text())

# example
example = root / "example"
for path in sorted(example.rglob("*.py")):
    module_path = path.relative_to(example).with_suffix("")
    doc_path = path.relative_to(example).with_suffix(".md")
    full_doc_path = Path("example", doc_path)

    parts = tuple(list(module_path.parts[:-1]) + [module_path.name.replace("_", " ").title()])
    nav[parts] = doc_path.as_posix()

    with mkdocs_gen_files.open(full_doc_path, "w") as w:
        w.write(f"Example `{path.name}`\n\n```python\n{path.read_text()}```\n")


with mkdocs_gen_files.open("example/SUMMARY.md", "w") as nav_file:
    nav_file.writelines(nav.build_literate_nav())
