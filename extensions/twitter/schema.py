import sqlmodel
import typing
from typing import Optional as Opt
from .resolver import TweetResolver


TweetID: typing.TypeAlias = int
TweetMediaKey: typing.TypeAlias = str

class VideoVariant(sqlmodel.SQLModel):
    bitrate: Opt[int] = None
    content_type: Opt[str] = None
    """Content type of this video variant.
    
    None is video/mp4
    """
    url: str

class TweetVideo(sqlmodel.SQLModel):
    id: TweetMediaKey
    variants: tuple[VideoVariant, ...]

class TweetPhoto(sqlmodel.SQLModel):
    id: TweetMediaKey
    url: str
    alt_text: Opt[str] = None

class Tweet(sqlmodel.SQLModel):
    __resolver__ = TweetResolver

    id: TweetID
    lang: Opt[str] = None
    text: str
    conversation_id: Opt[TweetID] = None
    photos: tuple[TweetPhoto, ...] = ()
    videos: tuple[TweetVideo, ...] = ()
    urls: tuple[str, ...] = ()
