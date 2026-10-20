import {AdminAuthGuard} from "../../../../../components/admin-auth-guard";
import {AdminOperationFeedback} from "../../../../../components/admin-operation-feedback";
import {StoreTemplateCustomizerPage} from "../../../../../components/store-template-customizer-page";

export default async function Page({params}:{params:Promise<{templateId:string}>}){
  const {templateId}=await params;
  return <AdminAuthGuard><AdminOperationFeedback/><StoreTemplateCustomizerPage templateId={templateId}/></AdminAuthGuard>;
}
