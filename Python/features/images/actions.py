"""
User-facing actions for the Logistics Images feature.
"""

# ----------------------------------------------------------------------------------------------------------------------
# IMPORTS

from pathlib import Path

from commonUtils.wrappers import piexifWrapper

from features.images import processing


# ----------------------------------------------------------------------------------------------------------------------
# IMAGE COMPRESSION

def get_default_compression_path() -> Path:
    """Return the default directory used by the image-compression tool."""

    return processing.default_path_to_convert_img


def batch_compress_to_webp(
        target_dir: str | Path,
        recursive: bool,
        always_keep_compressed: bool,
        quality_color: int,
        quality_grayscale: int,
        max_long_edge: int | None,
        max_height: int | None):
    """Batch compress supported images to WEBP."""

    return processing.batch_compress_image(
        target_dir=target_dir,
        recursive=recursive,
        always_keep_compressed=always_keep_compressed,
        img_quality_color=quality_color,
        img_quality_grayscale=quality_grayscale,
        img_max_long_edge=max_long_edge,
        img_max_height=max_height
    )


# ----------------------------------------------------------------------------------------------------------------------
# EXIF

def set_jpg_exif_comments(target_dir: str | Path, recursive: bool, comments: str) -> None:
    """Set the EXIF Comments field on JPG files in a directory."""

    piexifWrapper.jpg_batch_set_exif_comments(
        target_dir=target_dir,
        recursive=recursive,
        comments=comments
    )
