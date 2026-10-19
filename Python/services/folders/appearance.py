"""Portable folder glyph geometry and lock colours shared by desktop and mobile."""

_folder_outline = ((12, 20), (3, 20), (2, 19), (2, 6), (3, 5), (9, 5), (11, 8), (21, 8), (22, 9), (22, 10))
_folder_lock = ((15, 16), (22, 16), (23, 17), (23, 21), (22, 22), (15, 22), (14, 21), (14, 17), (15, 16))
_folder_shackle = ((16, 16), (16, 13), (16.6, 11.6), (18, 11), (20, 11), (21.4, 11.6), (22, 13))
# A short pair of links keeps the chained state legible without covering the face.
_folder_chains = (
    ((4, 11), (5, 10), (6, 10), (9, 13), (9, 14), (8, 15), (7, 15), (4, 12), (4, 11)),
    ((7, 14), (8, 13), (9, 13), (12, 16), (12, 17), (11, 18), (10, 18), (7, 15), (7, 14)),
)
# Lift the whole arch clear of the body on the open side, rather than just
# removing a short closing stroke from the closed padlock.
_folder_open_shackle = ((16, 16), (16, 12), (16.6, 10.6), (18, 10), (20, 10), (21.4, 10.6), (22, 12))

FOLDER_PATHS = {
    'cloud': (((6, 18), (3, 17), (2, 14), (3, 11), (6, 10), (7, 6), (11, 4),
               (15, 5), (17, 9), (20, 10), (22, 13), (21, 17), (18, 18), (6, 18)),),
    'folder': (((2, 20), (22, 20), (22, 8), (11, 8), (9, 5), (2, 5), (2, 20)),),
    'folder_locked': (_folder_outline, *_folder_chains, _folder_lock, _folder_shackle + ((22, 16),)),
    'folder_unlocked': (_folder_outline, _folder_lock, _folder_open_shackle),
}
LOCK_LIGHT = {'folder_unlocked': '#175eab', 'folder_locked': '#a64b00'}
LOCK_DARK = {'folder_unlocked': '#86b9ff', 'folder_locked': '#ffb86b'}
