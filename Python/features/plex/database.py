"""Read-only Plex database inspection, with optional columns across schema versions."""

from contextlib import closing
from pathlib import Path
import sqlite3

from .comparison import diff_metadata_item_cls_lsts_by_guid, diff_metadata_item_cls_lsts_by_info


def _connect(db_file):
    path = Path(db_file).resolve(strict=True)
    if not path.is_file():
        raise ValueError(f'Not a database file: {path}')
    return sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)


def _query(db_file, statement):
    with closing(_connect(db_file)) as connection:
        return connection.execute(statement).fetchall()


def _table(db_file, name, columns):
    # Table and column names come only from the fixed selectors in this module.
    with closing(_connect(db_file)) as connection:
        available = {row[1] for row in connection.execute(f'PRAGMA table_info("{name}")')}
        if not available:
            raise ValueError(f'Plex database has no {name} table.')
        required = {
            'metadata_items': {'id', 'metadata_type', 'parent_id', 'library_section_id'},
            'media_items': {'id', 'metadata_item_id', 'duration'},
            'media_parts': {'media_item_id', 'file'},
            'library_sections': {'id', 'section_type'},
        }[name]
        if missing := required - available:
            raise ValueError(f'Plex {name} is missing required columns: {sorted(missing)}')
        projection = ', '.join(f'"{column}"' if column in available else f'NULL AS "{column}"'
                               for column in columns)
        rows = connection.execute(f'SELECT {projection} FROM "{name}"').fetchall()
    return [dict(zip(columns, row), row_number=index) for index, row in enumerate(rows, 1)]


def get_plex_db_table_media_items(db_file):
    """
    Returns a list of the PLEX Media Items from its SQL Database (com.plexapp.plugins.library.db file).

    :param db_file: Path to the database file
    :type db_file: str
    """
    media_items_column_lst = [
        'id',
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
        'color_trc'
    ]

    return _table(db_file, 'media_items', media_items_column_lst)


def get_plex_db_table_metadata_items(db_file, filter_type=None):
    """
    Returns a list of the PLEX Metadata Items from its SQL Database (com.plexapp.plugins.library.db file).

    :param db_file: Path to the database file
    :type db_file: str
    :param filter_type: Type of metadata item to filter for
                        ('Movies', 'TV Series', 'Seasons', 'Episodes', 'Other Videos', 'Photo' or 'Music')
    :type filter_type: str
    """
    metadata_items_column_lst = [
        'id',
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
        'edition_title'
    ]

    row_lst = _table(db_file, 'metadata_items', metadata_items_column_lst)

    if filter_type is None:
        return row_lst

    types = {'Movies': 1, 'TV Series': 2, 'Seasons': 3, 'Episodes': 4, 'Music': 10}
    if filter_type == 'Other Videos':
        sections = {row['id'] for row in get_plex_db_table_library_sections(db_file, 'Other Videos')}
        return [row for row in row_lst if row['metadata_type'] == 1 and row['library_section_id'] in sections]
    if filter_type == 'Photo':
        raise NotImplementedError('Photo metadata filtering is not supported.')
    if filter_type not in types:
        raise ValueError(f'Unknown metadata filter: {filter_type}')
    rows = [row for row in row_lst if row['metadata_type'] == types[filter_type]]
    if filter_type == 'Movies':
        sections = set(get_movies_library_section_ids(db_file))
        rows = [row for row in rows if row['library_section_id'] in sections]
    return rows


def get_plex_db_table_library_sections(db_file, filter_type=None):
    """
    Returns a list of the PLEX Library Sections from its SQL Database (com.plexapp.plugins.library.db file).

    :param db_file: Path to the database file
    :type db_file: str
    :param filter_type: Type of Library to filter for ('Movies', 'Episodes', 'Other Videos', 'Photo' or 'Music')
    :type filter_type: str
    """
    library_sections_column_lst = [
        'id',
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
        'content_changed_at'
    ]

    row_lst = _table(db_file, 'library_sections', library_sections_column_lst)

    if filter_type is None:
        return row_lst

    if filter_type in ('Movies', 'Other Videos'):
        other = filter_type == 'Other Videos'
        return [row for row in row_lst if row['section_type'] == 1 and (row['language'] == 'xn') == other]
    types = {'Episodes': 2, 'TV Series': 2, 'Music': 8}
    if filter_type == 'Photo':
        raise NotImplementedError('Photo library filtering is not supported.')
    if filter_type not in types:
        raise ValueError(f'Unknown library filter: {filter_type}')
    return [row for row in row_lst if row['section_type'] == types[filter_type]]


def get_plex_db_table_media_parts(db_file):
    """
    Returns a list of the PLEX Media Parts from its SQL Database (com.plexapp.plugins.library.db file).

    :param db_file: Path to the database file
    :type db_file: str
    """
    media_parts_column_lst = [
        'id',
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
        'extra_data'
    ]

    return _table(db_file, 'media_parts', media_parts_column_lst)


def _parts_by_metadata_id(db_file):
    parts = {}
    for row in get_plex_db_table_media_parts(db_file):
        if row['deleted_at'] is None:
            parts.setdefault(row['media_item_id'], []).append({
                'File Location': row['file'], 'Size': row['size'],
                'Duration': row['duration'], 'Hash': row['hash']})
    result = {}
    for row in get_plex_db_table_media_items(db_file):
        if row['deleted_at'] is None:
            result.setdefault(row['metadata_item_id'], []).extend(parts.get(row['id'], []))
    return result


def get_plex_db_table_media_parts_with_guid(db_file):
    """Group active media parts by nonempty metadata GUID."""
    parts = _parts_by_metadata_id(db_file)
    result = {}
    for row in get_plex_db_table_metadata_items(db_file):
        if row['guid'] and row['deleted_at'] is None:
            result.setdefault(row['guid'], []).extend(parts.get(row['id'], []))
    return result


class MetadataItem:
    def __init__(self, metadata_item):
        self.title = metadata_item['title']
        self.year = metadata_item['year']
        self.library_section_id = metadata_item['library_section_id']
        self.hash = metadata_item['hash']
        self.guid = metadata_item['guid']
        self.media_part = []
        self.tv_series_title = None
        self.tv_series_guid = None
        self.tv_series_season_int = None
        self.tv_series_episode_int = None


def get_plex_db_total_duration_days(db_file):
    """Return fractional days, including zero for an empty database."""
    return _query(db_file, 'SELECT COALESCE(SUM(duration), 0)/86400000.0 FROM media_items')[0][0]


def get_movies_library_section_ids(db_file):
    return [row['id'] for row in get_plex_db_table_library_sections(db_file, 'Movies')]


def get_metadata_item_cls_lst(db_file, filter_type=None):
    rows = get_plex_db_table_metadata_items(db_file)
    active = {row['id']: row for row in rows if row['deleted_at'] is None}
    selected = rows if filter_type is None else get_plex_db_table_metadata_items(db_file, filter_type)
    parts = _parts_by_metadata_id(db_file)
    result = []
    # Plex stores season/episode numbering in the column named index.
    indices = {row['id']: row['index'] for row in _table(db_file, 'metadata_items', ['id', 'index'])} if filter_type == 'Episodes' else {}
    for row in selected:
        if row['deleted_at'] is not None:
            continue
        item = MetadataItem(row)
        item.media_part = parts.get(row['id'], [])
        if filter_type == 'Episodes':
            season = active.get(row['parent_id'])
            show = active.get(season['parent_id']) if season else None
            if season and show and season['metadata_type'] == 3 and show['metadata_type'] == 2:
                item.tv_series_title = show['title']
                item.tv_series_guid = show['guid']
                item.tv_series_season_int = indices.get(season['id'])
                item.tv_series_episode_int = indices.get(row['id'])
        result.append(item)
    return result


def diff_media_type(db_file_01, db_file_02, filter_type, hash_check=False, print_result=False, print_detailed=False):
    """
    Returns a dictionary containing differences between two Plex databases.

    :param db_file_01: Path to the database file to diff (left)
    :type db_file_01: str
    :param db_file_02: Path to the database file to diff (right)
    :type db_file_02: str
    :param filter_type: Type of Library to filter for ('Movies', 'Episodes', 'Other Videos', 'Photo' or 'Music')
    :type filter_type: str
    :param print_result: Whether to print results or not
    :type print_result: bool
    """
    print(f'\nDiff media items of type {filter_type} between PLEX database files')
    print('Database File #01: ' + str(db_file_01))
    print('Database File #02: ' + str(db_file_02))

    metadata_items_cls_lst_db_01 = get_metadata_item_cls_lst(db_file_01, filter_type)
    metadata_items_cls_lst_db_02 = get_metadata_item_cls_lst(db_file_02, filter_type)

    # Diff is performed differently depending on media type
    if filter_type == 'Movies':
        diff_results = diff_metadata_item_cls_lsts_by_guid(
            metadata_items_cls_lst_db_01,
            metadata_items_cls_lst_db_02,
            hash_check=hash_check
        )
    elif filter_type == 'Episodes':
        diff_results = diff_metadata_item_cls_lsts_by_info(
            metadata_items_cls_lst_db_01,
            metadata_items_cls_lst_db_02,
            hash_check=hash_check
        )
    else:
        raise NotImplementedError(f'Comparison is not supported for {filter_type}.')

    match_count = len(diff_results['Match'])
    only_left_count = len(diff_results['Only in 1'])
    only_right_count = len(diff_results['Only in 2'])
    total_count = match_count + only_left_count + only_right_count

    if print_result:
        print(f'\nMetadata Item Matches ({match_count}/{total_count}): ')

        if print_detailed:
            for item in diff_results['Match']:
                print(f' - {item[0].title} ({item[0].year})')

        print(f'\nMetadata Items missing from Database File #01: {db_file_01} ({only_right_count}/{total_count})')

        if print_detailed:
            for item in diff_results['Only in 2']:
                print(f' - {item.title} ({item.year})')

        print(f'\nMetadata Items missing from Database File #02: {db_file_02} ({only_left_count}/{total_count})')

        if print_detailed:
            for item in diff_results['Only in 1']:
                print(f' - {item.title} ({item.year})')

        print(f'Total count was: {total_count}')

    return diff_results


def test_script(db_file_01=None, db_file_02=None):
    """Compare selected database copies; no personal platform paths are assumed."""
    if db_file_01 is None or db_file_02 is None:
        from commonUtils.ui import pyside
        db_file_01, _ = pyside.QFileDialog.getOpenFileName(None, 'Select first Plex database')
        if not db_file_01:
            return None
        db_file_02, _ = pyside.QFileDialog.getOpenFileName(None, 'Select second Plex database')
        if not db_file_02:
            return None
    return {kind: diff_media_type(db_file_01, db_file_02, kind, print_result=True)
            for kind in ('Movies', 'Episodes')}
