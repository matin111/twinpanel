from __future__ import annotations


_MARKER = "TWINPANEL_PUBLIC_CONNECT_REQUEST_BACKPRESSURE_V1"


_V34_SUBSCRIPTION_COUNT_OLD = r"""  async function subscriptionCount(protocol){
    const url=subscriptionUrl(protocol);if(!url)return 0;
    try{
      const response=await fetch(url,{cache:'no-store',headers:{Accept:'text/plain'}});
      if(!response.ok)return 0;
      const encoded=String(await response.text()).trim();if(!encoded)return 0;
      const decoded=atob(encoded.replace(/\s+/g,''));
      return decoded.split(/\r?\n/).map(row=>row.trim()).filter(Boolean).length;
    }catch(_error){return 0}
  }
"""

_V34_SUBSCRIPTION_COUNT_NEW = r"""  function subscriptionCount(panel){
    return panel ? panel.querySelectorAll('.server-views .server-view').length : 0;
  }
"""

_V34_CARD_START_OLD = r"""    const card=document.createElement('section');card.className='v34-subscription-card';card.hidden=true;
    const head=document.createElement('div');head.className='v34-head';
    head.innerHTML='<b>همه سرورها</b><span>در حال بررسی…</span>';
"""

_V34_CARD_START_NEW = r"""    const count=subscriptionCount(panel);if(count<=0)return null;
    const card=document.createElement('section');card.className='v34-subscription-card';
    const head=document.createElement('div');head.className='v34-head';
    head.innerHTML='<b>همه سرورها</b><span>'+count+' سرور</span>';
"""

_V34_ASYNC_COUNT_OLD = r"""    subscriptionCount(key).then(count=>{
      if(count<=0){card.remove();return}
      const counter=head.querySelector('span');if(counter)counter.textContent=count+' سرور';
      card.hidden=false;
    });
"""

_V37_MULTI_META_OLD = r"""  async function multiMeta(protocol){
    const url=multiUrl(protocol);if(!url)return null;
    try{
      const response=await fetch(url+'/meta',{cache:'no-store',headers:{Accept:'application/json'}});
      if(!response.ok)return null;
      return await response.json();
    }catch(_error){return null}
  }
"""

_V37_MULTI_META_NEW = r"""  function multiMeta(panel){
    const nodeCount=panel ? panel.querySelectorAll('.server-views .server-view').length : 0;
    return nodeCount>0?{node_count:nodeCount,kind:''}:null;
  }
"""

_LIVE_REFRESH_OLD = r"""  async function refresh(){
    try{
      const response=await fetch(endpoint,{cache:'no-store',headers:{Accept:'application/json'}});
      if(!response.ok)return;
      apply(await response.json());
    }catch(_error){}
  }

  refresh();
  const timer=setInterval(refresh,3000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
"""

_LIVE_REFRESH_NEW = r"""  let refreshInFlight=false;
  async function refresh(){
    if(refreshInFlight||document.hidden)return;
    refreshInFlight=true;
    try{
      const response=await fetch(endpoint,{cache:'no-store',headers:{Accept:'application/json'}});
      if(!response.ok)return;
      apply(await response.json());
    }catch(_error){}finally{refreshInFlight=false}
  }

  refresh();
  const timer=setInterval(refresh,10000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
"""

# V44 already has a click-triggered lazy loader for grouped V2Ray/Xray profiles.
# Its trailing eager load duplicates that work during initial page boot and causes
# an unnecessary /sub/meta request before the customer opens the details.
_V44_EAGER_GROUP_LOAD_OLD = r"""    summary.append(count,toggle);
    card.append(summary,groups);
    loadGroups(card);
  }
"""

_V44_EAGER_GROUP_LOAD_NEW = r"""    summary.append(count,toggle);
    card.append(summary,groups);
  }
"""


def refine_public_connection_request_backpressure_v1(source: str) -> str:
    """Remove initial Public Connect request fan-out without changing delivery endpoints.

    Presentation counts are derived from the already-rendered canonical server views,
    V44 grouped V2Ray metadata remains click-triggered, and live polling is guarded so
    a slow request cannot overlap the next poll. All subscription/multi endpoints and
    user-triggered actions remain intact.
    """
    if _MARKER in source:
        return source

    source = source.replace(
        _V34_SUBSCRIPTION_COUNT_OLD,
        _V34_SUBSCRIPTION_COUNT_NEW,
        1,
    )
    source = source.replace(
        _V34_CARD_START_OLD,
        _V34_CARD_START_NEW,
        1,
    )
    source = source.replace(_V34_ASYNC_COUNT_OLD, "", 1)

    source = source.replace(_V37_MULTI_META_OLD, _V37_MULTI_META_NEW, 1)
    source = source.replace(
        "  async function buildMulti(panel){",
        "  function buildMulti(panel){",
        1,
    )
    source = source.replace(
        "    const meta=await multiMeta(protocol);",
        "    const meta=multiMeta(panel);",
        1,
    )

    source = source.replace(_V44_EAGER_GROUP_LOAD_OLD, _V44_EAGER_GROUP_LOAD_NEW, 1)
    source = source.replace(_LIVE_REFRESH_OLD, _LIVE_REFRESH_NEW, 1)

    return source.replace(
        "</body>",
        f"<!-- {_MARKER} -->\n</body>",
        1,
    )
