"""Read-only per-node accounting evidence must never trust an ONLINE flag."""
from __future__ import annotations

from unittest import TestCase, main
from scripts.twinpanel_node_protocol_metering_matrix_v1 import build_matrix, classify_row


class MeteringMatrixTests(TestCase):
    def test_online_without_positive_bytes_is_unverified(self):
        status=classify_row(source="wireguard",online_flag="online",
            fresh_probe=True,positive_events=0,accepted_bytes=0,
            device_mismatch_events=0)
        self.assertEqual(status,"online_without_positive_metering_evidence")

    def test_stale_probe_never_counts_as_connected(self):
        status=classify_row(source="sudoku",online_flag="online",
            fresh_probe=False,positive_events=0,accepted_bytes=0,
            device_mismatch_events=0)
        self.assertEqual(status,"node_service_probe_stale_or_missing")

    def test_identity_mismatch_is_priority_over_positive_events(self):
        status=classify_row(source="xray",online_flag="online",
            fresh_probe=True,positive_events=5,accepted_bytes=500,
            device_mismatch_events=1)
        self.assertEqual(status,"identity_mismatch_in_ledger")

    def test_shadowtls_without_attribution_is_not_verified(self):
        status=classify_row(source="shadowtls",online_flag="online",
            fresh_probe=True,positive_events=0,accepted_bytes=0,
            device_mismatch_events=0)
        self.assertEqual(status,"shadowtls_source_attribution_unverified")

    def test_aliases_coalesce_and_no_customer_identifiers_escape(self):
        matrix=build_matrix(
            [{"node_id":1,"protocol":"cisco","status":"online","probe_fresh":True}],
            {(1,"cisco"):{"positive_events":2,"accepted_bytes":4096}},
        )
        self.assertEqual(matrix["registered_protocol_count"],16)
        self.assertEqual(matrix["pairs"][0]["protocol"],"cisco")
        self.assertEqual(matrix["pairs"][0]["recent_accepted_bytes"],4096)
        self.assertNotIn("subscription_id",matrix["pairs"][0])


if __name__ == "__main__":
    main()
