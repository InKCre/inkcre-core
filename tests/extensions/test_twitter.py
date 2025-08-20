

# test auth

from extensions.twitter.api import TwitterAPI

def test_get_oauth_authorize_url():
    url = TwitterAPI.get_oauth_authorize_url()
    assert type(url) is str

    print(url)
