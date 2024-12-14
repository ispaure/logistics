import pyzipper
import patoolib
import zipfile
from shutil import make_archive


def unzip_file(source_file, destination_dir, pwd=None):
    """
    Extracts zip file to desired location.
    :param source_file: Path to file to extract.
    :type source_file: str
    :param destination_dir: Directory to extract into.
    :type destination_dir: str
    :param pwd: Password for extraction. Leave none if archive is not password protected.
    :type pwd: str
    """
    if pwd is None:
        with zipfile.ZipFile(source_file, 'r') as zip_ref:
            zip_ref.extractall(destination_dir)
    else:
        # # Legacy: Only works with ZIP 2.0 encryption method (legacy; unsecure)
        # with zipfile.ZipFile(source_file, 'r') as zip_ref:
        #     zip_ref.extractall(path=destination_dir, members=None, pwd=pwd.encode())

        # Following method works with both ZIP 2.0 AND AES-256 encryption methods (secure)
        with pyzipper.AESZipFile(source_file, 'r', compression=pyzipper.ZIP_DEFLATED,
                                 encryption=pyzipper.WZ_AES) as extracted_zip:
            extracted_zip.extractall(path=destination_dir,
                                     pwd=str.encode(pwd))


def unrar_file(source_file, destination_dir):
    """
    Extracts rar file to desired location.
    :param source_file: Path to file to extract.
    :type source_file: str
    :param destination_dir: Directory to extract into.
    :type destination_dir: str
    """
    if sys.platform == 'win32':
        patoolib.extract_archive(source_file, outdir=destination_dir)
    else:
        unrar_program_path = str(Path(config.LogisticsConfig().path_logistics_software, 'unrar'))
        patoolib.extract_archive(source_file, outdir=destination_dir, program=unrar_program_path)
    # TODO: Doesn't work for macos because cant find software. Need program= flag with proper software
    # TODO: Or alternate solution is interfacing with Keka through Commandline perhaps?: https://github.com/aonez/Keka/wiki/Terminal-support


def zip_file(source, destination, keep_root=True):
    """
    Create a zip file from the source to the destination.
    :param source: Source path to compress
    :type source: str
    :param destination: Destination path of compressed archive (incl. extension)
    :type destination: str
    :param keep_root: When source is a dir, keeps the dir as part of the archive as a root folder (Default true)
    :type keep_root: bool
    """
    def make_zipfile_keep_root(output_filename, source_dir):
        relroot = os.path.abspath(os.path.join(source_dir, os.pardir))
        with zipfile.ZipFile(output_filename, "w", zipfile.ZIP_DEFLATED) as zip:
            for root, dirs, files in os.walk(source_dir):
                # add directory (needed for empty dirs)
                zip.write(root, os.path.relpath(root, relroot))
                for file in files:
                    filename = os.path.join(root, file)
                    if os.path.isfile(filename):  # regular files only
                        arcname = os.path.join(os.path.relpath(root, relroot), file)
                        zip.write(filename, arcname)

    def make_zipfile_discard_root(source, destination):
        make_archive(destination, 'zip', source)

    if keep_root:
        make_zipfile_keep_root(destination, source)
    else:
        make_zipfile_discard_root(source, destination[:-len('.zip')])