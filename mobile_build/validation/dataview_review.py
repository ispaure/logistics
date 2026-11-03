"""Generate the offline, original Notes Library sample supplied to App Review."""
import argparse
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED


FILES = {
    '.obsidian/': '',
    'Home.md': '''# Data view review

This note demonstrates automatic, read-only JavaScript views of personal data.

```dataviewjs
dv.header(2, "Inline view");
dv.paragraph("Inline script complete");
await dv.view("views/inventory", {path: "data/items.json"});
```

Open Source editing to inspect this code. Open data/items.json or
views/inventory.js in Files to inspect and edit their source. Save a changed
quantity, then reopen this note to refresh the table.
''',
    'views/inventory.js': '''const rows = JSON.parse(await dv.io.load(input.path));
dv.header(2, "Inventory");
dv.table(["Name", "Quantity"], rows.map(row => [row.name, row.quantity]));
dv.list(["Reusable view complete"]);
''',
    'data/items.json': json.dumps([{'name': 'Review pencils', 'quantity': 7}], indent=2) + '\n',
    'Blocked read.md': '''# Blocked read

This view deliberately attempts a path outside the library. Reading mode should
display a Data view error instead of reading a file.

```dataviewjs
dv.paragraph(await dv.io.load("../../outside.txt"));
```
''',
}


def write_archive(destination):
    """Write only synthetic, self-contained review content; never read user data."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Refuse to replace a previously prepared attachment accidentally.
    with ZipFile(destination, 'x', compression=ZIP_DEFLATED) as archive:
        for name, text in FILES.items():
            archive.writestr('Data view review/' + name, text)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(write_archive(args.output))


if __name__ == '__main__':
    main()
