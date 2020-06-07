from collections import namedtuple

MusicState = namedtuple(
    "MusicState",
    ["group_index", "group_name", "track_list_index", "track_list_name", "master_volume", "track_list_volume"],
)
