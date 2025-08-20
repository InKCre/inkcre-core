
> Current branch's todo item.

## Source

- 

## Extension
- [ ] Run `pdm install` to install dependencies the extension required when install or upgrade an extension.
- [ ] Create `data/extensions/<ext_id>/` folder for extension to locally store its data.
- [ ] Add lifespan management: start and close.

### Twitter

- [x] Introduce a unified interface for fetching bookmarks, user and other stuff from Twitter.
  Current `auth.py` will be a kind of backend: `OfficialAPIBackend`.
  And we are going to introduce `twikit` backend.
  Only one backend can be enabled, config it at `config.backend`.
- [ ] Remove medias link in text
- [ ] Add twikit exception handling
- [ ] Close APIClient when close the application.
- [ ] Twikit get_tweet_id and _get_more_replies has bug: last item of entries does not has `itemContent` in `content`, should directly read `value` from `content`