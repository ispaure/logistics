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
import commonUtils.fileUtils as fileUtils
from PIL import Image, ImageStat, ImageOps
from commonUtils.debugUtils import *
from typing import *


# ----------------------------------------------------------------------------------------------------------------------
# User defined settings
image_file_cls_supported_ext_lst = ['jpg', 'jpeg', 'bmp', 'tif', 'tiff', 'webp', 'png', 'gif']  # Supported Extensions by the ImageFile class

default_path_to_convert_img = Path(fileUtils.get_user_home_dir(), 'Images2Convert')

# Decide to keep the compressed image if its size is smaller than this percentage of the original.
img_min_allowed_compression_percentage = 75
# ----------------------------------------------------------------------------------------------------------------------


class ImageFile(fileUtils.File):
    def __init__(self, path: Path):
        super().__init__(path)

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
            log(Severity.CRITICAL, "fileUtils.imageUtils.ImageFile.__set_width_height",
                f"Failed to read image dimensions for {self.path}: {e}")

    from PIL import Image, ImageChops

    def __set_color_property(self, chroma_std_threshold: float = 2.5, sample_max: int = 512) -> bool:
        """
        Sets and returns self.color:
          - True  => color image
          - False => grayscale image

        Heuristic:
          - Convert to YCbCr and examine stddev of Cb/Cr (chroma) channels.
          - Truly grayscale images have ~flat Cb/Cr => very low stddev.
          - JPEG artifacts or slight noise tolerated via threshold.

        Params:
          chroma_std_threshold: raise to be more forgiving (treat near-gray as grayscale).
          sample_max: downsize longest edge to this for speed; does not affect accuracy much.
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
                cb_std = ImageStat.Stat(cb).stddev[0]
                cr_std = ImageStat.Stat(cr).stddev[0]

                # If both chroma stddevs are tiny, it's grayscale
                is_color = (cb_std > chroma_std_threshold) or (cr_std > chroma_std_threshold)
                self.color = is_color
                return self.color

        except Exception as e:
            log(Severity.CRITICAL, "fileUtils.imageUtils.ImageFile.__set_color_property",
                f"Failed to determine if image is color for {self.path}: {e}")
            raise

    def compress(self,
                 dest_path,
                 quality_grayscale: int,
                 quality_color: int,
                 max_long_edge: int | None = None,
                 max_height: int | None = None) -> bool:
        """
        Compresses the image file to a .JPG or .WEBP at the destination path.

        - Automatically converts non-RGB formats (e.g. RGBA, P) to RGB.
        - Overwrites existing file at dest_path if present.
        - 'quality' ranges from 1 (lowest) to 95 (highest).
        - If max_long_edge is set (e.g., 2200), longest side is capped to that size.
        - If max_height is set (e.g., 3200), height is capped to that size.
          Both caps can be used independently or together.
        - Output format is deduced from dest_path extension (.jpg/.jpeg/.webp)
        """
        try:
            with Image.open(self.path) as img:
                img = ImageOps.exif_transpose(img)

                if self.color is None:
                    self.__set_color_property()

                quality = quality_color if self.color else quality_grayscale

                # Convert if image has alpha channel or palette
                if img.mode in ("RGBA", "LA", "P"):
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

                dest_path = Path(dest_path)
                dest_path.parent.mkdir(parents=True, exist_ok=True)

                ext = dest_path.suffix.lower()
                if ext in (".jpg", ".jpeg"):
                    img.save(dest_path, "JPEG", quality=quality, optimize=True)
                elif ext == ".webp":
                    img.save(dest_path, "WEBP", quality=quality, method=6)
                else:
                    log(Severity.CRITICAL, 'ImageFile.compress', f"Unsupported export format: {ext}")
                    return False

                self.compressed_image = self.__class__(dest_path)
                self.compressed_image.color = self.color
                return True

        except Exception as e:
            log(Severity.ERROR,
                'fileUtils.imageUtils.ImageFile.compress',
                f'Failed to convert/compress image {self.path}: {e}')
            return False

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
                         img_max_height: Optional[int]):
    """Batch compresses images, updating the original file with the changed file."""
    func_name = 'batch_compress_image'

    # --------------------------------------------------------------------------------------------------------------
    # STEP ONE: GATHER LIST OF IMAGE FILES TO CONVERT
    original_img_file_cls_lst: List[ImageFile] = []
    file_lst: List[fileUtils.File] = fileUtils.get_file_list_from_path(target_dir, recursive=recursive)

    for file in file_lst:
        if file.ext in image_file_cls_supported_ext_lst:
            image_file_cls = ImageFile(file.path)
            original_img_file_cls_lst.append(image_file_cls)

    # --------------------------------------------------------------------------------------------------------------
    # STEP TWO: COMPRESS LIST OF IMAGES TO .WEBP, REPLACE IF SMALLER OR ALWAYS_KEEP_COMPRESSED
    for img_file_cls in original_img_file_cls_lst:
        if img_file_cls.ext != 'webp':
            log(Severity.DEBUG, f'imageUtils.{func_name}', f'Compressing {img_file_cls.file_name}...')
            dest_path = img_file_cls.path.with_suffix('.webp')
            result = img_file_cls.compress(
                dest_path=dest_path,
                quality_grayscale=img_quality_grayscale,
                quality_color=img_quality_color,
                max_long_edge=img_max_long_edge,
                max_height=img_max_height,
            )

            if not result:
                msg = f'An error occurred whilst compressing {img_file_cls.file_name}!'
                log(Severity.ERROR, f'cbzUtils.{func_name}', msg)
                return False

            # STEP THREE: SELECT IMAGES TO KEEP
            if always_keep_compressed or img_file_cls.compressed_image.size < img_file_cls.size * img_min_allowed_compression_percentage / 100:
                img_file_cls.delete_file()
            else:
                img_file_cls.compressed_image.delete_file()
        else:
            msg = f'Image {img_file_cls.file_name} is already webp! Skipping...'
            log(Severity.DEBUG, f'imageUtils.{func_name}', msg)

    # Done
    log(Severity.INFO, 'Image Compression', 'Images Compression Completed successfully!')
