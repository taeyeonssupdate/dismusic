from typing import Union

from wavelink import SoundCloudTrack, YouTubeMusicTrack, YouTubeTrack, YouTubePlaylist
from wavelink.ext.spotify import SpotifyTrack

Provider = Union[YouTubeTrack, YouTubeMusicTrack, SoundCloudTrack, SpotifyTrack, YouTubePlaylist]
