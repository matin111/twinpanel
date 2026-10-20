"use client";

import Link from "next/link";
import {useRouter} from "next/navigation";
import {useI18n} from "../lib/i18n";
import {installedStoreTemplate} from "../lib/store-template-registry";
import {EditorialTemplateCustomizer} from "./store-template-editorial-customizer";
import {StoreTemplateCustomizer} from "./store-template-customizer";
import {Card,Shell} from "./ui";

export function StoreTemplateCustomizerPage({templateId}:{templateId:string}){
  const {pick}=useI18n();
  const router=useRouter();
  const template=installedStoreTemplate(templateId);

  if(!template){
    return <Shell active="/admin/store-settings"><div className="page storeAdminManager">
      <div className="page-head">
        <div><h1>{pick("قالب پیدا نشد","Template not found")}</h1><small>{pick("این قالب در نسخه فعلی نصب نیست.","This template is not installed in the current version.")}</small></div>
        <div className="action-row"><Link className="ghost" href="/admin/store-settings">{pick("بازگشت به قالب‌ها","Back to templates")}</Link></div>
      </div>
      <Card><b>{pick("شناسه قالب نامعتبر است.","The template id is invalid.")}</b><p>{templateId}</p></Card>
    </div></Shell>;
  }

  return <Shell active="/admin/store-settings"><div className="page storeAdminManager">
    {template.id==="editorial-grid-2027"
      ?<EditorialTemplateCustomizer onClose={()=>router.push("/admin/store-settings")}/>
      :<StoreTemplateCustomizer templateId={template.id} onClose={()=>router.push("/admin/store-settings")}/>
    }
  </div></Shell>;
}
