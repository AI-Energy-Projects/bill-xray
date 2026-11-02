"""Document layout parsing: PDF bill -> structured text + tables using Docling.

Run:  python parse.py samples/riverbend_tou_summer.pdf
"""

from __future__ import annotations

import os
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")   

import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
from docling.document_converter import DocumentConverter, PdfFormatOption


@dataclass
class ParsedBill:
    markdown: str              # whole document as Markdown (headings, text, tables)
    tables: list[pd.DataFrame]  # every table Docling found in reading order


@lru_cache(maxsize=2)
def make_converter(ocr: bool = False) -> DocumentConverter:
    """Build the Docling pipeline once; loading the models is the slow part."""
    opts = PdfPipelineOptions(do_ocr=ocr, do_table_structure=True)
    opts.table_structure_options.mode = TableFormerMode.ACCURATE   # better cell boundaries
    return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})


def table_to_df(table, doc) -> pd.DataFrame:
    try:
        return table.export_to_dataframe(doc=doc)   # newer Docling versions
    except TypeError:
        return table.export_to_dataframe()          # older versions


def parse_pdf(path: str | Path, ocr: bool = False) -> ParsedBill:
    doc = make_converter(ocr).convert(str(path)).document
    return ParsedBill(
        markdown=doc.export_to_markdown(),
        tables=[table_to_df(t, doc) for t in doc.tables],
    )


if __name__ == "__main__":
    pdf = sys.argv[1] if len(sys.argv) > 1 else "samples/riverbend_tou_summer.pdf"
    parsed = parse_pdf(pdf)
    print(parsed.markdown)
    print(f"\n=== {len(parsed.tables)} tables ===")
    for i, df in enumerate(parsed.tables):
        print(f"\n--- table {i}: columns = {list(df.columns)}")
        print(df.to_string(index=False))