"""Statistics and text logs for comic compression."""

from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import List
from commonUtils.fileTypes import txtType


class CompressionStats:
    def __init__(self):
        self.has_comicinfo_xml: Optional[bool] = None
        self.original_images_size = 0
        self.compressed_images_size = 0
        self.kept_images_size = 0
        self.kept_images_compressed_cnt = 0
        self.kept_images_original_cnt = 0
        self.total_file_count = 0
        self.compressed_file_count = 0
        self.already_compressed_file_count = 0
        self.error_during_compression = 0
        self.processed_file_count = 0
        self.cancelled = False
        self.remaining = []
        self.failed = {}

    def reset(self):
        for key in (
            "original_images_size", "compressed_images_size",
            "kept_images_size", "kept_images_compressed_cnt",
            "kept_images_original_cnt", "total_file_count",
            "compressed_file_count", "already_compressed_file_count",
            "error_during_compression"
        ):
            setattr(self, key, 0)
        self.has_comicinfo_xml = None
        self.processed_file_count = 0
        self.cancelled = False
        self.remaining = []
        self.failed = {}

    def __add__(self, other: CompressionStats) -> CompressionStats:
        new = CompressionStats()
        for key in (
            "original_images_size", "compressed_images_size",
            "kept_images_size", "kept_images_compressed_cnt",
            "kept_images_original_cnt", "total_file_count",
            "compressed_file_count", "already_compressed_file_count",
            "error_during_compression"
        ):
            setattr(new, key, getattr(self, key) + getattr(other, key))
        return new

    def __iadd__(self, other: CompressionStats) -> CompressionStats:
        for key in (
            "original_images_size", "compressed_images_size",
            "kept_images_size", "kept_images_compressed_cnt",
            "kept_images_original_cnt", "total_file_count",
            "compressed_file_count", "already_compressed_file_count",
            "error_during_compression"
        ):
            setattr(self, key, getattr(self, key) + getattr(other, key))
        return self

    def __to_mb(self, value_bytes: int) -> float:
        return value_bytes / (1024 * 1024)

    def get_summary(self):

        summary = "||Compression Statistics||\n"

        # conversions and helpers

        reduction_bytes = self.original_images_size - self.kept_images_size
        new_size_mb = self.get_new_size_mb()
        orig_size_mb = self.get_original_size_mb()
        reduction_mb = self.__to_mb(reduction_bytes)

        if self.original_images_size == 0:
            reduction_pct = 'N/A'
            new_pct = 'N/A'
        else:
            reduction_pct = 100 - (self.kept_images_size / self.original_images_size * 100)
            reduction_pct = f'-{reduction_pct:.2f}'
            new_pct = self.kept_images_size / self.original_images_size * 100
            new_pct = f'{new_pct:.2f}'

        if getattr(self, "total_file_count", 0) > 0:
            summary += (
                "  |CBZ Files|\n"
                f"    Total File Count in Dir:    {self.total_file_count}\n"
                f"    Already Compressed:         {self.already_compressed_file_count}\n"
                f"    Error During Compression:   {self.error_during_compression}\n"
                f"    Successful Compression:     {self.compressed_file_count}\n"
            )

        summary += (
            f"  |Images|\n"
            f"    Original # Kept:            {self.kept_images_original_cnt}\n"
            f"    Compressed # Kept:          {self.kept_images_compressed_cnt}\n"
            f"  |Archive|\n"
            f"    Original Size:              {orig_size_mb:.2f} MB\n"
            f"    Reduction Size:             {reduction_mb:.2f} MB\n"
            f"    New Size:                   {new_size_mb:.2f} MB\n"
            f"    Reduction (%):              {reduction_pct}%\n"
            f"    New (%):                    {new_pct}%"
        )

        return summary

    def get_original_size_mb(self):
        return self.__to_mb(self.original_images_size)

    def get_new_size_mb(self):
        return self.__to_mb(self.kept_images_size)

    def print_summary(self):
        """Print only the integer stats in a clean format."""
        print(self.get_summary())


class CompressionLog:
    def __init__(self, name: str):
        self.name: str = name
        self.ext = 'cbz'
        self.__compression_log_line_lst: List[str] = []

    def append(self, string: str):
        self.__compression_log_line_lst.extend(string.split("\n"))

    def append_skip_line(self):
        self.__compression_log_line_lst.append('')

    def append_msg_start(self, quality_grayscale, quality_color, always_keep_compressed):
        self.append(f'|| Compression Log "{self.name}" ||')
        self.append(f'Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        self.append(f'Quality Setting for WEBP Compression: Grayscale: "{quality_grayscale}", Color: "{quality_color}"')
        if always_keep_compressed:
            self.append(f'Parameter: Always Keep Compressed Image, Regardless if Smaller')
        self.append_skip_line()

    def append_msg_end(self, compression_stats: CompressionStats):
        self.append_skip_line()
        self.append(compression_stats.get_summary())

    def reset(self):
        self.__compression_log_line_lst = []

    def export(self, export_path: Path):
        txt_file = txtType.TXTFile(export_path)
        txt_file.line_lst = self.__compression_log_line_lst
        txt_file.write_lines()


