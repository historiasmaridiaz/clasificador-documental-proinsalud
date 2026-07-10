from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from core.catalog import build_catalog_from_files, save_catalog_json  # noqa: E402


def source_files(paths: list[str]) -> list[tuple[str, bytes]]:
    result = []
    for raw_path in paths:
        path = Path(raw_path)
        if path.is_dir():
            candidates = sorted(
                child
                for child in path.rglob("*")
                if child.is_file() and child.suffix.lower() in {".xlsx", ".xlsm", ".xls", ".csv", ".tsv", ".zip", ".rar"}
            )
        else:
            candidates = [path]
        for candidate in candidates:
            result.append((candidate.name, candidate.read_bytes()))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Normaliza archivos TRD/CCD en un catálogo JSON.")
    parser.add_argument("sources", nargs="+", help="Archivos o directorios con TRD/CCD")
    parser.add_argument("-o", "--output", required=True, help="Ruta del JSON de salida")
    parser.add_argument("--name", default="Catálogo TRD/CCD", help="Nombre descriptivo")
    args = parser.parse_args()

    build = build_catalog_from_files(source_files(args.sources))
    for error in build.errors:
        print(f"ADVERTENCIA: {error}", file=sys.stderr)
    if not build.entries:
        print("ERROR: no se detectaron registros.", file=sys.stderr)
        return 1
    save_catalog_json(
        build.entries,
        args.output,
        {
            "name": args.name,
            "sources": build.sources,
            "stats": build.stats,
            "trd_rows": build.trd_rows,
            "ccd_rows": build.ccd_rows,
        },
    )
    print(f"Catálogo creado: {args.output}")
    print(build.stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

