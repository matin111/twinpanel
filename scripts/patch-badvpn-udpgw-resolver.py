#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"BADVPN_PATCH_{label}_MATCHES={count}")
    return text.replace(old, new, 1)


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch-badvpn-udpgw-resolver.py PATH_TO_UDPGW_C")

    path = Path(sys.argv[1])
    source = path.read_text(encoding="utf-8")

    source = replace_once(
        source,
        """#ifndef BADVPN_USE_WINAPI
#include <base/BLog_syslog.h>
#include <arpa/nameser.h>
#include <resolv.h>
#endif
""",
        """#ifndef BADVPN_USE_WINAPI
#include <base/BLog_syslog.h>
#include <arpa/inet.h>
#include <arpa/nameser.h>
#include <resolv.h>
#endif
""",
        "INCLUDE",
    )

    source = replace_once(
        source,
        """static struct connection * find_connection (struct client *client, uint16_t conid);
static int uint16_comparator (void *unused, uint16_t *v1, uint16_t *v2);
static void maybe_update_dns (void);
""",
        """static struct connection * find_connection (struct client *client, uint16_t conid);
static int uint16_comparator (void *unused, uint16_t *v1, uint16_t *v2);
static int read_resolv_conf_dns (BAddr *out);
static void maybe_update_dns (void);
""",
        "PROTOTYPE",
    )

    old_dns = """void maybe_update_dns (void)
{
#ifndef BADVPN_USE_WINAPI
    btime_t now = btime_gettime();
    if (now < btime_add(last_dns_update_time, DNS_UPDATE_TIME)) {
        return;
    }
    last_dns_update_time = now;
    BLog(BLOG_DEBUG, \"update dns\");
    
    if (res_init() != 0) {
        BLog(BLOG_ERROR, \"res_init failed\");
        goto fail;
    }
    
    if (_res.nscount == 0) {
        BLog(BLOG_ERROR, \"no name servers available\");
        goto fail;
    }
    
    BAddr addr;
    BAddr_InitIPv4(&addr, _res.nsaddr_list[0].sin_addr.s_addr, hton16(53));
    
    if (!BAddr_Compare(&addr, &dns_addr)) {
        char str[BADDR_MAX_PRINT_LEN];
        BAddr_Print(&addr, str);
        BLog(BLOG_INFO, \"using DNS server %s\", str);
    }
    
    dns_addr = addr;
    return;
    
fail:
    BAddr_InitNone(&dns_addr);
#endif
}
"""

    new_dns = """static int read_resolv_conf_dns (BAddr *out)
{
#ifndef BADVPN_USE_WINAPI
    FILE *f = fopen(\"/etc/resolv.conf\", \"r\");
    if (!f) {
        return 0;
    }

    char line[512];
    while (fgets(line, sizeof(line), f)) {
        char key[32];
        char value[64];
        if (sscanf(line, \" %31s %63s\", key, value) != 2 || strcmp(key, \"nameserver\")) {
            continue;
        }

        struct in_addr ipv4;
        if (inet_pton(AF_INET, value, &ipv4) == 1) {
            BAddr_InitIPv4(out, ipv4.s_addr, hton16(53));
            fclose(f);
            return 1;
        }
    }

    fclose(f);
#endif
    return 0;
}

void maybe_update_dns (void)
{
#ifndef BADVPN_USE_WINAPI
    btime_t now = btime_gettime();
    if (now < btime_add(last_dns_update_time, DNS_UPDATE_TIME)) {
        return;
    }
    last_dns_update_time = now;
    BLog(BLOG_DEBUG, \"update dns\");

    BAddr addr;
    int resolver_ready = 0;

    if (res_init() == 0 && _res.nscount > 0) {
        BAddr_InitIPv4(&addr, _res.nsaddr_list[0].sin_addr.s_addr, hton16(53));
        resolver_ready = 1;
    } else {
        BLog(BLOG_WARNING, \"resolver state has no name server; trying /etc/resolv.conf fallback\");
        if (read_resolv_conf_dns(&addr)) {
            BLog(BLOG_NOTICE, \"loaded DNS server from /etc/resolv.conf fallback\");
            resolver_ready = 1;
        }
    }

    if (!resolver_ready) {
        BLog(BLOG_ERROR, \"no name servers available\");
        goto fail;
    }

    if (!BAddr_Compare(&addr, &dns_addr)) {
        char str[BADDR_MAX_PRINT_LEN];
        BAddr_Print(&addr, str);
        BLog(BLOG_INFO, \"using DNS server %s\", str);
    }

    dns_addr = addr;
    return;

fail:
    BAddr_InitNone(&dns_addr);
#endif
}
"""

    source = replace_once(source, old_dns, new_dns, "DNS_FUNCTION")

    path.write_text(source, encoding="utf-8")
    print("BADVPN_UDPGW_RESOLVER_PATCH_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
