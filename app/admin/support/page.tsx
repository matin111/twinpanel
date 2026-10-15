import "../../support-center-cleanup.css";
import {AdminAuthGuard} from "../../../components/admin-auth-guard";
import {SupportCenterRuntimeV3} from "../../../components/support-center-runtime-v3";

export default function AdminSupportPage(){
  return <AdminAuthGuard><SupportCenterRuntimeV3/></AdminAuthGuard>;
}
