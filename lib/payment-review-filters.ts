/** Client-only, read-only payment review selectors. Never mutate payment states. */
export type PaymentReviewKind = "purchase" | "wallet";
export type PaymentReviewFilter =
  | "all"
  | PaymentReviewKind
  | "needs_review"
  | "new_receipts"
  | "purchase_review"
  | "wallet_review";

export type ReviewFilterRow = {
  kind: PaymentReviewKind;
  status: string;
  hasReceipt: boolean;
};

const finalStatuses = new Set([
  "approved", "auto_verified", "paid", "rejected", "completed", "fulfilled",
]);
const reviewStatuses = new Set([
  "awaiting_review", "payment_submitted", "submitted", "review", "waiting",
]);

export function needsPaymentReview(row: ReviewFilterRow): boolean {
  const status = row.status.toLowerCase();
  return !finalStatuses.has(status) && (
    reviewStatuses.has(status) || row.hasReceipt
  );
}

export function isNewPaymentReceipt(row: ReviewFilterRow): boolean {
  return row.hasReceipt && !finalStatuses.has(row.status.toLowerCase());
}

export function matchesPaymentReviewFilter(
  row: ReviewFilterRow,
  filter: PaymentReviewFilter,
): boolean {
  switch (filter) {
    case "all": return true;
    case "purchase": return row.kind === "purchase";
    case "wallet": return row.kind === "wallet";
    case "needs_review": return needsPaymentReview(row);
    case "new_receipts": return isNewPaymentReceipt(row);
    case "purchase_review":
      return row.kind === "purchase" && needsPaymentReview(row);
    case "wallet_review":
      return row.kind === "wallet" && needsPaymentReview(row);
    default: return false;
  }
}
