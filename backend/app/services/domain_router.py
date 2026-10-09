SERVICE_ROUTES = {
    "shop": {
        "host": "127.0.0.1",
        "port": 3000,
        "service": "twinpanel-web",
    },

    "panel": {
        "host": "127.0.0.1",
        "port": 3000,
        "service": "twinpanel-web",
    },

    "api": {
        "host": "127.0.0.1",
        "port": 8095,
        "service": "vpnshop-api",
    },

    "subscription": {
        "host": "127.0.0.1",
        "port": 8095,
        "service": "vpnshop-api",
    },
}


def resolve_domain_route(domain_type):
    key = str(domain_type).lower()

    if "." in key:
        key = key.split(".")[-1]

    return SERVICE_ROUTES.get(
        key,
        SERVICE_ROUTES["shop"]
    )
