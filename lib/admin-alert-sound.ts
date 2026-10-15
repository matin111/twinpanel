"use client";

let ctx:AudioContext|null=null;
let unlocked=false;
let listenersInstalled=false;

function getContext(){
  if(typeof window==="undefined")return null;
  const Ctor=window.AudioContext||(window as typeof window&{webkitAudioContext?:typeof AudioContext}).webkitAudioContext;
  if(!Ctor)return null;
  if(!ctx)ctx=new Ctor();
  return ctx;
}

async function unlock(){
  const audio=getContext();
  if(!audio)return;
  try{
    if(audio.state==="suspended")await audio.resume();
    unlocked=audio.state==="running";
  }catch{}
}

export function installSoundUnlock(){
  if(typeof window==="undefined"||listenersInstalled)return;
  listenersInstalled=true;
  const handler=()=>{void unlock();};
  window.addEventListener("pointerdown",handler,{passive:true});
  window.addEventListener("keydown",handler,{passive:true});
}

function tone(frequency:number,start:number,duration:number,gainValue:number){
  const audio=getContext();
  if(!audio||audio.state!=="running")return;
  const osc=audio.createOscillator();
  const gain=audio.createGain();
  osc.type="sine";
  osc.frequency.setValueAtTime(frequency,start);
  gain.gain.setValueAtTime(0.0001,start);
  gain.gain.exponentialRampToValueAtTime(gainValue,start+0.015);
  gain.gain.exponentialRampToValueAtTime(0.0001,start+duration);
  osc.connect(gain);
  gain.connect(audio.destination);
  osc.start(start);
  osc.stop(start+duration+0.03);
}

export function playAdminAlert(kind:"support"|"receipt"|"customer_reply"="support"){
  installSoundUnlock();
  const audio=getContext();
  if(!audio)return;
  if(audio.state!=="running"||!unlocked){void unlock();return;}
  const now=audio.currentTime+0.01;
  if(kind==="receipt"){
    tone(660,now,0.12,0.12);
    tone(880,now+0.15,0.16,0.14);
    tone(1040,now+0.34,0.18,0.12);
    return;
  }
  if(kind==="customer_reply"){
    tone(740,now,0.14,0.11);
    tone(980,now+0.18,0.18,0.12);
    return;
  }
  tone(880,now,0.12,0.11);
  tone(1120,now+0.16,0.15,0.12);
}
