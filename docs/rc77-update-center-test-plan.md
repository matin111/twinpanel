# rc.77 real-server acceptance

Final acceptance must be performed on TwinPanel test server `217.179.6.142` after public release installation.

1. Complete the in-panel update to rc.77 and allow the automatic refresh.
2. Verify the System Update Center is not left open after the refresh.
3. Open the System Update Center manually and verify the header/close button and footer/actions are all reachable without any part of the card escaping the viewport.
4. Reduce the browser height and repeat step 3; only the card interior should scroll.
5. During a future active update, a manual page refresh must still recover progress from backend release status rather than from a stale client marker.

Do not mark the issue solved until the real-server checks pass.
