"use client";

let audioContext:AudioContext|null=null;
let primed=false;

function context(){
  if(typeof window==="undefined")return null;
  const AudioCtor=window.AudioContext||(window as typeof window&{webkitAudioContext?:typeof AudioContext}).webkitAudioContext;
  if(!AudioCtor)return null;
  if(!audioContext)audioContext=new AudioCtor();
  return audioContext;
}

export async function primeNotificationSound(){
  const ctx=context();
  if(!ctx)return;
  try{
    if(ctx.state==="suspended")await ctx.resume();
    primed=ctx.state==="running";
  }catch{}
}

function tone(ctx:AudioContext,frequency:number,start:number,duration:number,gainValue:number){
  const oscillator=ctx.createOscillator();
  const gain=ctx.createGain();
  oscillator.type="sine";
  oscillator.frequency.setValueAtTime(frequency,start);
  gain.gain.setValueAtTime(0.0001,start);
  gain.gain.exponentialRampToValueAtTime(gainValue,start+0.015);
  gain.gain.exponentialRampToValueAtTime(0.0001,start+duration);
  oscillator.connect(gain);
  gain.connect(ctx.destination);
  oscillator.start(start);
  oscillator.stop(start+duration+0.02);
}

export async function playNotificationSound(kind:"message"|"receipt"="message"){
  const ctx=context();
  if(!ctx)return;
  try{
    if(ctx.state==="suspended")await ctx.resume();
    if(ctx.state!=="running")return;
    const now=ctx.currentTime+0.01;
    if(kind==="receipt"){
      tone(ctx,740,now,0.12,0.06);
      tone(ctx,988,now+0.13,0.16,0.055);
    }else{
      tone(ctx,660,now,0.10,0.05);
      tone(ctx,880,now+0.105,0.11,0.045);
    }
    primed=true;
  }catch{}
}

export function notificationSoundPrimed(){return primed;}
