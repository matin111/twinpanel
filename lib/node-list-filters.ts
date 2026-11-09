/** Read-only node table filters. Never alter provisioned node roles/statuses. */
export type NodeListFilter =
  | "all" | "online" | "iran" | "exit"
  | "offline" | "maintenance" | "mother";

export type NodeListFilterRow = {
  node_type?: string | null;
  is_mother?: boolean;
  status?: string | null;
};

export function nodeListRole(node: NodeListFilterRow): "iran" | "exit" | "mother" {
  if (node.is_mother || ["mother", "core"].includes(String(node.node_type ?? "").toLowerCase())) {
    return "mother";
  }
  return String(node.node_type ?? "").toLowerCase() === "iran" ? "iran" : "exit";
}

export function matchesNodeListFilter(node: NodeListFilterRow, filter: NodeListFilter, status?: string | null): boolean {
  const role = nodeListRole(node);
  const currentStatus = String(status ?? node.status ?? "").trim().toLowerCase();
  switch (filter) {
    case "all": return true;
    case "iran": return role === "iran";
    case "exit": return role === "exit";
    case "mother": return role === "mother";
    case "online": return currentStatus === "online";
    case "offline": return ["offline", "inactive", "failed", "error"].includes(currentStatus);
    case "maintenance": return currentStatus === "maintenance";
    default: return false;
  }
}
