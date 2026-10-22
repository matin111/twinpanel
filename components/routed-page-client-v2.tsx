"use client";

import {AdminAuthGuard} from "./admin-auth-guard";
import {AdminOperationFeedback} from "./admin-operation-feedback";
import {LegacyNodesRuntimePage} from "./legacy-nodes-runtime-v2";
import {RoutedPageClient as BaseRoutedPageClient} from "./routed-page-client";
import {SubscriptionDeliveryPolicyManager} from "./subscription-delivery-policy-manager";

const admin=(node:React.ReactNode)=><AdminAuthGuard><AdminOperationFeedback/>{node}</AdminAuthGuard>;

export function RoutedPageClient({routeKey}:{routeKey:string}){
  if(routeKey==="admin/nodes"||routeKey==="admin/network"){
    return admin(<LegacyNodesRuntimePage/>);
  }
  if(routeKey==="admin/subscriptions"){
    return <><BaseRoutedPageClient routeKey={routeKey}/><SubscriptionDeliveryPolicyManager/></>;
  }
  return <BaseRoutedPageClient routeKey={routeKey}/>;
}
