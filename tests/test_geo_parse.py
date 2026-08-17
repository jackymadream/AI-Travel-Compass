from src.utils.geo_parse import parse_google_maps_url


def test_parse_at_coords() -> None:
    assert parse_google_maps_url(
        "https://www.google.com/maps/@35.6595,139.7004,17z"
    ) == (35.6595, 139.7004)


def test_parse_bang_3d() -> None:
    assert parse_google_maps_url(
        "https://www.google.com/maps/place/Foo/data=!3d35.68!4d139.76"
    ) == (35.68, 139.76)


def test_parse_invalid() -> None:
    assert parse_google_maps_url("not a maps url") is None
