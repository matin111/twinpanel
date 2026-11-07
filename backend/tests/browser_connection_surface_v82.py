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
    "naive","tuic","snell","cisco","sudoku","socks5",
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
    if not panel.is_visible():
        diagnostic=page.evaluate("""(id)=>{
          const node=document.getElementById(id);
          const attrs=e=>!e?null:{tag:e.tagName,classes:e.className,style:e.getAttribute('style'),
            display:getComputedStyle(e).display,visibility:getComputedStyle(e).visibility,
            hidden:e.hidden,width:e.getBoundingClientRect().width,height:e.getBoundingClientRect().height};
          return {panel:attrs(node),parent:attrs(node?.parentElement),
            grandparent:attrs(node?.parentElement?.parentElement),
            body:attrs(document.body),clicked:attrs(document.querySelector('.protocol-choice[data-protocol-key="openvpn"]')),
            active:[...document.querySelectorAll('.protocol-panel.active')].map(e=>e.id),
            classes:[...document.querySelectorAll('.protocol-panel')].slice(0,5).map(e=>({id:e.id,classes:e.className}))};
        }""",panel_id)
        print("MOBILE_HIDDEN_PANEL_DIAGNOSTIC",device,diagnostic,flush=True)
        page.screenshot(path=str(outfile).replace(".png","-hidden.png"),full_page=True)
    assert panel.is_visible(),f"{device}: panel hidden after selecting OpenVPN"
    assert panel.locator(".tp77-native-row").count()==4,f"{device}: expected four OpenVPN nodes"
    assert panel.locator(".tp80-file-download").count()==4,f"{device}: missing actual per-node file buttons"
    assert panel.locator(".tp80-file-download").first.is_visible()
    assert panel.locator('.tp78-action-footer a[href*="/multi/openvpn"]').count()==1,f"{device}: missing real all-files ZIP"
    # Only one country navigation; Germany has two distinct native files.
    assert panel.locator(":scope > .tp80-country-bar").count()==1,(device,"duplicate country navigation")
    assert panel.locator(".panel-head .server-tabs:visible").count()==0,(device,"duplicate header country flags")
    assert panel.locator(".tp80-country-bar button").count()==4,(device,"country dedupe")
    panel.locator('.tp80-country-bar button[data-tp80-country="DE"]').click()
    assert panel.locator(".tp77-native-row:visible").count()==2,(device,"DE must show both nodes")
    panel.locator('.tp80-country-bar button[data-tp80-country="TR"]').click()
    assert panel.locator(".tp77-native-row:visible").count()==1,(device,"TR must show only its node")
    panel.locator('.tp80-country-bar button[data-tp80-country="ALL"]').click()
    assert panel.locator(".tp77-native-row:visible").count()==4,(device,"ALL must restore every node")
    sizes=panel.locator(".tp77-native-row:visible").evaluate_all(
       "(nodes)=>nodes.map(node=>Math.round(node.getBoundingClientRect().height))")
    assert max(sizes)<=83,(device,"oversized file rows",sizes)
    for code in ("DE","TR","US"):
        assert panel.locator('.tp80-country-bar button[data-tp80-country="'+code+'"] img[src]').count()==1,(device,code,"flag image missing")
    if panel.locator('.tp78-action-footer [data-kind="app"]').count():
        assert panel.locator(':scope > .ref70-app-card:visible,:scope > .v34-client-card:visible').count()==0,(device,"duplicate app download")
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
        assert pane.locator(":scope > .tp80-country-bar").count()==1,(device,protocol,"duplicate flags")
        assert pane.locator(".panel-head .server-tabs:visible").count()==0,(device,protocol,"old flags still visible")
        shared=pane.locator(".tp80-credentials")
        assert shared.count()==1 and shared.is_visible(),(device,protocol,"login info hidden")
        assert shared.evaluate("(e)=>e.tagName")=="SECTION",(device,protocol,"credentials collapsed")
        fields=shared.locator(".v35-manual-item small").all_inner_texts()
        for required in (["نام کاربری","رمز عبور","IPsec Secret"] if protocol=="l2tp" else ["نام کاربری","رمز عبور"]):
            assert required in fields,(device,protocol,required,fields)
        assert shared.locator(".v35-manual-item button:visible").count()>=len(fields),(device,protocol,"copy action missing")
        country=pane.locator('.tp80-country-bar button[data-tp80-country="DE"]')
        assert country.count()==1,(device,protocol,"DE country button missing")
        country.click()
        assert pane.locator(".tp77-native-row:visible").count()==1,(device,protocol,"wrong country filtering")
        pane.locator('.tp80-country-bar button[data-tp80-country="ALL"]').click()
        assert pane.locator(".tp77-native-row:visible").count()>=2,(device,protocol,"ALL broken")
        # A node's detail must appear directly under that row, never after
        # the whole list when dozens of nodes exist.
        rows=pane.locator(".tp77-native-row:visible")
        rows.first.locator(".tp80-detail-toggle").click()
        inline=rows.first.locator("xpath=following-sibling::*[1]")
        assert inline.get_attribute("class") and "tp80-inline-native-detail" in inline.get_attribute("class")
        assert inline.is_visible(),(device,protocol,"detail is not inline")
        assert inline.locator(".server-view:visible").count()==1,(device,protocol,"real facts not visible")
        if rows.count()>1:
            rows.nth(1).locator(".tp80-detail-toggle").click()
            assert not inline.is_visible(),(device,protocol,"previous detail still expanded")
            second=rows.nth(1).locator("xpath=following-sibling::*[1]")
            assert second.is_visible(),(device,protocol,"second server detail missing")
        pane.screenshot(path=str(outfile).replace("openvpn",protocol+"-inline"),animations="disabled")
        if pane.locator('.tp78-action-footer [data-kind="app"]').count():
            assert pane.locator(':scope > .ref70-app-card:visible,:scope > .v34-client-card:visible').count()==0,(device,protocol,"duplicate app")
    # Visit each one of the fifteen customer-facing protocols, not just the
    # OpenVPN screenshot. All share the same node-row/real-action contract.
    native={"wireguard","openvpn","l2tp","amneziawg","cisco"}
    for protocol in PROTOCOLS:
        target=page.locator('.protocol-choice[data-protocol-key="'+protocol+'"]')
        assert target.count()==1,(device,protocol,"choice missing")
        target.click()
        page.wait_for_timeout(180)
        pane=page.locator("#"+target.get_attribute("data-protocol"))
        if not pane.is_visible():
            diagnostic=page.evaluate("""(id)=>{
              const node=document.getElementById(id);
              const attrs=e=>!e?null:{id:e.id,classes:e.className,display:getComputedStyle(e).display,
                visibility:getComputedStyle(e).visibility,ariaHidden:e.getAttribute('aria-hidden')};
              return {clicked:attrs(document.querySelector('.protocol-choice[data-protocol-key="'+
                   document.querySelector('.protocol-choice[data-protocol="'+id+'"]')?.dataset.protocolKey+'"]')),
                selected:attrs(node),
                active:[...document.querySelectorAll('.protocol-panel.active')].map(attrs),
                open:[...document.querySelectorAll('.protocol-panel.v36-open')].map(attrs)};
            }""",target.get_attribute("data-protocol"))
            print("HIDDEN_PROTOCOL_DEBUG",device,protocol,diagnostic,flush=True)
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
    # Validate newest SOCKS5 card and the official Sudoku application.
    sudoku_choice=page.locator('.protocol-choice[data-protocol-key="sudoku"]')
    sudoku_choice.click()
    page.wait_for_timeout(450)
    sudoku=page.locator("#"+sudoku_choice.get_attribute("data-protocol"))
    app=sudoku.locator('.tp78-action-footer [data-kind="app"]')
    assert app.count()==1 and app.is_visible(),(device,"missing Sudoku download")
    assert "github.com/SUDOKU-ASCII/sudoku-" in app.get_attribute("href") or "apps.apple.com" in app.get_attribute("href"),(device,"unofficial client")
    assert sudoku.locator(':scope > .ref70-app-card:visible,:scope > .v34-client-card:visible').count()==0,(device,"duplicate Sudoku download")
    socks_choice=page.locator('.protocol-choice[data-protocol-key="socks5"]')
    socks_choice.click()
    page.wait_for_timeout(450)
    socks=page.locator("#"+socks_choice.get_attribute("data-protocol"))
    details=socks.locator(".tp80-socks5-detail")
    assert details.count()>=1,(device,"no compact SOCKS5 details")
    first=socks.locator(".tp80-detail-toggle").first
    first.click()
    assert details.first.is_visible(),(device,"SOCKS5 details not opened under node")
    assert details.first.locator(".facts:visible .fact").count()>=3,(device,"SOCKS5 credentials unavailable")
    assert details.first.locator(".server-view:visible").count()==0,(device,"duplicate raw SOCKS5 data displayed")
    socks.screenshot(path=str(outfile).replace("openvpn","socks5"),animations="disabled")
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
