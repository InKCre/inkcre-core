"""Twitter Bookmark Source
"""

import asyncio
import typing
import json
from typing import Optional as Opt
from app.business.block import _create_block, _get_recent_blocks, _get_block
from app.business.relation import RelationManager
from app.business.source import SourceBase, CollectGeneratedTV
from app.schemas.block import BlockID, BlockModel
from .api import TwitterAPI
from .schema import Tweet, TweetID



class Source(SourceBase):
    """Twitter Bookmark as Source
    """

    API_BASE_URL = "https://api.x.com/2"
    
    async def _collect(  # type: ignore[override]  seems to be a bug of pyright
        self, full: bool = False, page: Opt[str] = None
    ) -> typing.AsyncGenerator[BlockModel, None]:
        """Collect all new bookmarks and its notes.

        :param page: Which page to collect.
        :param full: If True, collect until no more pages.

        What is new bookmarks?
        The tweets before the last collected tweet. The last collected tweet
        is the latest created_at tweet block.
        (Potential issue if bookmarks order changes)

        What is bookmark note?
        User can add a note to a bookmark by replying the bookmark tweet.

        Docs https://docs.x.com/x-api/bookmarks/get-bookmarks
        """
        RESULT_LIMIT = 40
        api_client = TwitterAPI.new()
        bookmarks_res = await api_client.get_bookmarks(page=page, max_results=RESULT_LIMIT)

        # find new tweets start point
        old_start_at = len(bookmarks_res.tweets)
        if not full:
            latest_tweet_blocks = _get_recent_blocks(num=1, resolver=Tweet.__resolver__.__rsotype__)
            if latest_tweet_blocks:
                latest_tweet = Tweet.model_validate_json(latest_tweet_blocks[0].content)
                old_start_at = next(
                    (
                        i 
                        for i, tweet in enumerate(bookmarks_res.tweets)
                        if tweet.id == latest_tweet.id
                    ), 
                    len(bookmarks_res.tweets)
                )

        for tweet in (
            bookmarks_res.tweets if full else
            reversed(bookmarks_res.tweets[:old_start_at])
        ): 
            yield BlockModel(
                resolver=Tweet.__resolver__.__rsotype__,
                content=tweet.model_dump_json(),
            )

        if full and bookmarks_res.next_page and bookmarks_res.next_page != page:
            await asyncio.sleep(10) 
            async for i in self._collect(page=bookmarks_res.next_page, full=full):
                yield i

    async def _organize(self, block_id: BlockID) -> None:
        block = _get_block(block_id)
        if not block:
            # TODO log error
            return
        bookmarked_tweet = Tweet.model_validate_json(block.content)
        api_client = TwitterAPI.new()

        # collect notes
        replies: tuple[Tweet, ...] = (await api_client.get_replies(
            str(bookmarked_tweet.id), from_=api_client.user_handle
        )).tweets
        for reply in replies:
            if not reply.conversation_id:
                # TODO log warning
                continue

            reply_block = _create_block(BlockModel(resolver="text", content=reply.text))
            RelationManager.create(
                from_=typing.cast(BlockID, block.id), 
                to_=typing.cast(BlockID, reply_block.id), 
                content="bookmarked for"
            )
