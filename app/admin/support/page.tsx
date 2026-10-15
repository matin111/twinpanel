import {AdminAuthGuard} from "../../../components/admin-auth-guard";
import {SupportCenterRuntimeV2} from "../../../components/support-center-runtime-v2";

export default function AdminSupportPage(){
  return <AdminAuthGuard><SupportCenterRuntimeV2/></AdminAuthGuard>;
}
