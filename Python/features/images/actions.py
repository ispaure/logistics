"""
User-facing actions for the Logistics Images feature.
"""

# ----------------------------------------------------------------------------------------------------------------------
# IMPORTS

from pathlib import Path

from commonUtils.integrations.wrappers import piexifWrapper

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
        max_height: int | None,
        preserve_animated_and_multipage_originals: bool | None = None,
        exclude_webp: bool = False):
    """Batch compress supported images to WEBP."""

    return processing.batch_compress_image(
        target_dir=target_dir,
        recursive=recursive,
        always_keep_compressed=always_keep_compressed,
        img_quality_color=quality_color,
        img_quality_grayscale=quality_grayscale,
        img_max_long_edge=max_long_edge,
        img_max_height=max_height,
        preserve_animated_and_multipage_originals=preserve_animated_and_multipage_originals,
        exclude_webp=exclude_webp
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


def compress_folders(target_dirs, *, recursive=True, always_keep_compressed=False,
                     quality_color=80, quality_grayscale=45, max_long_edge=5120,
                     max_height=None, preserve_animated_and_multipage_originals=True,
                     exclude_webp=True, report=lambda done, total, message: None,
                     cancelled=lambda: False):
    """Cancellable folder workflow with per-image outcomes and system-folder policy."""
    from commonUtils.runtime.operations import run_batch
    from commonUtils.filesystem.traversal import scan_directory, natural_path_key
    from services.folder_safety import require_safe_folder
    if not processing.validate_compression_options(always_keep_compressed, preserve_animated_and_multipage_originals):
        raise ValueError('Preserve originals and always keep compressed images cannot be combined')
    if isinstance(target_dirs, (str, Path)):
        target_dirs = (target_dirs,)
    roots = [require_safe_folder(root, recursive=recursive) for root in target_dirs]
    paths = set()
    for root in roots:
        paths.update(path for path in scan_directory(root, recursive=recursive, cancelled=cancelled)
                     if not path.is_symlink() and path.suffix.lower().lstrip('.') in processing.image_file_cls_supported_ext_lst
                     and not (exclude_webp and path.suffix.lower() == '.webp'))
    outcomes = {}
    def compress(path):
        require_safe_folder(path.parent, recursive=False)
        outcomes[path] = processing.compress_image(processing.ImageFile(path),
            always_keep_compressed=always_keep_compressed, img_quality_color=quality_color,
            img_quality_grayscale=quality_grayscale, img_max_long_edge=max_long_edge,
            img_max_height=max_height,
            preserve_animated_and_multipage_originals=preserve_animated_and_multipage_originals)
    result = run_batch(sorted(paths, key=natural_path_key), compress, progress=report, cancelled=cancelled)
    return result, outcomes
