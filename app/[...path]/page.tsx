import {RoutedPageClient} from "../../components/routed-page-client-v2";

export default async function Page({params}:{params:Promise<{path:string[]}>}){
  const {path}=await params;
  return <RoutedPageClient routeKey={path.join("/")}/>;
}