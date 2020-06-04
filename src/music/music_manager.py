from typing import Dict

from src.music.music_group import MusicGroup


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
