
> Current branch's todo item.

## Base

- [ ] Logging

## Source

- [x] Run collect intervally. 
  Each source can has their own interval.
- [x] Collected data will be organized later by running a background task for each data item using `organize` of its resolver.
- [ ] Collect is an active way to gather data. Source should be able to configure webhooks or other ways to passively gathering data. Source can done this in `start` method which will be called once the application starts.

## Resolver

- [ ] Standard of auto organization

## Extension
- [ ] Run `pdm install` to install dependencies the extension required when install or upgrade an extension.
- [ ] Create `data/extensions/<ext_id>/` folder for extension to locally store its data.
- [x] Add lifespan management: start and close.

### Twitter

- [x] Introduce a unified interface for fetching bookmarks, user and other stuff from Twitter.
  Current `auth.py` will be a kind of backend: `OfficialAPIBackend`.
  And we are going to introduce `twikit` backend.
  Only one backend can be enabled, config it at `config.backend`.
- [ ] Remove medias link in text
- [x] Add twikit exception handling
- [x] Close APIClient when close the application.
- [ ] Twikit get_tweet_id and _get_more_replies has a bug: last item of entries does not has `itemContent` in `content`, should directly read `value` from `content`
  Follow up this [PR](https://github.com/d60/twikit/pull/377) for solving this issue.