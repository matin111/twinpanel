from __future__ import annotations

from app.routers.public_connection_modern_delivery_v16 import (
    _scope_modern_actions_to_server_views,
)


def main() -> None:
    source = '''
<section id="hub-protocol-7" class="protocol-panel active" data-modern-protocol="hysteria2">
  <div class="panel-head">Hysteria2</div>
  <div class="server-views">
    <div id="hub-protocol-7-server-0" class="server-view active"><div class="facts">Germany</div></div>
    <div id="hub-protocol-7-server-1" class="server-view"><div class="facts">Netherlands</div></div>
  </div>
  <div class="v13-modern-action" data-v13-protocol="hysteria2"><div class="v13-action-buttons"><a href="/de">Germany config</a></div></div>
  <div class="v13-modern-action" data-v13-protocol="hysteria2"><div class="v13-action-buttons"><a href="/nl">Netherlands config</a></div></div>
</section>
'''

    result = _scope_modern_actions_to_server_views(source)

    de_open = (
        '<div id="hub-protocol-7-server-0" class="server-view active">'
        '<div class="v13-modern-action" data-v13-protocol="hysteria2">'
    )
    nl_open = (
        '<div id="hub-protocol-7-server-1" class="server-view">'
        '<div class="v13-modern-action" data-v13-protocol="hysteria2">'
    )

    assert de_open in result
    assert nl_open in result
    assert result.count('class="v13-modern-action"') == 2
    assert result.index('href="/de"') < result.index('hub-protocol-7-server-1')
    assert result.index('hub-protocol-7-server-1') < result.index('href="/nl"')

    # A mapping mismatch must remain unchanged rather than assigning the wrong
    # country's configuration to a server tab.
    mismatch = source.replace(
        '  <div class="v13-modern-action" data-v13-protocol="hysteria2"><div class="v13-action-buttons"><a href="/nl">Netherlands config</a></div></div>\n',
        '',
    )
    assert _scope_modern_actions_to_server_views(mismatch) == mismatch

    classic = '''
<section id="hub-protocol-1" class="protocol-panel active">
  <div id="hub-protocol-1-server-0" class="server-view active"></div>
</section>
'''
    assert _scope_modern_actions_to_server_views(classic) == classic

    print("MODERN_SERVER_COUNTRY_SCOPE_V263=PASS")


if __name__ == "__main__":
    main()
