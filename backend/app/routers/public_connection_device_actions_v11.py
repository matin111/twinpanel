from __future__ import annotations

from .public_connection_canonical_presentation_v24 import (
    refine_public_connection_canonical_presentation_v24,
)
from .public_connection_mobile_stability_v25 import (
    refine_public_connection_mobile_stability_v25,
)


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

/* TWINPANEL_PUBLIC_CONNECT_KARING_DOWNLOADS_V50 */
.app-card.tp-karing-recommended{
  border-color:color-mix(in srgb,var(--primary) 52%,var(--line));
  background:linear-gradient(135deg,color-mix(in srgb,var(--primary) 11%,var(--surface)),var(--surface));
  box-shadow:0 10px 28px color-mix(in srgb,var(--primary) 10%,transparent);
}
.app-card.tp-karing-recommended b::after{
  content:'پیشنهادی';
  display:inline-flex;
  margin-inline-start:7px;
  padding:2px 7px;
  border-radius:999px;
  background:color-mix(in srgb,var(--primary) 13%,transparent);
  color:var(--primary);
  font-size:9px;
  font-weight:900;
  vertical-align:middle;
}
.app-card.tp-karing-recommended small{font-weight:700}
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

  const karingDownloads={
    windows:{
      url:'https://dot.karing.app/client.html?tag=windows-installer-stable',
      note:'دانلود مستقیم نسخه Stable ویندوز'
    },
    macos:{
      url:'https://dot.karing.app/client.html?tag=macos-stable',
      note:'دانلود مستقیم نسخه Stable مک'
    },
    android:{
      url:'https://dot.karing.app/client.html?tag=android-stable',
      note:'دانلود مستقیم نسخه Stable اندروید'
    },
    ios:{
      url:'https://apps.apple.com/us/app/karing/id6472431552',
      note:'دانلود Karing از App Store'
    },
    linux:{
      url:'https://dot.karing.app/client.html?tag=linux-deb-stable',
      note:'دانلود مستقیم Karing برای Debian / Ubuntu'
    }
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

  function addKaringDownload(group,platformKey){
    if(!group||group.querySelector('.tp-karing-recommended'))return;
    const item=karingDownloads[platformKey];
    if(!item)return;
    const grid=group.querySelector('.app-grid');
    if(!grid)return;

    const link=document.createElement('a');
    link.className='app-card tp-karing-recommended';
    link.href=item.url;
    link.target='_blank';
    link.rel='noopener noreferrer';
    link.dataset.client='karing';
    link.dataset.platform=platformKey;

    const icon=document.createElement('span');
    icon.textContent='↓';
    const copy=document.createElement('div');
    const title=document.createElement('b');
    title.textContent='Karing';
    const note=document.createElement('small');
    note.textContent=item.note;
    copy.append(title,note);
    link.append(icon,copy);
    grid.prepend(link);
  }

  document.querySelectorAll('.platform-group').forEach(group=>{
    addKaringDownload(group,String(group.dataset.platform||''));
  });

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
    """Detect the device once; keep connection data canonical and change presentation/apps only."""
    if "TWINPANEL_PUBLIC_CONNECT_DEVICE_ACTIONS_V11" not in source:
        source = source.replace("</style>", _V11_CSS + "\n</style>", 1)
        source = source.replace("</body>", _V11_SCRIPT + "\n</body>", 1)
    source = refine_public_connection_canonical_presentation_v24(source)
    return refine_public_connection_mobile_stability_v25(source)
