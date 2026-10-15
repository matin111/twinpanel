import {AdminAuthGuard} from "../../../components/admin-auth-guard";
import {SupportCenterRuntime} from "../../../components/support-center-runtime";

export default function AdminSupportPage(){
  return <AdminAuthGuard><SupportCenterRuntime/></AdminAuthGuard>;
}
