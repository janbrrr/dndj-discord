import pkg_resources

import requests


def is_latest_youtube_dl_version() -> bool:
    """
    Returns `False` if a new version of the 'youtube-dl' package is available.
    """
    result = requests.get("https://pypi.org/pypi/youtube_dl/json")
    latest_version = result.json()["info"]["version"]
    current_version = pkg_resources.get_distribution("youtube-dl").version
    return current_version == latest_version
