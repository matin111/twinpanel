export type StoreProtocolCategory="classic"|"recommended"|"camouflage"|"standalone";

export type StoreProtocolMeta={
  id:string;
  name:string;
  short:string;
  mark:string;
  icon:string;
  category:StoreProtocolCategory;
  transport:string;
  fa:string;
  en:string;
  aliases:string[];
};

export const STORE_PROTOCOL_CATALOG:StoreProtocolMeta[]=[
  {id:"cisco",name:"Cisco / OpenConnect",short:"Cisco",mark:"OC",icon:"◫",category:"classic",transport:"TCP / TLS",fa:"اتصال کلاسیک با OpenConnect و سازگاری گسترده روی دستگاه‌های مختلف.",en:"Classic OpenConnect access with broad device compatibility.",aliases:["cisco","openconnect","ocserv","cisco/openconnect"]},
  {id:"openvpn",name:"OpenVPN",short:"OpenVPN",mark:"OV",icon:"◉",category:"classic",transport:"UDP / TCP",fa:"پروتکل کلاسیک و قابل اتکا برای سیستم‌عامل‌ها و شبکه‌های مختلف.",en:"A proven classic protocol for many operating systems and networks.",aliases:["openvpn"]},
  {id:"wireguard",name:"WireGuard",short:"WireGuard",mark:"WG",icon:"⌁",category:"classic",transport:"UDP",fa:"اتصال سبک و سریع با فایل یا QR برای تجربه مدرن‌تر.",en:"Fast, lightweight connectivity with file or QR setup.",aliases:["wireguard","wg"]},
  {id:"l2tp",name:"L2TP / IPsec",short:"L2TP",mark:"L2",icon:"⌬",category:"classic",transport:"UDP",fa:"راه‌اندازی مستقیم از تنظیمات داخلی بسیاری از دستگاه‌ها.",en:"Built-in VPN setup on many devices without an extra client.",aliases:["l2tp","l2tp/ipsec","ipsec"]},
  {id:"v2ray",name:"V2Ray / Xray",short:"V2Ray",mark:"XR",icon:"V",category:"classic",transport:"Multi",fa:"گزینه منعطف برای شرایط شبکه متفاوت و سناریوهای حرفه‌ای‌تر.",en:"Flexible connectivity for varied network conditions and advanced scenarios.",aliases:["v2ray","xray","v2ray/xray"]},
  {id:"hysteria2",name:"Hysteria2",short:"Hysteria2",mark:"H2",icon:"H2",category:"recommended",transport:"UDP / QUIC",fa:"مسیر مدرن مبتنی بر QUIC برای شبکه‌های متغیر و اتصال‌های موبایل.",en:"Modern QUIC transport designed for variable and mobile networks.",aliases:["hysteria2","hysteria","hy2"]},
  {id:"tuic",name:"TUIC v5",short:"TUIC",mark:"TU",icon:"TU",category:"recommended",transport:"UDP / QUIC",fa:"ترنسپورت QUIC کم‌تاخیر برای اتصال‌های مدرن و پاسخ‌گو.",en:"Low-latency QUIC transport for responsive modern connectivity.",aliases:["tuic","tuic5","tuic_v5","tuic-v5"]},
  {id:"anytls",name:"AnyTLS",short:"AnyTLS",mark:"AT",icon:"AT",category:"recommended",transport:"TCP / TLS",fa:"ترنسپورت TLS محور برای سازگاری مناسب روی مسیرهای TCP.",en:"TLS-oriented transport for broad compatibility on TCP paths.",aliases:["anytls","any_tls"]},
  {id:"naive",name:"NaiveProxy",short:"NaiveProxy",mark:"NA",icon:"NA",category:"camouflage",transport:"TCP / TLS",fa:"اتصال TLS با الگوی ترافیکی نزدیک به مرورگر برای شبکه‌های محدودتر.",en:"Browser-like TLS transport intended for more restricted networks.",aliases:["naive","naiveproxy","naive_proxy"]},
  {id:"shadowtls",name:"ShadowTLS v3",short:"ShadowTLS",mark:"ST",icon:"ST",category:"camouflage",transport:"TCP",fa:"لایه استتار TLS برای سناریوهایی که ظاهر ترافیک اهمیت بیشتری دارد.",en:"TLS camouflage layer for scenarios where traffic appearance matters.",aliases:["shadowtls","shadowtls3","shadowtls_v3","shadowtls-v3"]},
  {id:"snell",name:"Snell",short:"Snell",mark:"SN",icon:"SN",category:"camouflage",transport:"TCP",fa:"ترنسپورت TCP پیشرفته با تمرکز بر کنترل و شکل‌دهی ترافیک.",en:"Advanced TCP transport focused on controlled traffic behavior.",aliases:["snell","snell6","snell_v6"]},
  {id:"mieru",name:"Mieru",short:"Mieru",mark:"MI",icon:"MI",category:"standalone",transport:"TCP / UDP",fa:"Runtime مستقل مدرن با پشتیبانی هم‌زمان از مسیرهای TCP و UDP.",en:"Standalone modern runtime supporting both TCP and UDP paths.",aliases:["mieru","mita"]},
  {id:"trusttunnel",name:"TrustTunnel",short:"TrustTunnel",mark:"TT",icon:"TT",category:"standalone",transport:"TCP / UDP / QUIC",fa:"Runtime مستقل چندمسیره با پشتیبانی HTTP و QUIC برای اتصال منعطف‌تر.",en:"Standalone multi-path runtime with HTTP and QUIC support.",aliases:["trusttunnel","trust_tunnel","trust-tunnel"]},
  {id:"amneziawg",name:"AmneziaWG",short:"AmneziaWG",mark:"AW",icon:"AW",category:"standalone",transport:"UDP",fa:"گزینه مستقل خانواده WireGuard برای سناریوهای اتصال مدرن.",en:"Standalone WireGuard-family option for modern connectivity scenarios.",aliases:["amneziawg","amnezia_wg","awg"]},
  {id:"sudoku",name:"Sudoku",short:"Sudoku",mark:"SU",icon:"SU",category:"standalone",transport:"TCP",fa:"Runtime مستقل TCP برای افزودن یک مسیر اتصال متفاوت به مجموعه پروتکل‌ها.",en:"Standalone TCP runtime adding another distinct connectivity path.",aliases:["sudoku"]},
];

export const STORE_CLASSIC_PROTOCOLS=STORE_PROTOCOL_CATALOG.filter(protocol=>protocol.category==="classic");
export const STORE_MODERN_PROTOCOLS=STORE_PROTOCOL_CATALOG.filter(protocol=>protocol.category!=="classic");

const protocolAliasMap=new Map<string,StoreProtocolMeta>();
for(const protocol of STORE_PROTOCOL_CATALOG){
  protocolAliasMap.set(protocol.id,protocol);
  for(const alias of protocol.aliases) protocolAliasMap.set(alias.toLowerCase(),protocol);
}

export function storeProtocolMeta(value:unknown){
  const normalized=String(value??"").trim().toLowerCase();
  return protocolAliasMap.get(normalized)??null;
}

export function normalizeStoreProtocolId(value:unknown){
  return storeProtocolMeta(value)?.id??String(value??"").trim().toLowerCase();
}
