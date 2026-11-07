"""Visual browser regression of the actual Connection renderers with fake data.

No live secrets or VPN endpoints: the page is served entirely from Playwright routes.
Run: PYTHONPATH=backend python backend/tests/browser_connection_surface_v82.py
"""
from __future__ import annotations

from datetime import datetime
import importlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

from playwright.sync_api import sync_playwright

PROTOCOLS=[
    "v2ray","wireguard","openvpn","l2tp","amneziawg",
    "hysteria2","anytls","shadowtls","trusttunnel","mieru",
    "naive","tuic","snell","cisco","sudoku",
]

def mock_page():
    hub=importlib.import_module("app.routers.public_connection_hub_v5")
    composer=importlib.import_module("app.routers.public_connection_canonical_mobile_v26")
    sub=SimpleNamespace(id=1,user_id=2,account_username="DEMO",status="active",
                        starts_at=datetime(2026,11,1),expires_at=datetime(2026,12,1))
    creds=[]
    for protocol in PROTOCOLS:
        items=[]
        for i,code in enumerate(["DE","US","TR","DE"] if protocol=="openvpn" else ["DE","TR"]):
            n=13+i
            items.append({
              "node_id":n,"country_code":code,"host":f"198.51.100.{n}",
              "filename":f"{code}-{n}." + ("ovpn" if protocol=="openvpn" else "conf"),
              "config":f"# synthetic profile {protocol} {n}\n",
              "uri":f"vless://synthetic@198.51.100.{n}:443?encryption=none",
              "username":"DEMO","password":"dummy","port":443,"psk":"fake-test-key",
            })
        creds.append({"protocol":protocol,"items":items})
    fake_payload={"account":{"username":"DEMO","password":"dummy"},
                  "subscription_link":"https://mock.panel/v1/connect/demo/sub","credentials":creds}
    class Query:
        def filter(self,*args,**kwargs):return self
        def filter_by(self,*args,**kwargs):return self
        def order_by(self,*args,**kwargs):return self
        def join(self,*args,**kwargs):return self
        def limit(self,*args,**kwargs):return self
        def first(self):return None
        def all(self):return []
    class DB:
        def query(self,model):return Query()
        def get(self,model,pk):return SimpleNamespace(full_name="Demo",email="demo@example.invalid")
    originals={name:getattr(hub,name) for name in (
       "_subscription_from_share_token","_public_payload","_usage_payload","public_downloads_by_platform")}
    try:
        hub._subscription_from_share_token=lambda token,db:sub
        hub._public_payload=lambda db,sub:fake_payload
        hub._usage_payload=lambda db,sub:{"used_gb":0.5,"total_gb":100,
                                          "remaining_gb":99.5,"percent":0.5}
        hub.public_downloads_by_platform=lambda db:{}
        raw=hub.public_connection_hub_v5("demo",DB()).body.decode("utf-8")
        return composer.refine_public_connection_canonical_mobile_v26(raw)
    finally:
        for name,value in originals.items():setattr(hub,name,value)

def fake_meta():
    servers=[]
    for n,code in [(13,"DE"),(14,"TR")]:
        profiles=[]
        for mode in ["WebSocket TLS","XHTTP REALITY","TCP TLS"]:
            profiles.append({"uri":f"vless://synthetic@198.51.100.{n}:443#node-{n}",
                             "title":f"Node {n}","transport":mode,"security":"tls"})
        servers.append({"node_id":n,"country_code":code,"profiles":profiles})
    return json.dumps({"servers":servers})

def verify(context,html,device,outfile):
    page=context.new_page()
    errors=[]
    page.on("pageerror",lambda error:errors.append(str(error)))
    def mocked(route):
        url=route.request.url
        if url.endswith("/v1/connect/demo"):
            route.fulfill(status=200,content_type="text/html; charset=utf-8",body=html)
        elif url.endswith("/v1/connect/demo/sub/meta"):
            route.fulfill(status=200,content_type="application/json",body=fake_meta())
        elif "/v1/connect/demo/" in url:
            route.fulfill(status=404,content_type="application/json",body="{}")
        else:
            route.fulfill(status=404,body="")
    page.route("**/*",mocked)
    page.goto("http://mock.panel/v1/connect/demo",wait_until="domcontentloaded")
    page.wait_for_timeout(1700)
    stats=page.locator(".traffic .stats > .stat")
    assert stats.count()==5,f"{device}: missing two dates"
    assert stats.nth(3).is_visible() and stats.nth(4).is_visible(),f"{device}: dates hidden"
    assert "اولین اتصال" in stats.nth(3).inner_text()
    assert page.locator(".protocol-choice").count()>=15
    assert page.locator(".tp78-ping,.ref71-rtt,.tp78-reach").filter(visible=True).count()==0
    assert page.locator(".protocol-panel.active").count()==1,f"{device}: many protocol panels"

    choice=page.locator('.protocol-choice[data-protocol-key="openvpn"]')
    assert choice.count()==1
    choice.click()
    page.wait_for_timeout(1100)
    panel_id=choice.get_attribute("data-protocol")
    panel=page.locator("#"+panel_id)
    assert panel.is_visible()
    assert panel.locator(".tp77-native-row").count()==4,f"{device}: expected four OpenVPN nodes"
    assert panel.locator(".tp80-file-download").count()==4,f"{device}: missing actual per-node file buttons"
    assert panel.locator(".tp80-file-download").first.is_visible()
    assert panel.locator('.tp78-action-footer a[href*="/multi/openvpn"]').count()==1,f"{device}: missing real all-files ZIP"
    assert panel.locator(".server-view:visible").count()==0,f"{device}: duplicate large native file cards still displayed"
    assert panel.locator(".tp78-ping:visible,.ref71-rtt:visible").count()==0
    if device=="mobile":
        css=page.locator(".protocols").evaluate("(e)=>getComputedStyle(e).gridTemplateColumns")
        assert len(css.split())==4,f"Mobile protocol grid must have 4 columns: {css}"
        assert choice.locator(".protocol-text b").is_visible()
        assert choice.locator(".protocol-icon").is_visible()
    panel.screenshot(path=str(outfile),animations="disabled")
    assert len([e for e in errors if "SyntaxError" in e])==0,(device,errors[:5])

    for protocol in ("cisco","l2tp"):
        target=page.locator('.protocol-choice[data-protocol-key="'+protocol+'"]')
        target.click()
        page.wait_for_timeout(450)
        pane=page.locator("#"+target.get_attribute("data-protocol"))
        assert pane.locator(".tp77-native-row").count()>=1,f"{device} {protocol}: no server rows"
        assert pane.locator(".tp78-ping:visible").count()==0
    # Visit each one of the fifteen customer-facing protocols, not just the
    # OpenVPN screenshot. All share the same node-row/real-action contract.
    native={"wireguard","openvpn","l2tp","amneziawg","cisco"}
    for protocol in PROTOCOLS:
        target=page.locator('.protocol-choice[data-protocol-key="'+protocol+'"]')
        assert target.count()==1,(device,protocol,"choice missing")
        target.click()
        page.wait_for_timeout(180)
        pane=page.locator("#"+target.get_attribute("data-protocol"))
        assert pane.is_visible(),(device,protocol,"hidden panel")
        assert page.locator(".protocol-panel.active").count()==1,(device,protocol,"multiple panels")
        if protocol in native:
            assert pane.locator(".tp77-native-row").count()>=1,(device,protocol,"missing file/manual nodes")
        elif protocol=="v2ray":
            assert pane.locator(".v54-v2ray-server").count()>=1,(device,protocol,"missing profile groups")
        else:
            assert pane.locator(".ref67-row").count()>=1,(device,protocol,"missing modern node rows")
        assert pane.locator(".tp78-ping:visible,.ref71-rtt:visible").count()==0,(device,protocol,"ping visible")
        for button in pane.locator(".tp78-action-footer > button,.tp78-action-footer > a").all():
            assert button.is_enabled(),(device,protocol,"dead footer button")
            href=button.get_attribute("href")
            assert not href or not href.startswith("#"),(device,protocol,"broken app link")
    page.close()

def main():
    html=mock_page()
    out=Path(os.environ.get("CONNECTION_TEST_ARTIFACTS","connection-browser-artifacts"))
    out.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=True,args=["--no-sandbox"])
        desktop=browser.new_context(viewport={"width":1440,"height":900},accept_downloads=True)
        verify(desktop,html,"desktop",out/"desktop-openvpn.png")
        desktop.close()
        mobile=browser.new_context(viewport={"width":390,"height":844},
            user_agent="Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 Chrome/130.0 Mobile Safari/537.36",
            is_mobile=True,has_touch=True,accept_downloads=True)
        verify(mobile,html,"mobile",out/"mobile-openvpn.png")
        mobile.close()
        browser.close()
    print("Browser verified: five stats, fifteen choices, single selected panel, four OpenVPN files, real bundle, no ping, mobile protocol grid.")

if __name__=="__main__":
    main()
