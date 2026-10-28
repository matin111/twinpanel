from __future__ import annotations


_MARKER = "TWINPANEL_PUBLIC_CONNECT_MOBILE_STABILITY_V25"

# V24 is inserted before the retired V17/V18/V20/V21 scripts.  The old guard
# watched the entire body subtree and then mutated that same subtree from its
# callback (syncApps changes textContent/style and retireLegacyMobile removes
# nodes).  That creates a self-triggering MutationObserver loop on mobile.
#
# Keep V24 as the canonical presentation/data authority, but defer one cleanup
# pass until the current parser task has finished executing the legacy inline
# scripts.  No persistent subtree observer is needed after that point.
_OLD_GUARD = """  function bindLegacyGuard(){
    legacyObserver?.disconnect();
    legacyObserver=new MutationObserver(()=>{
      retireLegacyMobile();
      syncApps();
    });
    legacyObserver.observe(document.body,{attributes:true,attributeFilter:['class'],childList:true,subtree:true});
    retireLegacyMobile();
  }
"""

_NEW_GUARD = """  function bindLegacyGuard(){
    /* TWINPANEL_PUBLIC_CONNECT_MOBILE_STABILITY_V25 */
    legacyObserver?.disconnect();
    legacyObserver=null;
    setTimeout(()=>{
      if(!window.matchMedia(MOBILE).matches)return;
      retireLegacyMobile();
      syncApps();
    },0);
  }
"""


def refine_public_connection_mobile_stability_v25(source: str) -> str:
    """Remove V24's self-triggering body observer without changing canonical data."""
    if _MARKER in source:
        return source
    if _OLD_GUARD not in source:
        return source
    return source.replace(_OLD_GUARD, _NEW_GUARD, 1)
