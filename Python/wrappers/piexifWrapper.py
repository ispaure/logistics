import piexif
import commonUtils.fileUtils as fileUtils


def jpg_batch_set_exif_comments(target_dir, recursive, comments):
    """
    In designated folder, batch set exif comments for .jpg files to whichever is set in comments
    """

    # Gather list of JPG files
    jpg_file_lst = fileUtils.get_file_path_list(target_dir, recursive, filter_extension='jpg')

    # For each file, assign comments tag only if it doesn't match
    for jpg_file in jpg_file_lst:
        jpg_set_exif_comments(jpg_file, comments)

    print('DONE!')


def jpg_set_exif_comments(jpg_file, comments):
    """
    Modifies a jpg file by setting the comments tag if the comments doesn't match the file's current comments tag
    """

    def set_comments():
        """
        Has determined comments need to be set. Set it.
        """
        # Set comments procedure initiated!

        # Create comments tuple
        comments_byte_tuple = tuple(bytes(comments, 'utf-8'))
        # Add 0 between each item and at end
        comments_byte_tuple = tuple(item for pair in zip(comments_byte_tuple, (0,) * len(comments_byte_tuple)) for item in pair) + (0, 0)

        # Show some debug info (string transformed to bytes)
        print('"Comments" field to set (in string form): ' + comments)
        print('"Comments" field to set (in bytes form): ' + str(comments_byte_tuple))

        print('Original dict')
        print(jpg_exif_dict)

        # Modify the original dict
        new_jpg_exif_dict = jpg_exif_dict
        new_jpg_exif_dict['0th'][comments_tag_address] = comments_byte_tuple

        print('Modified dict')
        print(new_jpg_exif_dict)

        # Dump back in file
        piexif.insert(piexif.dump(new_jpg_exif_dict), jpg_file)

    print('\nLoading .JPG file: ' + jpg_file)

    # Load JPG's EXIF
    jpg_exif_dict = piexif.load(jpg_file)
    dict_0th = jpg_exif_dict['0th']

    # See if Comments Tag is set
    comments_tag_address = 40092

    if comments_tag_address in dict_0th.keys():

        comments_in_file_bytes_tuple = dict_0th[comments_tag_address]
        comments_in_file_bytes_tuple_rem_0 = tuple(filter(lambda x: x != 0, comments_in_file_bytes_tuple))

        comments_in_file_str = str(bytes(comments_in_file_bytes_tuple_rem_0).decode('utf-8'))

        print('Found "Comments" Tag: ' + comments_in_file_str)
        print('Existing "Comments" Bytes Tuple: ' + str(dict_0th[comments_tag_address]))

        if comments != comments_in_file_str:
            set_comments()
            return True
        else:
            print('Comments match, no need to do anything.')
            return False
    else:
        print('Did not found a "Comments" Tag.')
        set_comments()
        return True
