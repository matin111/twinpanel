import "../../support-center-cleanup.css";
import {AdminAuthGuard} from "../../../components/admin-auth-guard";
import {SupportCenterRuntimeV4} from "../../../components/support-center-runtime-v4";

export default function AdminSupportPage(){
  return <AdminAuthGuard><SupportCenterRuntimeV4/></AdminAuthGuard>;
}
