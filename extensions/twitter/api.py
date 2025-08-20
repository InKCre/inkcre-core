
import abc
import asyncio
import base64
import datetime
import os
import re
import typing
import secrets
import aiohttp
import fastapi
import sqlmodel
import twikit
import twikit.media
import urllib.parse
from typing import Optional as Opt
from dd import dd
from app.utils.base import AIOHTTP_CONNECTOR_GETTER
from app.utils.datetime_ import get_timestamp
from .schema import Tweet, TweetPhoto, TweetVideo, VideoVariant
from . import Extension


class TwitterAPIResult(sqlmodel.SQLModel):
    next_page: Opt[str] = None
    previous_page: Opt[str] = None
    tweets: tuple[Tweet, ...] = ()


class TwitterAPI(abc.ABC):
    """Twitter API client.

    Should be singleton.
    """

    SINGLETON: Opt["TwitterAPI"] = None

    @classmethod
    def new(cls, api_router: Opt[fastapi.APIRouter] = None) -> "TwitterAPI":
        """Create an instance of the Twitter API client.
        
        Use `config.backend` to determine which backend to use.
        """
        if cls.SINGLETON is not None:
            return cls.SINGLETON
        else:
            backend_type = Extension.config.backend
            if backend_type == "official":
                cls.SINGLETON = OfficialAPI(
                    client_id=Extension.config.client_id,
                    client_secret=Extension.config.client_secret
                )
                if api_router:
                    api_router.get("/auth/authorize")(cls.SINGLETON.get_oauth_authorize_url)
                    api_router.get("/auth/callback")(cls.SINGLETON.handle_oauth_callback)
                else:
                    # log warning
                    pass
            elif backend_type == "twikit":
                cls.SINGLETON = TwikitAPI(
                    email=Extension.config.email,
                    username=Extension.config.username,
                    password=Extension.config.password,
                    totp_secret=Extension.config.totp_secret,
                    language=Extension.config.api_language,
                    proxy=Extension.config.proxy,
                )
            else:
                raise ValueError(f"Unknown backend type: {backend_type}")
            
            return cls.SINGLETON
        
    async def close(self):
        ...
        
    @property
    @abc.abstractmethod
    def user_handle(self) -> str:
        ...

    @property
    @abc.abstractmethod
    def user_id(self) -> str:
        ...

    @abc.abstractmethod
    async def get_bookmarks(
        self, max_results: int = 20, page: Opt[str] = None
    ) -> TwitterAPIResult:
        ...

    @abc.abstractmethod
    async def get_tweets(
        self, query: str, max_results: int = 20, page: Opt[str] = None
    ) -> TwitterAPIResult:
        ...

    @abc.abstractmethod
    async def get_replies(
        self, *conversation_ids: str, from_: Opt[str] = None,
        max_results: int = 20
    ) -> TwitterAPIResult:
        ...


class OfficialAPI(TwitterAPI):
    """Official Twitter API client.
    """

    state = None
    challenge = None
    request_records: dict[str, tuple[int, datetime.datetime]] = {}
    """How many requests made to each endpoint for last 15 mins.
    """
    rate_limit_reset: dict[str, int] = {}
    """When the rate limit for each endpoint will reset.
    """

    def __init__(self, client_id: str, client_secret: str):
        self.__client_id = client_id
        self.__client_secret = client_secret
        self.__access_token: Opt[str] = None
        self.__refresh_token: Opt[str] = None
        self.__user_id: Opt[str] = None
        self.__user_handle: Opt[str] = None

    @property
    def user_handle(self) -> str:
        if self.__user_handle is None:
            raise ValueError("User handle is not set. Please authorize first.")
        return self.__user_handle
    
    @property
    def user_id(self) -> str:
        if self.__user_id is None:
            raise ValueError("User ID is not set. Please authorize first.")
        return self.__user_id

    async def _request(
        self, 
        method: str, endpoint: str, 
        path_params: Opt[dict] = None,
        query: Opt[dict] = None, body: Opt[dict] = None,
        retried: int = 0
    ) -> dict:
        """Make a request to the Twitter API.

        :param method: HTTP method (GET, POST, etc.)
        :param endpoint: API endpoint (e.g., "/users/me")
            Must start with a slash ("/").
            Use "{variable}" to mark path parameters.
        :param path_params: List of path parameters to format into the endpoint
        :param query: Query parameters as a dictionary
        :param body: Request body as a dictionary (for POST/PUT requests)
        
        - Auto authorization header
        - Auto refresh access token
        - Rate limit
          - Failed requests also count
        - TODO Monthly limit  
        - Error handling
        - Resopnse body parsing
        """
        if not self.__access_token:
            # TODO raise Unauthorized
            raise ValueError("Access token is not set. Please authorize first.")
        
        endpoint_with_params = endpoint.format(**path_params) if path_params else endpoint
        headers = {
            "Authorization": f"Bearer {self.__access_token}",
        }

        rate_limit_reset_at = self.rate_limit_reset.get(endpoint)
        if rate_limit_reset_at:
            await asyncio.sleep((rate_limit_reset_at - get_timestamp()) + 5)
            del self.request_records[endpoint]

        # request_record = cls.request_records.get(endpoint)
        # if request_record:
        #     last_request_count, last_15m_start_at = request_record
        #     if last_15m_start_at + datetime.timedelta(minutes=15) < datetime.datetime.now():
        #         del cls.request_records[endpoint]
        #     else:
        #         if last_request_count >= Extension.config.api_rate_limit", {}).get(endpoint, 1):
        #             # wait until the rate limit resets
        #             await asyncio.sleep((
        #                 last_15m_start_at + datetime.timedelta(minutes=15)
        #                 - datetime.datetime.now()
        #             ).total_seconds() + 5) # add a buffer of 5 seconds
        #             # reset
        #             cls.request_records[endpoint] = (0, datetime.datetime.now())
        # else:
        #     last_request_count, last_15m_start_at = 0, datetime.datetime.now()

        async with aiohttp.ClientSession(connector=AIOHTTP_CONNECTOR_GETTER()) as session:
            async with session.request(
                method, f"https://api.x.com/2{endpoint_with_params}", params=query, headers=headers, 
            ) as resp:
                if resp.status == 429:
                    x_rate_limit_reset = resp.headers.get("x-rate-limit-reset")
                    if x_rate_limit_reset:
                        self.rate_limit_reset[endpoint] = int(x_rate_limit_reset)
                    
                    # # Rate limit exceeded but not expected, set request count to max
                    # # and request again when rate limit reset
                    # cls.request_records[endpoint] = (
                    #     Extension.config.api_rate_limit", {}).get(endpoint, 1),
                    #     datetime.datetime.now()
                    # )

                    if retried < 3:
                        return await self._request(
                            method, endpoint, path_params, query, body, retried + 1
                        )
                    else:
                        raise TooManyRequests  # TODO

                resp.raise_for_status()
                return await resp.json()

    async def get_user(self) -> tuple[str, str]:
        """Get the user info the token represents and store to state.

        :returns: (user ID, user handle)
        """
        user_info = await self._request("GET", "/users/me")
        user_id = user_info.get("data", {}).get("id")
        if not user_id:
            raise ValueError("Failed to get user ID from Twitter API.")
        user_handle = user_info.get("data", {}).get("username")
        if not user_handle:
            raise ValueError("Failed to get user handle from Twitter API.")
        
        # Extension.state["user_id"] = user_id
        # Extension.state["user_handle"] = user_handle
        self.__user_id = user_id
        self.__user_handle = user_handle
        return user_id, user_handle
    
    def _resolve_tweets(
        self, raw_tweets: list[dict], includes: dict[str, list[dict]]
    ) -> list[Tweet]:
        include_medias = includes.get("media", ())

        tweets: list[Tweet] = []
        for tweet in raw_tweets:
            tweet = dd(tweet)
            tweet_id = tweet.id()

            # resolve medias
            media_keys = tweet._.attachments.media_keys() or ()
            photos: list[TweetPhoto] = []
            videos: list[TweetVideo] = []
            for media_key in media_keys:
                for include_media in include_medias:
                    include_media = dd(include_media)
                    if include_media._.media_key() == media_key:
                        media_type = include_media._.type()
                        if media_type == "video":
                            videos.append(TweetVideo(
                                id=media_key,
                                variants=tuple(
                                    VideoVariant(**variant) 
                                    for variant in (include_media._.variants() or ())
                                )
                            ))
                        elif media_type == "photo":
                            photos.append(TweetPhoto(
                                id=media_key,
                                url=include_media.url(lambda x: x or ""),
                            ))
                        else:
                            # TODO log warning for unsupported media type
                            pass
                        break
                        
            # resolve conversation ID
            conversation_id = tweet._.conversation_id()
            if conversation_id == tweet_id:
                conversation_id = None

            # resolve url entities
            urls: list[str] = []
            for entity in (tweet._.entities.urls() or []):
                url = entity.get("expanded_url")
                if url:
                    urls.append(url)

            # resolve text
            tweet_text = tweet.text()
            tweet_text = re.sub(r'^(?:@\w+\s*)+', '', tweet_text)
            
            tweets.append(Tweet(
                id=tweet_id,
                lang=tweet.lang(),
                text=tweet_text,
                conversation_id=conversation_id,
                photos=tuple(photos),
                videos=tuple(videos),
                urls=tuple(urls),
            ))

        return tweets
    
    async def get_bookmarks(self, max_results: int = 20, page: str | None = None) -> TwitterAPIResult:
        """Get user bookmarks.
        
        Rate limit: 
        - Free: 1 req per 15 minutes
        - Basic: 5 req per 15 minutes
        - Pro: 50 req per 15 minutes
        """
        bookmarks_query = {
            "max_results": max_results,
            "tweet.fields": "attachments,entities,lang,conversation_id",
            "media.fields": "alt_text,media_key,url,type",
            "expansions": "attachments.media_keys,attachments.media_source_tweet",
        }
        if page:
            bookmarks_query["pagination_token"] = page
        res = await self._request(
            "GET", "/users/{id}/bookmarks",
            path_params={"id": self.__user_id},
            query=bookmarks_query
        )
        tweets = self._resolve_tweets(res.get("data", []), res.get("includes", {}))
        return TwitterAPIResult(
            next_page=res.get("meta", {}).get("next_token"),
            previous_page=res.get("meta", {}).get("previous_token"),
            tweets=tuple(tweets)
        )
    
    async def get_tweets(
        self, query: str, max_results: int = 20, page: str | None = None
    ) -> TwitterAPIResult:
        res = await self._request(
            "GET", "/tweets/search/recent",
            query={
                "query": query,
                "max_results": max_results,
                "tweet.fields": "attachments,entities,lang,conversation_id",
                "media.fields": "alt_text,media_key,url,type",
                "expansions": "attachments.media_keys,attachments.media_source_tweet",
            }
        )
        tweets = self._resolve_tweets(res.get("data", []), res.get("includes", {}))
        return TwitterAPIResult(
            next_page=res.get("meta", {}).get("next_token"),
            previous_page=res.get("meta", {}).get("previous_token"),
            tweets=tuple(tweets)
        )
    
    async def get_replies(
        self, *conversation_ids: str, from_: str | None = None,
        max_results: int = 20
    ) -> TwitterAPIResult:
        # TODO add query lenth limit auto adapt
        res = await self.get_tweets(
            query=f"from:{from_} ({" OR ".join(map(lambda x: f"conversation_id:{x}", conversation_ids))})",
            max_results=max_results,
        )
        return res

    @staticmethod
    def _get_oauth_redirect_url():
        return os.getenv("API_BASE_URL", "") + "/twitter/auth/callback"
    
    def get_oauth_authorize_url(self) -> str:

        BASE_URL = "https://x.com/i/oauth2/authorize"
        REDIRECT_URL = self._get_oauth_redirect_url()
        CLIENT_ID = self.__client_id

        scope = " ".join([
            "tweet.read",
            "users.read",
            "bookmark.read",
            "bookmark.write",
            "offline.access",
        ])
        self.state = secrets.token_urlsafe(16)  # A random string to prevent CSRF attacks
        self.code_challenge = secrets.token_urlsafe(32)  # Code challenge for PKCE

        params = {
            "response_type": "code",
            "client_id": CLIENT_ID,
            "state": self.state,
            "code_challenge": self.code_challenge,
            "code_challenge_method": "plain",
            "redirect_uri": REDIRECT_URL,
            "scope": scope,
        }

        return BASE_URL + "?" + urllib.parse.urlencode(params)

    async def handle_oauth_callback(self, code: str, state: str):
        """Handle the OAuth2 callback from Twitter.

        Exchange the authorization code for an access token.
        """
        # verify state
        if state != self.state:
            raise ValueError("Invalid state parameter")

        TOKEN_URL = "https://api.x.com/2/oauth2/token"
        CLIENT_ID = self.__client_id
        CLIENT_SECRET = self.__client_secret

        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self._get_oauth_redirect_url(),
            "client_id": CLIENT_ID,
            "code_verifier": self.code_challenge, 
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {
                base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
            }"
        }

        async with aiohttp.ClientSession(connector=AIOHTTP_CONNECTOR_GETTER()) as session:
            async with session.post(TOKEN_URL, data=data, headers=headers) as resp:
                resp.raise_for_status()
                resp_body = await resp.json()
                access_token = resp_body.get("access_token")
                refresh_token = resp_body.get("refresh_token")
                if not access_token or not refresh_token:
                    raise ValueError("Failed to obtain access token or refresh token")
                # Extension.state["access_token"] = access_token
                # Extension.state["refresh_token"] = refresh_token
                self.__access_token = access_token
                self.__refresh_token = refresh_token

                self.state = None 
                self.challenge = None

                # Get user info and store to state
                await self.get_user()

                return resp_body
    
    async def refresh_access_token(self, refresh_token: str) -> str:
        """Get a new access token using the refresh token.

        Docs https://docs.x.com/fundamentals/authentication/oauth-2-0/authorization-code#refresh-tokens
        """
        TOKEN_URL = "https://api.x.com/2/oauth2/token"
        CLIENT_ID = self.__client_id

        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": CLIENT_ID,
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }

        async with aiohttp.ClientSession(connector=AIOHTTP_CONNECTOR_GETTER()) as session:
            async with session.post(TOKEN_URL, data=data, headers=headers) as resp:
                resp.raise_for_status()
                token_response = await resp.json()
        return token_response


class TwikitAPI(TwitterAPI):
    """Twikit API client.
    """

    def __init__(
        self, 
        email: str, username: str, 
        password: str, totp_secret: Opt[str] = None,
        language: Opt[str] = None, proxy: Opt[str] = None
    ):
        """
        :param language: The language code to use in API requests.
            Keep the same with your daily use of Twitter.
        """
        if not language:
            language = "en-US"
        self._client = twikit.Client(language=language, proxy=proxy)
        self._email = email
        self._username = username
        self._password = password
        self._totp_secret = totp_secret

    async def close(self):
        self._client.save_cookies("data/extensions/twitter/twikit_cookies.json")

    @property
    def user_handle(self) -> str:
        return self._username
    
    @property
    def user_id(self) -> str:
        if not self._client._user_id:
            raise ValueError("User ID is not set. Please login first.")
        return self._client._user_id    

    async def _login(self):
        await self._client.login(
            auth_info_1=self._email, auth_info_2=self._username, 
            password=self._password, totp_secret=self._totp_secret,
            cookies_file="data/extensions/twitter/twikit_cookies.json"
        )

    @staticmethod
    def _resolve_tweet(tweet: twikit.Tweet) -> Tweet:
        # resolve medias
        photos: list[TweetPhoto] = []
        videos: list[TweetVideo] = []
        for media in tweet.media:
            if isinstance(media, twikit.media.Photo):
                photos.append(TweetPhoto(
                    id=media.id,
                    url=media.media_url
                ))
            elif isinstance(media, twikit.media.Video):
                videos.append(TweetVideo(
                    id=media.id,
                    variants=tuple(
                        VideoVariant(
                            bitrate=variant.bitrate,
                            content_type=variant.content_type,
                            url=variant.url or "",
                        ) for variant in media.streams
                    )
                ))

        # resolve urls
        urls: list[str] = []
        for i in typing.cast(dict, tweet.urls):
            url = i["expanded_url"]
            if url:
                urls.append(url)
        
        tweet_text = re.sub(r'^(?:@\w+\s*)+', '', tweet.text)

        return Tweet(
            id=int(tweet.id),
            lang=tweet.lang,
            text=tweet_text,
            conversation_id=int(tweet.in_reply_to) if tweet.in_reply_to else None,
            photos=tuple(photos),
            videos=tuple(videos),
            urls=tuple()
        )

    @classmethod
    def _resolve_tweets(cls, result: twikit.utils.Result[twikit.Tweet]) -> tuple[Tweet, ...]:
        return tuple(
            cls._resolve_tweet(tweet)
            for tweet in result
        )

    async def get_bookmarks(self, max_results: int = 20, page: str | None = None) -> TwitterAPIResult:
        if not self._client._user_id:
            await self._login()
        res = await self._client.get_bookmarks(count=max_results, cursor=page)
        return TwitterAPIResult(
            next_page=res.next_cursor,
            previous_page=res.previous_cursor,
            tweets=tuple(self._resolve_tweets(res))
        )
    
    async def get_tweets(
        self, 
        query: str, max_results: int = 20, page: str | None = None,
        tried: int = 0
    ) -> TwitterAPIResult:
        if not self._client._user_id:
            await self._login()
        try:
            res = await self._client.search_tweet(
                query=query, product="Latest", count=max_results, cursor=page
            )
        except twikit.errors.NotFound:
            if tried < 3:
                await asyncio.sleep(3) 
                return await self.get_tweets(query, max_results, page, tried + 1)
            else:
                return TwitterAPIResult()
        else:
            return TwitterAPIResult(
                next_page=res.next_cursor,
                previous_page=res.previous_cursor,
                tweets=tuple(self._resolve_tweets(res))
            )
    
    async def _get_a_reply_of(
        self, from_: str, replies: twikit.utils.Result[twikit.Tweet]
    ) -> Tweet | None:
        if len(replies) == 0:
            return None
        for reply in replies:
            if reply.user.screen_name == from_:
                return self._resolve_tweet(reply)
        else:
            await asyncio.sleep(5)  # avoid rate limit
            replies = await replies.next()
            return await self._get_a_reply_of(from_, replies)

    async def get_replies(
        self, *conversation_ids: str, from_: str | None = None, max_results: int = 20
    ) -> TwitterAPIResult:
        res_tweets: list[Tweet] = []
        for cid in conversation_ids:
            await asyncio.sleep(3)  # avoid rate limit
            try:
                tweet = await self._client.get_tweet_by_id(cid)
            except twikit.errors.TweetNotAvailable:
                # TODO log warning
                continue
            else:
                replies = tweet.replies
                if not replies:
                    continue
                else:
                    if from_:
                        the_reply = await self._get_a_reply_of(from_, replies)
                        if the_reply:
                            res_tweets.append(the_reply)
                    else:
                        res_tweets.extend(self._resolve_tweets(replies))

        return TwitterAPIResult(tweets=tuple(res_tweets))
