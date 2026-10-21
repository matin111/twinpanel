"use client";

import {AdminAuthGuard} from "./admin-auth-guard";
import {AdminOperationFeedback} from "./admin-operation-feedback";
import {LegacyNodesRuntimePage} from "./legacy-nodes-runtime-v2";
import {RoutedPageClient as BaseRoutedPageClient} from "./routed-page-client";

const admin=(node:React.ReactNode)=><AdminAuthGuard><AdminOperationFeedback/>{node}</AdminAuthGuard>;

export function RoutedPageClient({routeKey}:{routeKey:string}){
  if(routeKey==="admin/nodes"||routeKey==="admin/network"){
    return admin(<LegacyNodesRuntimePage/>);
  }
  return <BaseRoutedPageClient routeKey={routeKey}/>;
}
