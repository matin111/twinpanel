from __future__ import annotations

# Only the visual subscription-status card on the public Connection page.
# No changes to subscription data, quotas, dates, services or VPN configs.
_MARKER = "TWINPANEL_PUBLIC_CONNECT_STATUS_DASHBOARD_V66"

_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_STATUS_DASHBOARD_V66 */
body.tp66-status .traffic{
  display:grid!important;grid-template-columns:minmax(0,1fr)!important;gap:16px!important;
  padding:20px!important;border:1px solid #42467d!important;border-radius:20px!important;
  background:linear-gradient(125deg,#17223d 5%,#171c37 65%,#251c4b 100%)!important;
  box-shadow:0 14px 38px rgba(0,0,0,.18);
}
body.tp66-status .traffic .visual{
  display:flex!important;align-items:center!important;justify-content:space-between!important;
  gap:14px!important;min-width:0;padding:0 2px 13px;border-bottom:1px solid rgba(151,165,209,.17);
}
body.tp66-status .traffic .visual>div:last-child{order:-1;min-width:0;display:flex;align-items:center;gap:12px;flex-wrap:wrap}
body.tp66-status .traffic .visual h2{
  font-size:19px!important;line-height:1.55!important;font-weight:850!important;
  letter-spacing:0!important;color:#fff!important;margin:0!important;
}
body.tp66-status .traffic .visual em{
  font-size:10px!important;line-height:1.2!important;font-weight:800!important;
  padding:6px 10px!important;border:1px solid rgba(74,227,154,.36)!important;
  border-radius:999px!important;background:rgba(34,187,112,.14)!important;color:#7ff5b7!important;
  margin:0!important;
}
body.tp66-status .traffic .donut{
  flex:0 0 76px!important;width:76px!important;height:76px!important;
  background:conic-gradient(#926cff calc(var(--pct)*1%),#303b61 0)!important;
}
body.tp66-status .traffic .donut:before{inset:8px!important;background:#151b32!important}
body.tp66-status .traffic .donut b{font-size:17px!important;line-height:1.2!important;color:#fff!important}
body.tp66-status .traffic .donut small{font-size:10px!important;line-height:1.4!important;color:#c1cce1!important}
body.tp66-status .traffic .stats{
  display:grid!important;grid-template-columns:repeat(5,minmax(0,1fr))!important;gap:10px!important;
  width:100%!important;direction:rtl!important;align-items:stretch;
}
body.tp66-status .traffic .stat{
  min-width:0;min-height:92px;padding:13px 12px!important;
  border:1px solid #394668!important;border-radius:13px!important;
  background:linear-gradient(145deg,#1c2845,#182039)!important;
  display:flex!important;flex-direction:column;justify-content:center!important;gap:9px!important;
  text-align:right!important;
}
body.tp66-status .traffic .stat:last-child{border:1px solid #394668!important}
body.tp66-status .traffic .stat small{
  display:block!important;color:#c3cee5!important;font-size:12px!important;
  font-weight:650!important;line-height:1.5!important;
}
body.tp66-status .traffic .stat strong{
  display:block!important;color:#fff!important;font-size:clamp(15px,1.35vw,19px)!important;
  font-weight:850!important;line-height:1.5!important;font-variant-numeric:tabular-nums;
  overflow-wrap:anywhere;word-break:normal;unicode-bidi:plaintext;
}
@media(max-width:980px){
  body.tp66-status .traffic .stats{grid-template-columns:repeat(3,minmax(0,1fr))!important}
}
@media(max-width:720px){
  body.tp66-status .traffic{padding:13px!important;gap:11px!important;border-radius:17px!important}
  body.tp66-status .traffic .visual{min-height:62px;padding-bottom:11px;gap:9px}
  body.tp66-status .traffic .visual h2{font-size:17px!important}
  body.tp66-status .traffic .visual>div:last-child{gap:7px}
  body.tp66-status .traffic .donut{width:62px!important;height:62px!important;flex-basis:62px!important}
  body.tp66-status .traffic .donut:before{inset:7px!important}
  body.tp66-status .traffic .donut b{font-size:14px!important}
  body.tp66-status .traffic .donut small{font-size:9px!important}
  body.tp66-status .traffic .stats{grid-template-columns:repeat(2,minmax(0,1fr))!important;gap:8px!important}
  body.tp66-status .traffic .stat{min-height:77px;padding:10px 11px!important;gap:6px!important;border-radius:11px!important}
  body.tp66-status .traffic .stat small{font-size:11px!important}
  body.tp66-status .traffic .stat strong{font-size:16px!important}
  body.tp66-status .traffic .stat:nth-child(5){grid-column:span 2}
}
@media(max-width:350px){
  body.tp66-status .traffic .stat strong{font-size:14px!important}
}
@media(prefers-reduced-motion:reduce){
  body.tp66-status .traffic *{transition:none!important}
}
"""

_SCRIPT = r"""
<script id="twinpanelPublicConnectStatusDashboardV66">
(function(){
  if(!/^\/v1\/connect\/[^/]+\/?$/.test(location.pathname))return;
  if(!document.querySelector('.traffic .visual, .traffic .stats'))return;
  // The original server-rendered status, numbers, dates and percentage remain
  // untouched: this is solely a final layout/typography layer.
  document.body.classList.add('tp66-status');
})();
</script>
"""

def refine_public_connection_status_dashboard_v66(source: str) -> str:
    if _MARKER in source:
        return source
    source = source.replace("</style>", _CSS + "\n</style>", 1)
    return source.replace("</body>", _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>", 1)
