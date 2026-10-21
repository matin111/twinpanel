from __future__ import annotations


_V11_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_DEVICE_ACTIONS_V11 */
body[data-public-connect-mobile="v7"] .mobile-send-btn,
body[data-public-connect-mobile="v7"] .v9-icon-btn.mobile{
  display:none;
}
body[data-public-connect-mobile="v7"].tp-phone-actions .mobile-send-btn{
  display:inline-flex;
  align-items:center;
  justify-content:center;
}
body[data-public-connect-mobile="v7"].tp-phone-actions .v9-icon-btn.mobile{
  display:grid;
}

body[data-tp-platform="windows"] .platform-group:not([data-platform="windows"]),
body[data-tp-platform="macos"] .platform-group:not([data-platform="macos"]),
body[data-tp-platform="android"] .platform-group:not([data-platform="android"]),
body[data-tp-platform="ios"] .platform-group:not([data-platform="ios"]),
body[data-tp-platform="linux"] .platform-group:not([data-platform="linux"]){
  display:none;
}
body.tp-show-all-platforms .platform-group{display:block}
"""


_V11_SCRIPT = r"""
<script id="twinpanelPublicConnectDeviceActionsV11">
(function(){
  const body=document.body;
  const names={
    windows:'Windows',
    macos:'macOS',
    android:'Android',
    ios:'iPhone / iPad',
    linux:'Linux',
    unknown:'همه سیستم‌ها'
  };

  function detectPlatform(){
    const uaData=navigator.userAgentData||null;
    const ua=String(navigator.userAgent||'');
    const platform=String((uaData&&uaData.platform)||navigator.platform||'');
    const haystack=(ua+' '+platform).toLowerCase();

    if(/android/i.test(ua))return'android';
    if(/iphone|ipad|ipod/i.test(ua))return'ios';
    if(/macintosh|mac os|macintel/i.test(haystack)&&Number(navigator.maxTouchPoints||0)>1)return'ios';
    if(/windows|win32|win64|winarm/i.test(haystack))return'windows';
    if(/macintosh|mac os|macintel/i.test(haystack))return'macos';
    if(/linux|x11|cros/i.test(haystack))return'linux';
    return'unknown';
  }

  const platform=detectPlatform();
  const phoneActions=platform==='android'||platform==='ios';
  body.dataset.tpPlatform=platform;
  document.documentElement.dataset.tpPlatform=platform;
  body.classList.toggle('tp-phone-actions',phoneActions);
  body.classList.toggle('tp-desktop-device',!phoneActions);

  const deviceLabel=document.getElementById('device');
  if(deviceLabel)deviceLabel.textContent=names[platform]||names.unknown;

  const groups=[...document.querySelectorAll('.platform-group')];
  if(platform!=='unknown'){
    groups.forEach(group=>{
      const active=group.dataset.platform===platform;
      group.classList.toggle('device-active',active);
      group.classList.remove('show-all');
    });
  }

  const allButton=document.getElementById('all');
  if(allButton){
    allButton.textContent='همه سیستم‌ها';
    allButton.addEventListener('click',()=>{
      setTimeout(()=>{
        const showingAll=groups.some(group=>group.classList.contains('show-all'));
        body.classList.toggle('tp-show-all-platforms',showingAll);
      },0);
    });
  }

  function sourceAppLinks(){
    const apps=document.querySelector('.apps');
    if(!apps)return[];
    if(platform==='unknown')return[...apps.querySelectorAll('a.app-card')];
    const group=apps.querySelector('.platform-group[data-platform="'+CSS.escape(platform)+'"]');
    return group?[...group.querySelectorAll('a.app-card')]:[];
  }

  const drawer=document.querySelector('.v9-apps-drawer');
  if(drawer){
    const summary=drawer.querySelector('summary');
    const list=drawer.querySelector('.v9-apps-list');
    if(summary)summary.textContent=platform==='unknown'?'دانلود برنامه‌های اتصال':'برنامه‌های مناسب '+(names[platform]||'دستگاه شما');
    if(list){
      list.replaceChildren();
      sourceAppLinks().slice(0,10).forEach(link=>{
        const item=document.createElement('a');
        item.className='v9-app-link';
        item.href=link.getAttribute('href')||'#';
        item.target='_blank';
        item.rel='noopener noreferrer';
        item.textContent=(link.querySelector('b')?.textContent||'برنامه').trim();
        list.appendChild(item);
      });
    }
  }

  const appsHeading=document.querySelector('.apps-head h2');
  if(appsHeading&&platform!=='unknown')appsHeading.textContent='برنامه‌های '+(names[platform]||'دستگاه شما');
})();
</script>
"""


def refine_public_connection_device_actions_v11(source: str) -> str:
    """Use one OS detector for platform apps and phone-only actions across the public connection page."""
    if "TWINPANEL_PUBLIC_CONNECT_DEVICE_ACTIONS_V11" in source:
        return source
    source = source.replace("</style>", _V11_CSS + "\n</style>", 1)
    source = source.replace("</body>", _V11_SCRIPT + "\n</body>", 1)
    return source
