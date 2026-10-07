import {AdminDashboard,AdminListPage,NotificationsPage,SettingsPage,SupportPage} from "../../components/admin-screens";
import {LoginPage,PanelPage,ResellerPage,StorePage} from "../../components/public-screens";

const route=(key:string)=>{
  if(key==="login") return <LoginPage/>;
  if(key==="admin") return <AdminDashboard/>;
  if(key==="admin/settings") return <SettingsPage/>;
  if(key==="admin/notifications") return <NotificationsPage/>;
  if(key==="admin/support") return <SupportPage/>;
  if(key==="panel") return <PanelPage/>;
  if(key==="reseller") return <ResellerPage/>;
  if(key==="store") return <StorePage/>;

  const map:Record<string,string>={
    "admin/users":"user",
    "admin/subscriptions":"subscription",
    "admin/plans":"plan",
    "admin/nodes":"node",
    "admin/tunnels":"tunnel",
    "admin/payments":"payment"
  };

  const kind=map[key];
  return kind?<AdminListPage kind={kind}/>:<StorePage/>;
};

export default async function Page({params}:{params:Promise<{path:string[]}>}){
  const {path}=await params;
  return route(path.join("/"));
}
