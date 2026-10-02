"""
Image processing helpers for the Logistics Images feature.
"""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------
# IMPORTS

from pathlib import Path
from io import BytesIO
import os
import errno
import shutil
import stat
import commonUtils.fileUtils as fileUtils
from commonUtils import dirUtils
from PIL import Image, ImageStat, ImageOps, ImageCms
from commonUtils.debugUtils import *
from typing import *


# ----------------------------------------------------------------------------------------------------------------------
# User defined settings
image_file_cls_supported_ext_lst = ['jpg', 'jpeg', 'bmp', 'tif', 'tiff', 'webp', 'png', 'gif']  # Supported Extensions by the ImageFile class

default_path_to_convert_img = Path(fileUtils.get_user_home_dir(), 'Images2Convert')

# Decide to keep the compressed image if its size is smaller than this percentage of the original.
img_min_allowed_compression_percentage = 75
# ----------------------------------------------------------------------------------------------------------------------


def _source_signature(path: Path):
    snapshot = path.stat()
    return (snapshot.st_dev, snapshot.st_ino, snapshot.st_size, snapshot.st_mode,
            snapshot.st_mtime_ns, snapshot.st_ctime_ns)


def _publish_staged_image(staged_path: Path, destination: Path):
    """Publish without overwriting, falling back when hard links are unavailable."""
    try:
        os.link(staged_path, destination)
        return
    except OSError as error:
        if (error.errno not in {errno.EXDEV, errno.ENOSYS, errno.ENOTSUP, errno.EOPNOTSUPP, errno.EPERM}
                and getattr(error, 'winerror', None) not in (1, 50)):
            raise

    owns_destination = False
    try:
        with staged_path.open('rb') as source, destination.open('xb') as output:
            owns_destination = True
            shutil.copyfileobj(source, output)
            output.flush()
            os.fsync(output.fileno())
    except Exception:
        if owns_destination:
            destination.unlink()
        raise


def validate_compression_options(always_keep_compressed: bool,
                                 preserve_animated_and_multipage_originals: bool) -> bool:
    if always_keep_compressed and preserve_animated_and_multipage_originals:
        log(Severity.ERROR, 'Image compression',
            'Preserve animated and multipage originals cannot be used at same time as always keep compressed images.')
        return False
    return True


class ImageFile(fileUtils.File):
    def __init__(self, path: Path):
        super().__init__(path)
        self._source_signature = _source_signature(self.path)

        # Image-specific properties
        self.width: int = 0
        self.height: int = 0
        self.__set_width_height()
        self.color: Union[bool, None] = None

        self.compressed_image: Union[ImageFile, None] = None  # Gets updated with an ImageFile class if image gets compressed

    def __set_width_height(self):
        """Safely reads image dimensions without fully decoding the image."""
        try:
            with Image.open(self.path) as img:
                self.width, self.height = img.size
        except Exception as e:
            log(Severity.ERROR, "features.images.processing.ImageFile.__set_width_height",
                f"Failed to read image dimensions for {self.path}: {e}")
            raise

    def source_unchanged(self) -> bool:
        try:
            return _source_signature(self.path) == self._source_signature
        except FileNotFoundError:
            return False

    def __set_color_property(self, chroma_std_threshold: float = 2.5, sample_max: int = 512) -> bool:
        """
        Sets and returns self.color:
          - True  => color image
          - False => grayscale image

        Heuristic:
          - Convert to YCbCr and examine variation and mean of Cb/Cr channels.
          - Grayscale chroma is nearly flat and centered on neutral (128).
          - Uniform colors have low variation but non-neutral mean chroma.
          - JPEG artifacts or slight noise tolerated via threshold.

        Params:
          chroma_std_threshold: raise to be more forgiving (treat near-gray as grayscale).
          sample_max: downsize longest edge to this for speed; small color details can be diluted.
        """
        try:
            with Image.open(self.path) as img:
                # Fast path for obvious grayscale modes
                if img.mode in ("1", "L", "LA"):
                    self.color = False
                    return self.color

                # Normalize to YCbCr
                ycbcr = img.convert("YCbCr")

                # Optional downscale for speed on huge images
                w, h = ycbcr.size
                m = max(w, h)
                if m > sample_max:
                    scale = sample_max / float(m)
                    ycbcr = ycbcr.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.BILINEAR)

                _, cb, cr = ycbcr.split()
                cb_stats = ImageStat.Stat(cb)
                cr_stats = ImageStat.Stat(cr)

                # Keep the existing variation test and tolerance, and also detect
                # uniform color/tints whose chroma is offset from neutral.
                is_color = any(
                    channel.stddev[0] > chroma_std_threshold
                    or abs(channel.mean[0] - 128) > chroma_std_threshold
                    for channel in (cb_stats, cr_stats)
                )
                self.color = is_color
                return self.color

        except Exception as e:
            log(Severity.ERROR, "features.images.processing.ImageFile.__set_color_property",
                f"Failed to determine if image is color for {self.path}: {e}")
            raise

    def compress(self,
                 dest_path,
                 quality_grayscale: int,
                 quality_color: int,
                 max_long_edge: int | None = None,
                 max_height: int | None = None,
                 preserve_alpha: bool = True,
                 *, defer_replace: bool = False) -> bool:
        """
        Compresses the image file to a .JPG or .WEBP at the destination path.

        - Preserves alpha for WebP by default, including palette transparency.
        - Set preserve_alpha=False to discard transparency without compositing.
        - JPEG cannot preserve alpha and always discards it.
        - Encodes to a dot-prefixed sibling, then renames to dest_path on success.
        - Overwrites existing file at dest_path only after encoding and verification.
        - defer_replace=True leaves compressed_image pointing at the dot file so
          the caller can compare sizes before publishing or discarding it.
        - 'quality' ranges from 1 (lowest) to 95 (highest).
        - If max_long_edge is set (e.g., 2200), longest side is capped to that size.
        - If max_height is set (e.g., 3200), height is capped to that size.
          Both caps can be used independently or together.
        - Output format is deduced from dest_path extension (.jpg/.jpeg/.webp)
        """
        self.compressed_image = None
        dest_path = Path(dest_path)
        staged_path = dest_path.with_name(f'.{dest_path.name}')
        owns_stage = False
        leave_staged = False
        try:
            if not self.source_unchanged():
                raise RuntimeError(f'Source changed before compression: {self.path}')
            with Image.open(self.path) as img:
                img = ImageOps.exif_transpose(img)
                icc_profile = img.info.get('icc_profile')
                exif = img.getexif()

                if self.color is None:
                    self.__set_color_property()

                quality = quality_color if self.color else quality_grayscale

                dest_path = Path(dest_path)
                ext = dest_path.suffix.lower()
                has_alpha = 'A' in img.getbands() or 'transparency' in img.info
                converts_to_rgb = (ext == '.webp' or
                                   (ext in ('.jpg', '.jpeg') and (has_alpha or img.mode == 'P')))
                if icc_profile and converts_to_rgb:
                    source_profile = ImageCms.ImageCmsProfile(BytesIO(icc_profile))
                    color_space = source_profile.profile.xcolor_space.strip()
                    if color_space != 'RGB':
                        # WebP and JPEG alpha/palette removal produce RGB pixels.
                        # Convert non-RGB profiles with the pixels before encoding.
                        alpha = img.convert('RGBA').getchannel('A') if has_alpha else None
                        input_mode = {'CMYK': 'CMYK', 'GRAY': 'L'}.get(color_space)
                        if input_mode is None:
                            raise ValueError(f'Unsupported ICC color space: {color_space}')
                        output_profile = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB'))
                        img = ImageCms.profileToProfile(img.convert(input_mode), source_profile,
                            output_profile, outputMode='RGB')
                        if alpha is not None:
                            img.putalpha(alpha)
                        icc_profile = output_profile.tobytes()
                if has_alpha and preserve_alpha and ext == '.webp':
                    img = img.convert('RGBA')
                elif has_alpha or img.mode == 'P':
                    img = img.convert("RGB")

                # --- Unified downscale ---
                w, h = img.size
                scale = 1.0

                if max_height is not None and max_height > 0 and h > max_height:
                    scale = min(scale, max_height / float(h))

                if max_long_edge is not None and max_long_edge > 0 and max(w, h) > max_long_edge:
                    scale = min(scale, max_long_edge / float(max(w, h)))

                if scale < 1.0:
                    new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
                    img = img.resize(new_size, Image.Resampling.LANCZOS)
                # --------------------------

                dest_path.parent.mkdir(parents=True, exist_ok=True)
                with staged_path.open('xb'):
                    pass
                owns_stage = True

                metadata = {}
                if icc_profile:
                    metadata['icc_profile'] = icc_profile
                # Orientation has already been applied by exif_transpose.
                # Keep the remaining EXIF and update existing dimension tags.
                for tag, value in ((256, img.width), (257, img.height),
                                   (40962, img.width), (40963, img.height)):
                    if tag in exif:
                        exif[tag] = value
                if 34665 in exif:
                    exif_ifd = exif.get_ifd(34665)
                    for tag, value in ((40962, img.width), (40963, img.height)):
                        if tag in exif_ifd:
                            exif_ifd[tag] = value
                if exif:
                    metadata['exif'] = exif.tobytes()

                if ext in (".jpg", ".jpeg"):
                    img.save(staged_path, "JPEG", quality=quality, optimize=True, **metadata)
                elif ext == ".webp":
                    img.save(staged_path, "WEBP", quality=quality, method=6, **metadata)
                else:
                    log(Severity.CRITICAL, 'ImageFile.compress', f"Unsupported export format: {ext}")
                    return False

            # Close the input before replacement (also required on Windows).
            with Image.open(staged_path) as encoded:
                encoded.verify()
            if not self.source_unchanged():
                raise RuntimeError(f'Source changed during compression: {self.path}')
            if defer_replace:
                self.compressed_image = self.__class__(staged_path)
                leave_staged = True
            else:
                if dest_path.exists():
                    staged_path.chmod(stat.S_IMODE(dest_path.stat().st_mode))
                os.replace(staged_path, dest_path)
                self.compressed_image = self.__class__(dest_path)
            self.compressed_image.color = self.color
            return True

        except Exception as e:
            log(Severity.ERROR,
                'features.images.processing.ImageFile.compress',
                f'Failed to convert/compress image {self.path}: {e}')
            return False
        finally:
            if owns_stage and not leave_staged and staged_path.exists():
                staged_path.unlink()

    def get_description(self):
        if self.color is None:
            color_description = 'Undefined'
        elif self.color:
            color_description = 'Color'
        else:
            color_description = 'Grayscale'
        return (f'{self.file_name} - Dimensions: {self.width}x{self.height}, Color: {color_description}, '
                f'Size {self.size} bytes')


def batch_compress_image(target_dir: Union[str, Path],
                         recursive: bool,
                         always_keep_compressed: bool,
                         img_quality_color: int,
                         img_quality_grayscale: int,
                         img_max_long_edge: Optional[int],
                         img_max_height: Optional[int],
                         preserve_animated_and_multipage_originals: bool | None = None):
    """Stage WebP encodings as dot-prefixed siblings, then retain or replace originals."""
    func_name = 'batch_compress_image'
    if preserve_animated_and_multipage_originals is None:
        preserve_animated_and_multipage_originals = not always_keep_compressed
    if not validate_compression_options(always_keep_compressed, preserve_animated_and_multipage_originals):
        return False

    # --------------------------------------------------------------------------------------------------------------
    # STEP ONE: GATHER LIST OF IMAGE FILES TO CONVERT
    target_dir = dirUtils.Directory(Path(target_dir) if isinstance(target_dir, str) else target_dir)
    original_img_file_cls_lst: List[ImageFile] = []
    file_lst: List[fileUtils.File] = target_dir.list_files(recursive=recursive)

    try:
        for file in file_lst:
            if file.ext in image_file_cls_supported_ext_lst and not file.file_name.startswith('.'):
                image_file_cls = ImageFile(file.path)
                original_img_file_cls_lst.append(image_file_cls)
    except Exception as error:
        log(Severity.ERROR, 'Image compression', f'Could not inspect input: {error}')
        return False

    # Stage every encoding beside its destination so WebP inputs remain intact
    # until the strict size rule (or explicit override) chooses the new file.
    for img_file_cls in original_img_file_cls_lst:
        source_path = img_file_cls.path
        dest_path = source_path if img_file_cls.ext == 'webp' else source_path.with_suffix('.webp')
        staged_path = None
        owns_staged_file = False
        try:
            if not img_file_cls.source_unchanged():
                raise RuntimeError(f'Source changed before compression: {source_path}')
            if preserve_animated_and_multipage_originals:
                with Image.open(source_path) as image:
                    if getattr(image, 'n_frames', 1) > 1:
                        log(Severity.INFO, 'Image compression', f'Keeping animated/multipage original: {source_path}')
                        continue
            if dest_path != source_path and (dest_path.exists() or dest_path.is_symlink()):
                raise FileExistsError(f'Output already exists: {dest_path}')
            log(Severity.DEBUG, f'features.images.processing.{func_name}',
                f'Compressing {img_file_cls.file_name}...')
            result = img_file_cls.compress(
                dest_path=dest_path,
                defer_replace=True,
                quality_grayscale=img_quality_grayscale,
                quality_color=img_quality_color,
                max_long_edge=img_max_long_edge,
                max_height=img_max_height,
            )
            if not result:
                raise OSError(f'Could not compress {source_path}')
            staged_path = img_file_cls.compressed_image.path
            owns_staged_file = True
            if not img_file_cls.source_unchanged():
                raise RuntimeError(f'Source changed during compression: {source_path}')

            if (always_keep_compressed or img_file_cls.compressed_image.size
                    < img_file_cls.size * img_min_allowed_compression_percentage / 100):
                if dest_path == source_path:
                    # Same-filesystem replacement keeps a WebP source intact
                    # until its complete replacement is ready.
                    staged_path.chmod(stat.S_IMODE(source_path.stat().st_mode))
                    os.replace(staged_path, dest_path)
                else:
                    # Exclusive publication refuses a destination created by
                    # another operation while this image was being encoded.
                    _publish_staged_image(staged_path, dest_path)
                    staged_path.unlink()
                    if not img_file_cls.source_unchanged():
                        raise RuntimeError(f'Output created, but source changed before deletion: {source_path}')
                    if not img_file_cls.delete_file():
                        raise OSError(f'Output created, but could not delete {source_path}')
            # Otherwise cleanup discards the stage and retains the source bytes.
        except Exception as error:
            log(Severity.ERROR, f'features.images.processing.{func_name}', str(error))
            return False
        finally:
            if owns_staged_file and staged_path.exists():
                staged_path.unlink()

    log(Severity.INFO, 'Image Compression', 'Images Compression Completed successfully!')
    return True
