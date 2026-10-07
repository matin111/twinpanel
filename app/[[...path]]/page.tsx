import {AdminDashboard,AdminListPage,NotificationsPage,SettingsPage,SupportPage} from "../../components/admin-screens";
import {LoginPage,PanelPage,ResellerPage,StorePage} from "../../components/public-screens";
const route=(key:string)=>{
 if(key==="login")return <LoginPage/>; if(key==="admin")return <AdminDashboard/>;
 if(key==="admin/settings")return <SettingsPage/>; if(key==="admin/notifications")return <NotificationsPage/>;
 if(key==="admin/support")return <SupportPage/>; if(key==="panel")return <PanelPage/>; if(key==="reseller")return <ResellerPage/>; if(key==="store")return <StorePage/>;
 const map:Record<string,[string,string]>={"admin/users":["کاربران","user"],"admin/subscriptions":["اشتراک‌ها","subscription"],"admin/plans":["پلن‌ها","plan"],"admin/nodes":["نودها","node"],"admin/tunnels":["تانل‌ها","tunnel"],"admin/payments":["پرداخت‌ها","payment"]};
 const v=map[key]; return v?<AdminListPage title={v[0]} kind={v[1]}/>:<StorePage/>;
};
export default async function Page({params}:{params:Promise<{path?:string[]}>}){const {path=[]}=await params;return route(path.join("/"))}
