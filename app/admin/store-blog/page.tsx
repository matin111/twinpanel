import {AdminAuthGuard} from "../../../components/admin-auth-guard";
import {AdminOperationFeedback} from "../../../components/admin-operation-feedback";
import {NovaBlogManager} from "../../../components/nova-blog-manager";
export default function Page(){return <AdminAuthGuard><AdminOperationFeedback/><NovaBlogManager/></AdminAuthGuard>;}
