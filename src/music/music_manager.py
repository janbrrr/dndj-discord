import logging
from collections import namedtuple
from typing import Dict

from src.logging_config import stream_handler
from src.music.music_checker import MusicChecker
from src.music.music_group import MusicGroup

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(stream_handler)

_CurrentlyPlaying = namedtuple("_CurrentlyPlaying", ["group_index", "track_list_index"])
CurrentlyPlaying = namedtuple(
    "CurrentlyPlaying",
    ["group_index", "group_name", "track_list_index", "track_list_name", "master_volume", "track_list_volume"],
)


class MusicManager:
    def __init__(self, config: Dict):
        """
        Initializes a `MusicManager` instance.

        The `config` parameter is expected to be a dictionary with the following keys:
        - "volume": an integer between 0 (mute) and 100 (max)
        - "directory": the default directory to use if no directory is further specified (Optional)
        - "sort": whether to sort the groups alphabetically (Optional, default=True)
        - "groups": a list of configs for `MusicGroup` instances. See `MusicGroup` class for more information

        :param config: `dict`
        """
        self.volume = int(config["volume"])
        self.directory = config["directory"] if "directory" in config else None
        groups = [MusicGroup(group_config) for group_config in config["groups"]]
        if "sort" not in config or ("sort" in config and config["sort"]):
            groups = sorted(groups, key=lambda x: x.name)
        self.groups = tuple(groups)
        self._currently_playing = None
        MusicChecker().do_all_checks(self.groups, self.directory)

    def __eq__(self, other):
        if isinstance(other, MusicManager):
            attrs_are_the_same = self.volume == other.volume and self.directory == other.directory
            if not attrs_are_the_same:
                return False
            if len(self.groups) != len(other.groups):
                return False
            for my_group, other_group in zip(self.groups, other.groups):
                if my_group != other_group:
                    return False
            return True
        return False

    @property
    def currently_playing(self) -> CurrentlyPlaying:
        """
        Returns information about the music that is currently being played.
        Fields are `None` if nothing is being played.
        """
        if self._currently_playing is not None:
            group_index = self._currently_playing.group_index
            group = self.groups[group_index]
            track_list_index = self._currently_playing.track_list_index
            track_list = group.track_lists[track_list_index]
            return CurrentlyPlaying(
                group_index, group.name, track_list_index, track_list.name, self.volume, track_list.volume
            )
        return CurrentlyPlaying(None, None, None, None, self.volume, None)

    async def cancel(self):
        """
        If a track is currently being played, the replay will be cancelled.
        """
        logger.info("cancel()")

    async def play_track_list(self, request, group_index, track_list_index):
        """
        If a track list is already being played, it will be cancelled and the new track list will be played.
        """
        logger.info(f"play_track_list(group_index={group_index}, track_list_index={track_list_index})")

    async def set_master_volume(self, request, volume):
        """
        Sets the master volume for the music.
        """
        logger.info(f"set_master_volume(volume={volume})")

    async def set_track_list_volume(self, request, group_index, track_list_index, volume):
        """
        Sets the volume for a specific track list.

        :param request: the request that caused the action
        :param group_index: index of the group of the track list
        :param track_list_index: index of the track list within the group
        :param volume: value between 0 (mute) and 100 (max)
        """
        logger.info(
            f"set_track_list_volume(group_index={group_index}, track_list_index={track_list_index}, "
            f"volume={volume})"
        )
