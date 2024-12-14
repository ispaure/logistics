
import wrappers.sqlWrapper as sqlWrapper


def get_plex_db_table_media_items(db_file):
    """
    Returns a list of the PLEX Media Items from its SQL Database (com.plexapp.plugins.library.db file)
    :param db_file: Path to the database file
    :type db_file: str
    """
    media_items_column_lst = ['id',
                              'library_section_id',
                              'section_location_id',
                              'metadata_item_id',
                              'type_id',
                              'width',
                              'height',
                              'size',
                              'duration',
                              'bitrate',
                              'container',
                              'video_codec',
                              'audio_codec',
                              'display_aspect_ratio',
                              'frames_per_second',
                              'audio_channels',
                              'interlaced',
                              'source',
                              'hints',
                              'display_offset',
                              'settings',
                              'created_at',
                              'updated_at',
                              'optimized_for_streaming',
                              'deleted_at',
                              'media_analysis_version',
                              'sample_aspect_ratio',
                              'extra_data',
                              'proxy_type',
                              'channel_id',
                              'begins_at',
                              'ends_at',
                              'color_trc']

    result = sqlWrapper.fetch_sql_table(db_file, 'media_items', media_items_column_lst)
    return result


def get_plex_db_table_metadata_items(db_file, filter_type=None):
    """
    Returns a list of the PLEX Metadata Items from its SQL Database (com.plexapp.plugins.library.db file)
    :param db_file: Path to the database file
    :type db_file: str
    :param filter_type: Type of metadata item to filter for ('Movies', 'TV Series', 'Seasons', 'Episodes', 'Other Videos', 'Photo' or 'Music')
    :param filter_type: str
    """
    metadata_items_column_lst = ['id',
                                 'library_section_id',
                                 'parent_id',
                                 'metadata_type',
                                 'guid',
                                 'media_item_count',
                                 'title',
                                 'title_sort',
                                 'original_title',
                                 'studio',
                                 'rating',
                                 'rating_count',
                                 'tagline',
                                 'summary',
                                 'trivia',
                                 'quotes',
                                 'content_rating',
                                 'content_rating_age',
                                 'absolute_index',
                                 'duration',
                                 'user_thumb_url',
                                 'user_art_url',
                                 'user_banner_url',
                                 'user_music_url',
                                 'user_fields',
                                 'tags_genre',
                                 'tags_collection',
                                 'tags_director',
                                 'tags_writer',
                                 'tags_star',
                                 'originally_available_at',
                                 'available_at',
                                 'expires_at',
                                 'refreshed_at',
                                 'year',
                                 'added_at',
                                 'created_at',
                                 'updated_at',
                                 'deleted_at',
                                 'tags_country',
                                 'extra_data',
                                 'hash',
                                 'audience_rating',
                                 'changed_at',
                                 'resources_changed_at',
                                 'remote',
                                 'edition_title']

    row_lst = sqlWrapper.fetch_sql_table(db_file, 'metadata_items', metadata_items_column_lst)

    if filter_type is None:
        return row_lst
    else:
        filtered_row_lst = []
        if filter_type == 'Movies':
            movie_section_ids = get_movies_library_section_ids(db_file)
            for row in row_lst:
                if row['metadata_type'] == 1 and row['library_section_id'] in movie_section_ids:
                    filtered_row_lst.append(row)
        elif filter_type == 'Episodes':
            for row in row_lst:
                if row['metadata_type'] == 4:
                    filtered_row_lst.append(row)
        elif filter_type == 'TV Series':
            for row in row_lst:
                if row['metadata_type'] == 2:
                    filtered_row_lst.append(row)
        elif filter_type == 'Seasons':
            for row in row_lst:
                if row['metadata_type'] == 3:
                    filtered_row_lst.append(row)
        elif filter_type == 'Other Videos':
            for row in row_lst:
                # TODO: Figure out filter
                pass
        elif filter_type == 'Photo':
            for row in row_lst:
                # TODO: Figure out filter
                pass
        elif filter_type == 'Music':
            for row in row_lst:
                if row['metadata_type'] == 10:
                    filtered_row_lst.append(row)
        else:
            print('Wrong Filter Type, Aborting!')
            return False

        return filtered_row_lst


def get_plex_db_table_library_sections(db_file, filter_type=None):
    """
    Returns a list of the PLEX Library Sections from its SQL Database (com.plexapp.plugins.library.db file)
    :param db_file: Path to the database file
    :type db_file: str
    :param filter_type: Type of Library to filter for ('Movies', 'Episodes', 'Other Videos', 'Photo' or 'Music')
    :param filter_type: str
    """
    library_sections_column_lst = ['id',
                                   'library_id',
                                   'name',
                                   'name_sort',
                                   'section_type',
                                   'language',
                                   'agent',
                                   'scanner',
                                   'user_thumb_url',
                                   'user_art_url',
                                   'user_theme_music_url',
                                   'public',
                                   'created_at',
                                   'updated_at',
                                   'scanned_at',
                                   'display_secondary_level',
                                   'user_fields',
                                   'query_xml',
                                   'query_type',
                                   'uuid',
                                   'changed_at',
                                   'content_changed_at']

    row_lst = sqlWrapper.fetch_sql_table(db_file, 'library_sections', library_sections_column_lst)

    if filter_type is None:
        return row_lst
    else:
        filtered_row_lst = []
        if filter_type == 'Movies':
            for row in row_lst:
                if row['section_type'] == 1 and row['language'] != 'xn':
                    filtered_row_lst.append(row)
        elif filter_type == 'Episodes':
            for row in row_lst:
                if row['section_type'] == 2:
                    filtered_row_lst.append(row)
        elif filter_type == 'Other Videos':
            for row in row_lst:
                if row['section_type'] == 1 and row['language'] == 'xn':
                    filtered_row_lst.append(row)
        elif filter_type == 'Photo':
            for row in row_lst:
                # TODO: Figure out the section type for photos
                if row['section_type'] == '?':
                    filtered_row_lst.append(row)
        elif filter_type == 'Music':
            for row in row_lst:
                if row['section_type'] == 8:
                    filtered_row_lst.append(row)
        else:
            print('Wrong Filter Type, Aborting!')
            return False

        return filtered_row_lst


def get_plex_db_table_media_parts(db_file):
    """
    Returns a list of the PLEX Media Parts from its SQL Database (com.plexapp.plugins.library.db file)
    :param db_file: Path to the database file
    :type db_file: str
    """
    media_parts_column_lst = ['id',
                              'media_item_id',
                              'directory_id',
                              'hash',
                              'open_subtitle_hash',
                              'file',
                              'size',
                              'duration',
                              'created_at',
                              'updated_at',
                              'deleted_at',
                              'extra_data']

    result = sqlWrapper.fetch_sql_table(db_file, 'media_parts', media_parts_column_lst)
    return result


def get_plex_db_table_media_parts_with_guid(db_file):
    """
    This was more complex than a regular fetch... hard coded what I needed in here, which is a dictionary with the
    metadata item GUIDs as keys and lists of classes of file locations and relevant info: size/duration/hash.
    """

    sql_cmd = 'SELECT ' \
              '\nmetadata_items.guid as "GUID",' \
              '\nmedia_parts.file as "File Location",' \
              '\nmedia_parts.size as "Size",' \
              '\nmedia_parts.duration as "Duration",' \
              '\nmedia_parts.hash as "Hash"' \
              '\nFROM media_items' \
              '\nINNER JOIN metadata_items ON media_items.metadata_item_id=metadata_items.id' \
              '\nINNER JOIN media_parts ON media_parts.media_item_id=media_items.id' \
              '\nINNER JOIN section_locations ON media_items.section_location_id = section_locations.id'

    output_line_lst = sqlWrapper.exec_sql_command(db_file, sql_cmd)

    guid_dict = {}

    for line in output_line_lst:
        if line[0] is not None:
            if line[0] not in guid_dict.keys():
                guid_dict[line[0]] = [{'File Location': line[1], 'Size': line[2], 'Duration': line[3], 'Hash': line[4]}]
            else:
                current_value = guid_dict[line[0]]
                current_value.append({'File Location': line[1], 'Size': line[2], 'Duration': line[3], 'Hash': line[4]})
                guid_dict[line[0]] = current_value

    return guid_dict


class TVSeries:
    def __init__(self, id):
        pass


class MetadataItem:
    def __init__(self, metadata_item):
        self.title = metadata_item['title']
        self.year = metadata_item['year']
        self.library_section_id = metadata_item['library_section_id']
        self.hash = metadata_item['hash']
        self.guid = metadata_item['guid']
        self.media_part = None
        self.tv_series_title = None
        self.tv_series_guid = None
        self.tv_series_season_int = None
        self.tv_series_episode_int = None


def get_plex_db_total_duration_days(db_file):
    sql_cmd = 'SELECT SUM(duration)/1000/60/60/24 from media_items;'
    result = sqlWrapper.exec_sql_command(db_file, sql_cmd)
    return result[0][0]


def get_movies_library_section_ids(db_file):

    # Get List of Library_Sections which are Movie Libraries
    library_section_movies_lst = get_plex_db_table_library_sections(db_file, 'Movies')
    # Get List of ID for those
    movie_section_id_lst = []
    for lib_section in library_section_movies_lst:
        movie_section_id_lst.append(lib_section['id'])

    return movie_section_id_lst


def get_metadata_item_cls_lst(db_file, filter_type=None):

    # List that will get populated with metadata classes
    metadata_cls_lst = []

    # Get list of metadata items
    metadata_lst = get_plex_db_table_metadata_items(db_file, filter_type)

    # If the filter type is episodes, we will need to fetch specific additional information contained
    # in tv series and seasons
    if filter_type == 'Episodes':
        # Additionally, Fetch Seasons
        metadata_seasons_lst = get_plex_db_table_metadata_items(db_file, 'Seasons')  # Get list of seasons
        metadata_seasons_dict = {}
        for item in metadata_seasons_lst:
            metadata_seasons_dict[item['id']] = item

        # Additionally, Fetch TV Series
        metadata_series_lst = get_plex_db_table_metadata_items(db_file, 'TV Series')  # Get list of TV Series
        metadata_series_dict = {}
        for item in metadata_series_lst:
            metadata_series_dict[item['id']] = item

    # Get list of media parts (media files), so we can assign them with the metadata
    guid_media_part_dict = get_plex_db_table_media_parts_with_guid(db_file)

    # Create metadata classes for rows
    for row in metadata_lst:
        metadata_cls = MetadataItem(row)
        metadata_cls.media_part = guid_media_part_dict[metadata_cls.guid]

        # If it was an episode, need to get the additional info through
        if filter_type == 'Episodes':

            season_user_thumb_url = metadata_seasons_dict[row['parent_id']]['user_thumb_url']  # TODO: Will need to clean for answer
            show_id = metadata_seasons_dict[row['parent_id']]['parent_id']
            tv_series_title = metadata_series_dict[show_id]['title']
            tv_series_guid = metadata_series_dict[show_id]['guid']
            episode_count = row['user_thumb_url']  # TODO: Will need to clean for answer

            metadata_cls.tv_series_title = None
            metadata_cls.tv_series_guid = None
            metadata_cls.tv_series_season_int = None
            metadata_cls.tv_series_episode_int = None

        metadata_cls_lst.append(metadata_cls)

    return metadata_cls_lst


def diff_metadata_item_cls_lsts_by_guid(metadata_item_cls_lst_01, metadata_item_cls_lst_02, hash_check=False):
    """
    Returns a dictionary with differences between 2 (two) metadata item class lists.
    Return dict has four keys: Match, Only in 1, Only in 2.
                               Match value(s): [[x_cls in 1, x_cls in 2], [..., ...], ...]
                               Only in 1 value(s): [x_cls_01, x_cls_02, x_cls_03, ...]
                               Only in 2 value(s): [x_cls_01, x_cls_02, x_cls_03, ...]
    """

    match_cls_lst = []
    only_in_01_cls_lst = []
    only_in_02_cls_lst = []

    # Gather lists of GUIDs to Compare
    md_items_01_guid_dict = {}
    for metadata_item_cls in metadata_item_cls_lst_01:
        md_items_01_guid_dict[metadata_item_cls.guid] = metadata_item_cls
    md_items_02_guid_dict = {}
    for metadata_item_cls in metadata_item_cls_lst_02:
        md_items_02_guid_dict[metadata_item_cls.guid] = metadata_item_cls
    md_items_02_matched_lst = []

    # Use GUID to compare (for now, but need to elaborate will arise)
    for metadata_item_cls in metadata_item_cls_lst_01:
        if metadata_item_cls.guid in md_items_02_guid_dict.keys():
            if not hash_check:
                match_cls_lst.append([metadata_item_cls, md_items_02_guid_dict[metadata_item_cls.guid]])
                md_items_02_matched_lst.append(md_items_02_guid_dict[metadata_item_cls.guid])
            else:
                hash_check_succeed = False
                metadata_item_hash_lst_01 = []
                for item in metadata_item_cls.media_part:
                    metadata_item_hash_lst_01.append(item['Hash'])
                for item in md_items_02_guid_dict[metadata_item_cls.guid].media_part:
                    if item['Hash'] in metadata_item_hash_lst_01:
                        hash_check_succeed = True
                if hash_check_succeed:
                    match_cls_lst.append([metadata_item_cls, md_items_02_guid_dict[metadata_item_cls.guid]])
                    md_items_02_matched_lst.append(md_items_02_guid_dict[metadata_item_cls.guid])
                else:
                    only_in_01_cls_lst.append(metadata_item_cls)
        else:
            only_in_01_cls_lst.append(metadata_item_cls)

    for metadata_item_cls in metadata_item_cls_lst_02:
        if metadata_item_cls not in md_items_02_matched_lst:
            only_in_02_cls_lst.append(metadata_item_cls)

    # Create return dictionary
    return_dict = {}
    return_dict['Match'] = match_cls_lst
    return_dict['Only in 1'] = only_in_01_cls_lst
    return_dict['Only in 2'] = only_in_02_cls_lst

    return return_dict


def diff_metadata_item_cls_lsts_by_info(metadata_item_cls_lst_01, metadata_item_cls_lst_02, hash_check=False):
    """
    Returns a dictionary with differences between 2 (two) metadata item class lists.
    Return dict has four keys: Match, Only in 1, Only in 2.
                               Match value(s): [[x_cls in 1, x_cls in 2], [..., ...], ...]
                               Only in 1 value(s): [x_cls_01, x_cls_02, x_cls_03, ...]
                               Only in 2 value(s): [x_cls_01, x_cls_02, x_cls_03, ...]
    """

    match_cls_lst = []
    only_in_01_cls_lst = []
    only_in_02_cls_lst = []

    # Figure out match


    # Create return dictionary
    return_dict = {}
    return_dict['Match'] = match_cls_lst
    return_dict['Only in 1'] = only_in_01_cls_lst
    return_dict['Only in 2'] = only_in_02_cls_lst

    return return_dict


def diff_media_type(db_file_01, db_file_02, filter_type, hash_check=False, print_result=False, print_detailed=False):
    """
    Returns a dictionary (see method diff_metadata_item_cls_lsts)
    :param db_file_01: Path to the database file to diff (left)
    :type db_file_01: str
    :param db_file_02: Path to the database file to diff (right)
    :type db_file_02: st
    :param filter_type: Type of Library to filter for ('Movies', 'Episodes', 'Other Videos', 'Photo' or 'Music')
    :param filter_type: str
    :param print_result: Whether to print results or not (as debug)
    :type print_result: bool
    """
    print('\nDiff media items of type {filter_type} between PLEX database files')
    print('Database File #01: ' + db_file_01)
    print('Database File #02: ' + db_file_02)

    # Gather List of Metadata Items (DB 1)
    metadata_items_cls_lst_db_01 = get_metadata_item_cls_lst(db_file_01, filter_type)

    # Gather List of Metadata Items (DB 2)
    metadata_items_cls_lst_db_02 = get_metadata_item_cls_lst(db_file_02, filter_type)

    # Diff is performed differently depending on media type!
    if filter_type == 'Movies':
        # Can proceed with a simple GUID compare because all libraries seem to be using the new PLEX movie agent
        diff_results = diff_metadata_item_cls_lsts_by_guid(metadata_items_cls_lst_db_01, metadata_items_cls_lst_db_02, hash_check=hash_check)
    elif filter_type == 'Episodes':
        # Need to proceed with a more complex compare because libraries on either side could be using the new TV Series Agent or THETVDB
        # Therefore, the GUID might not match and more advanced comparison must be done
        diff_results = diff_metadata_items_cls_lsts_by_info(metadata_items_cls_lst_db_01, metadata_items_cls_lst_db_02, hash_check=hash_check)
    else:
        pass
        # TODO: Account for this possibility

    match_count = len(diff_results['Match'])
    only_left_count = len(diff_results['Only in 1'])
    only_right_count = len(diff_results['Only in 2'])
    total_count = match_count + only_left_count + only_right_count

    if print_result:
        print('\nMetadata Item Matches ({match_count}/{total_count}): '.format(match_count=match_count, total_count=total_count))
        if print_detailed:
            for item in diff_results['Match']:
                print(' - {title} ({year})'.format(title=item[0].title, year=str(item[0].year)))

        print('\nMetadata Items missing from Database File #01: ' + db_file_01 + ' ({only_right_count}/{total_count})'.format(only_right_count=only_right_count, total_count=total_count))
        if print_detailed:
            for item in diff_results['Only in 2']:
                print(' - {title} ({year})'.format(title=item.title, year=str(item.year)))

        print('\nMetadata Items missing from Database File #02: ' + db_file_02 + ' ({only_left_count}/{total_count})'.format(only_left_count=only_left_count, total_count=total_count))
        if print_detailed:
            for item in diff_results['Only in 1']:
                print(' - {title} ({year})'.format(title=item.title, year=str(item.year)))

        print('Total count was: ' + str(total_count))

    return diff_results


def test_script():
    # db_file = 'C:\\Users\\marca\\Yagi Dropbox\\Marc-Andre Voyer\\PLEX-LibraryDatabase\\com.plexapp.plugins.library-marc.db'
    db_file_01 = '/Users/marca/Yagi Dropbox/Marc-Andre Voyer/PLEX-LibraryDatabase/com.plexapp.plugins.library-marc.db'
    db_file_02 = '/Users/marca/Yagi Dropbox/Marc-Andre Voyer/PLEX-LibraryDatabase/com.plexapp.plugins.library-phil.db'
    print('Analyzing PLEX Database File: ' + db_file_01)
    print('Total days of playtime = ' + str(get_plex_db_total_duration_days(db_file_01)))

    diff_media_type(db_file_01, db_file_02, filter_type='Movies', hash_check=False, print_result=True, print_detailed=False)

    diff_media_type(db_file_01, db_file_02, filter_type='Episodes', hash_check=False, print_result=True, print_detailed=False)



    # # long painful file hash, temporary
    # metadata_items_cls_lst_db_01 = get_metadata_item_cls_lst(db_file_01, 'Episodes')
    # metadata_items_cls_lst_db_02 = get_metadata_item_cls_lst(db_file_02, 'Episodes')
    # md_lst_hsh_lst_01 = []
    # md_lst_hsh_dict = {}
    #
    # item_01_cnt = 0
    # item_01_size = 0
    # for md_item in metadata_items_cls_lst_db_01:
    #     md_lst_hsh_lst_01.append(md_item.media_part[0]['Hash'])
    #     item_01_cnt += 1
    #     item_01_size += md_item.media_part[0]['Size']
    #
    #
    # match_cnt = 0
    # match_size = 0
    # no_match_cnt = 0
    # no_match_cnt_size = 0
    # for md_item in metadata_items_cls_lst_db_02:
    #     if md_item.media_part[0]['Hash'] in md_lst_hsh_lst_01:
    #         match_cnt += 1
    #         match_size += md_item.media_part[0]['Size']
    #     else:
    #         no_match_cnt += 1
    #         no_match_cnt_size += md_item.media_part[0]['Size']
    #
    # print('hash match results (quick)')
    # print(str(match_cnt) + '/' + str(no_match_cnt + item_01_cnt))
    # print(str(match_size) + '/' + str(no_match_cnt_size + item_01_size))
    # print('done')



    print('CALCULATING SERIES HASH LIST')

    # # Print List of Movies
    # for movie_cls in movie_cls_lst:
    #     print(movie_cls.name)



    # # Get Library Sections
    # table_library_sections = get_plex_db_table_media_parts(db_file)
    #
    # for row in table_library_sections:
    #     print(row)

    # # Get Table Media Items
    # table_media_items = get_plex_db_table_media_items(db_file)
    #
    # # Print Rows
    # for row in table_media_items:
    #     print(row)
    #
    # print('DONE!')
    # time.sleep(0.2)
    #
    # # Get Table Metadata Items
    # metadata_items = get_plex_db_table_metadata_items(db_file)
    #
    # for row in metadata_items:
    #     print(row)
