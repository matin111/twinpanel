"use client";

import Link from "next/link";
import {useRouter} from "next/navigation";
import {useI18n} from "../lib/i18n";
import {installedStoreTemplate} from "../lib/store-template-registry";
import {ConversionTemplateCustomizer} from "./store-template-conversion-customizer";
import {EditorialTemplateCustomizer} from "./store-template-editorial-customizer";
import {OrbitTemplateCustomizerPolished} from "./store-template-orbit-customizer-polished";
import {StoreTemplateCustomizer} from "./store-template-customizer";
import {StoreTemplateSeoPanel} from "./store-template-seo-panel";
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

  const close=()=>router.push("/admin/store-settings");
  const customizer=template.id==="editorial-grid-2027"
    ?<EditorialTemplateCustomizer onClose={close}/>
    :template.id==="conversion-2027"
      ?<ConversionTemplateCustomizer onClose={close}/>
      :template.id==="orbit-neo-2027"
        ?<OrbitTemplateCustomizerPolished onClose={close}/>
        :<StoreTemplateCustomizer templateId={template.id} onClose={close}/>;

  return <Shell active="/admin/store-settings"><div className="page storeAdminManager">
    {customizer}
    {template.id!=="conversion-2027"&&<StoreTemplateSeoPanel templateId={template.id}/>}
  </div></Shell>;
}
