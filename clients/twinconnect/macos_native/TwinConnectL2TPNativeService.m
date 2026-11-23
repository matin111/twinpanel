// Unsigned macOS native L2TP service preparation. Does NOT start a VPN.
// The root-only create command stores only the selected server and username.
// Password and shared secret are NEVER persisted or passed as process args.
// A separate independent route watchdog is required BEFORE adding Connect.
#import <Foundation/Foundation.h>
#import <SystemConfiguration/SystemConfiguration.h>
#import <sys/stat.h>
#import <unistd.h>

static NSString *const ServiceName = @"TwinConnect L2TP";

static void result(NSString *state, NSString *reason) {
    NSDictionary *obj = @{@"state":state, @"reason":reason, @"connected":@NO};
    NSData *data = [NSJSONSerialization dataWithJSONObject:obj options:0 error:nil];
    if (data) {
        fwrite(data.bytes, 1, data.length, stdout);
        fputc('\n', stdout);
        fflush(stdout);
    }
}

static SCNetworkServiceRef findService(SCPreferencesRef prefs) {
    CFArrayRef list = SCNetworkServiceCopyAll(prefs);
    if (!list) return NULL;
    SCNetworkServiceRef found = NULL;
    for (CFIndex i=0; i<CFArrayGetCount(list); i++) {
        SCNetworkServiceRef item=(SCNetworkServiceRef)CFArrayGetValueAtIndex(list,i);
        CFStringRef name=SCNetworkServiceGetName(item);
        if (name && CFStringCompare(name, (__bridge CFStringRef)ServiceName, 0) == kCFCompareEqualTo) {
            if (found) {
                CFRelease(found);
                found=NULL;
                break;
            }
            found=(SCNetworkServiceRef)CFRetain(item);
        }
    }
    CFRelease(list);
    return found;
}

static BOOL safeText(id value, NSUInteger limit) {
    if (![value isKindOfClass:NSString.class]) return NO;
    NSString *s=(NSString*)value;
    if (!s.length || [s lengthOfBytesUsingEncoding:NSUTF8StringEncoding] > limit) return NO;
    NSCharacterSet *invalid=[NSCharacterSet controlCharacterSet];
    return [s rangeOfCharacterFromSet:invalid].location==NSNotFound;
}

static NSDictionary *readProfile(void) {
    NSMutableData *bytes=[NSMutableData data];
    unsigned char buffer[1024];
    while (bytes.length <= 4096) {
        ssize_t amount=read(STDIN_FILENO,buffer,sizeof(buffer));
        if (amount == 0) break;
        if (amount < 0) return nil;
        [bytes appendBytes:buffer length:(NSUInteger)amount];
        if (bytes.length > 4096) return nil;
    }
    if (!bytes.length) return nil;
    id object=[NSJSONSerialization JSONObjectWithData:bytes options:0 error:nil];
    if (![object isKindOfClass:NSDictionary.class]) return nil;
    NSDictionary *profile=(NSDictionary*)object;
    NSSet *keys=[NSSet setWithObjects:@"server",@"username",@"password",@"psk",nil];
    if (![keys isEqualToSet:[NSSet setWithArray:profile.allKeys]]) return nil;
    NSString *host=profile[@"server"];
    if (!safeText(host,253) || !safeText(profile[@"username"],256) ||
        !safeText(profile[@"password"],256) || !safeText(profile[@"psk"],256)) return nil;
    NSRegularExpression *reg=[NSRegularExpression regularExpressionWithPattern:
        @"^[A-Za-z0-9.-]{1,253}$" options:0 error:nil];
    if (![reg numberOfMatchesInString:host options:0 range:NSMakeRange(0,host.length)] ||
        [host hasPrefix:@"-"] || [host hasSuffix:@"."] ||
        [host containsString:@".."]) return nil;
    return profile;
}

static BOOL noParallelVPN(void) {
    // Refuse all changes if any independently guarded system VPN is active.
    for (NSString *path in @[
        @"/private/var/run/twinconnect-cisco-route-guard/state.json",
        @"/private/var/run/twinconnect-wireguard-route-guard/state.json",
        @"/private/var/run/twinconnect-full-route-guard/state.json"
    ]) {
        if ([[NSFileManager defaultManager] fileExistsAtPath:path]) return NO;
    }
    return YES;
}

static int capabilities(void) {
    SCNetworkInterfaceRef iface=SCNetworkInterfaceCreateWithInterface(
        kSCNetworkInterfaceIPv4,kSCNetworkInterfaceTypeL2TP);
    if (!iface) { result(@"error",@"L2TP_NATIVE_STACK_UNAVAILABLE"); return 2; }
    CFRelease(iface);
    SCPreferencesRef prefs=SCPreferencesCreate(NULL, CFSTR("TwinConnectL2TP"), NULL);
    if (!prefs) { result(@"error",@"L2TP_PREFERENCES_UNAVAILABLE"); return 2; }
    SCNetworkServiceRef item=findService(prefs);
    result(@"preflight", item ? @"L2TP_NATIVE_SERVICE_CONFIGURED" :
                          @"L2TP_NATIVE_SERVICE_NOT_CONFIGURED");
    if (item) CFRelease(item);
    CFRelease(prefs);
    return 0;
}

static int selftest(void) {
    // Construct a complete native service in the in-memory preferences view;
    // do not call SCPreferencesCommitChanges/ApplyChanges, connect or touch
    // network routes. This verifies the native API accepts our settings.
    SCPreferencesRef prefs=SCPreferencesCreate(NULL, CFSTR("TwinConnectL2TPTest"), NULL);
    if (!prefs) {result(@"error",@"L2TP_PREFS_MEMORY_TEST_FAILED");return 2;}
    if (!SCPreferencesLock(prefs,TRUE)) {
        result(@"error",@"L2TP_PREFS_TEST_LOCK_FAILED");
        CFRelease(prefs); return 2;
    }
    SCNetworkInterfaceRef iface=SCNetworkInterfaceCreateWithInterface(
        kSCNetworkInterfaceIPv4,kSCNetworkInterfaceTypeL2TP);
    if (!iface) {
        result(@"error",@"L2TP_NATIVE_INTERFACE_UNAVAILABLE");
        SCPreferencesUnlock(prefs);
        CFRelease(prefs); return 2;
    }
    // A native L2TP service is PPP layered over L2TP layered over IPv4.
    // SCNetworkServiceCreate rejects the L2TP bottom interface (SCError 1002).
    SCNetworkInterfaceRef pppInterface=SCNetworkInterfaceCreateWithInterface(
        iface,kSCNetworkInterfaceTypePPP);
    if (!pppInterface) {
        result(@"error",@"L2TP_NATIVE_PPP_INTERFACE_UNAVAILABLE");
        CFRelease(iface);
        SCPreferencesUnlock(prefs);
        CFRelease(prefs);
        return 2;
    }
    SCNetworkServiceRef service=SCNetworkServiceCreate(prefs,pppInterface);
    BOOL good=service != NULL;
    if (!good) {
        result(@"error",[NSString stringWithFormat:@"L2TP_NATIVE_SERVICE_ERROR_%d",SCError()]);
    } else {
        good=SCNetworkServiceEstablishDefaultConfiguration(service);
        if (!good) result(@"error",@"L2TP_NATIVE_SERVICE_DEFAULTS_REJECTED");
    }
    if (good) {
        NSDictionary *ppp=@{
            (__bridge NSString*)kSCPropNetPPPAuthName:@"TWINCONNECT_PROBE_ONLY",
            (__bridge NSString*)kSCPropNetPPPCommRemoteAddress:@"198.51.100.11"
        };
        NSDictionary *ipsec=@{
            (__bridge NSString*)kSCPropNetIPSecAuthenticationMethod:
                (__bridge NSString*)kSCValNetIPSecAuthenticationMethodSharedSecret
        };
        SCNetworkInterfaceRef servicePPP=SCNetworkServiceGetInterface(service);
        BOOL pppAccepted=servicePPP && SCNetworkInterfaceSetConfiguration(
            servicePPP,(__bridge CFDictionaryRef)ppp);
        BOOL ipsecAccepted=servicePPP && SCNetworkInterfaceSetExtendedConfiguration(
            servicePPP,kSCEntNetIPSec,(__bridge CFDictionaryRef)ipsec);
        if (!pppAccepted) {
            result(@"error",@"L2TP_NATIVE_PPP_SETTINGS_REJECTED");
            good=NO;
        } else if (!ipsecAccepted) {
            result(@"error",@"L2TP_NATIVE_IPSEC_SETTINGS_REJECTED");
            good=NO;
        } else {
            good=YES;
        }
    }
    if (service) {SCNetworkServiceRemove(service);CFRelease(service);}
    CFRelease(pppInterface);
    CFRelease(iface);
    SCPreferencesUnlock(prefs);
    CFRelease(prefs);
    if (good) result(@"tested",@"L2TP_NATIVE_SETTINGS_ACCEPTED_NO_COMMIT");
    return good?0:2;
}

static int prepareService(NSDictionary *profile) {
    if (geteuid()!=0) {
        result(@"error",@"L2TP_ROOT_REQUIRED");
        return 2;
    }
    if (!noParallelVPN()) {
        result(@"error",@"L2TP_OTHER_VPN_ACTIVE");
        return 2;
    }
    SCPreferencesRef prefs=SCPreferencesCreate(NULL, CFSTR("TwinConnectL2TP"), NULL);
    if (!prefs || !SCPreferencesLock(prefs,TRUE)) {
        result(@"error",@"L2TP_PREFERENCES_LOCK_FAILED");
        if(prefs) CFRelease(prefs);
        return 2;
    }
    int code=2;
    SCNetworkServiceRef svc=NULL;
    SCNetworkSetRef set=SCNetworkSetCopyCurrent(prefs);
    SCNetworkInterfaceRef iface=NULL;
    SCNetworkInterfaceRef pppInterface=NULL;
    do {
        if (!set) { result(@"error",@"L2TP_NETWORK_SET_UNAVAILABLE"); break; }
        SCNetworkServiceRef existing=findService(prefs);
        if (existing) {
            CFRelease(existing);
            result(@"error",@"L2TP_EXISTING_SERVICE_REQUIRES_REVIEW");
            break;
        }
        iface=SCNetworkInterfaceCreateWithInterface(kSCNetworkInterfaceIPv4,
                                                   kSCNetworkInterfaceTypeL2TP);
        if (!iface) { result(@"error",@"L2TP_NATIVE_INTERFACE_UNAVAILABLE"); break; }
        pppInterface=SCNetworkInterfaceCreateWithInterface(
            iface,kSCNetworkInterfaceTypePPP);
        if (!pppInterface) {
            result(@"error",@"L2TP_NATIVE_PPP_INTERFACE_UNAVAILABLE"); break;
        }
        svc=SCNetworkServiceCreate(prefs,pppInterface);
        if (!svc) { result(@"error",@"L2TP_SERVICE_CREATE_FAILED"); break; }
        if (!SCNetworkServiceSetName(svc,(__bridge CFStringRef)ServiceName) ||
            !SCNetworkServiceEstablishDefaultConfiguration(svc)) {
            result(@"error",@"L2TP_SERVICE_DEFAULTS_FAILED"); break;
        }
        // No passwords or PSK in SystemConfiguration preferences.
        // Disable automatic full-tunnel route; external watchdog owns routing.
        NSDictionary *ppp=@{
            (__bridge NSString*)kSCPropNetPPPAuthName:profile[@"username"],
            (__bridge NSString*)kSCPropNetPPPCommRemoteAddress:profile[@"server"]
        };
        NSDictionary *ipsec=@{
            (__bridge NSString*)kSCPropNetIPSecAuthenticationMethod:
                (__bridge NSString*)kSCValNetIPSecAuthenticationMethodSharedSecret
        };
        SCNetworkInterfaceRef servicePPP=SCNetworkServiceGetInterface(svc);
        if (!servicePPP ||
            !SCNetworkInterfaceSetConfiguration(servicePPP,(__bridge CFDictionaryRef)ppp) ||
            !SCNetworkInterfaceSetExtendedConfiguration(servicePPP,kSCEntNetIPSec,
                                                         (__bridge CFDictionaryRef)ipsec) ||
            !SCNetworkSetAddService(set,svc)) {
            result(@"error",@"L2TP_SERVICE_SETTINGS_REJECTED"); break;
        }
        if (!SCPreferencesCommitChanges(prefs) || !SCPreferencesApplyChanges(prefs)) {
            result(@"error",@"L2TP_SERVICE_COMMIT_FAILED"); break;
        }
        result(@"prepared",@"L2TP_SERVICE_PREPARED_NO_VPN_CONNECTED");
        code=0;
    } while (0);
    if (code && svc) SCNetworkServiceRemove(svc);
    if (svc) CFRelease(svc);
    if (pppInterface) CFRelease(pppInterface);
    if (iface) CFRelease(iface);
    if (set) CFRelease(set);
    SCPreferencesUnlock(prefs);
    CFRelease(prefs);
    return code;
}

static SCNetworkConnectionRef l2tpConnection(void) {
    SCPreferencesRef prefs=SCPreferencesCreate(NULL, CFSTR("TwinConnectL2TP"), NULL);
    if (!prefs) return NULL;
    SCNetworkServiceRef svc=findService(prefs);
    SCNetworkConnectionRef conn=NULL;
    if (svc) {
        CFStringRef identifier=SCNetworkServiceGetServiceID(svc);
        if (identifier) conn=SCNetworkConnectionCreateWithServiceID(
            NULL,identifier,NULL,NULL);
        CFRelease(svc);
    }
    CFRelease(prefs);
    return conn;
}

static int currentStatus(void) {
    SCNetworkConnectionRef conn=l2tpConnection();
    if (!conn) { result(@"offline",@"L2TP_NATIVE_SERVICE_NOT_CONFIGURED"); return 0; }
    SCNetworkConnectionStatus state=SCNetworkConnectionGetStatus(conn);
    NSString *name=@"L2TP_NATIVE_STATUS_UNKNOWN";
    if (state==kSCNetworkConnectionConnected) name=@"L2TP_NATIVE_LINK_CONNECTED_UNROUTED";
    else if (state==kSCNetworkConnectionConnecting) name=@"L2TP_NATIVE_LINK_CONNECTING";
    else if (state==kSCNetworkConnectionDisconnected) name=@"L2TP_NATIVE_LINK_DISCONNECTED";
    else if (state==kSCNetworkConnectionDisconnecting) name=@"L2TP_NATIVE_LINK_DISCONNECTING";
    result(state==kSCNetworkConnectionConnected ? @"link" : @"offline",name);
    CFRelease(conn);
    return 0;
}

static int stopService(void) {
    if (geteuid()!=0) { result(@"error",@"L2TP_ROOT_REQUIRED"); return 2; }
    SCNetworkConnectionRef conn=l2tpConnection();
    if (!conn) { result(@"offline",@"L2TP_NATIVE_SERVICE_NOT_CONFIGURED"); return 0; }
    SCNetworkConnectionStatus old=SCNetworkConnectionGetStatus(conn);
    if (old==kSCNetworkConnectionDisconnected) {
        result(@"offline",@"L2TP_NATIVE_LINK_DISCONNECTED");
        CFRelease(conn);
        return 0;
    }
    BOOL ok=SCNetworkConnectionStop(conn,TRUE);
    CFRelease(conn);
    result(ok?@"stopping":@"error",
           ok?@"L2TP_NATIVE_DISCONNECT_REQUESTED":@"L2TP_NATIVE_DISCONNECT_FAILED");
    return ok?0:2;
}

static BOOL routeWatchdogArmed(void) {
    NSString *path=@"/private/var/run/twinconnect-l2tp-route-guard/state.json";
    struct stat info;
    if (lstat(path.UTF8String,&info)!=0 || !S_ISREG(info.st_mode) ||
        info.st_uid!=0 || (info.st_mode & 0077)!=0 || info.st_nlink!=1 ||
        info.st_size>8192) return NO;
    NSData *data=[NSData dataWithContentsOfFile:path];
    NSDictionary *obj=[NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
    if (![obj isKindOfClass:NSDictionary.class]) return NO;
    if (![obj[@"mode"] isEqual:@"armed"]) return NO;
    NSNumber *deadline=obj[@"deadline"];
    return [deadline isKindOfClass:NSNumber.class] &&
        deadline.doubleValue > [[NSDate date] timeIntervalSince1970];
}

static int connectService(NSDictionary *profile) {
    if (geteuid()!=0 || !noParallelVPN() || !routeWatchdogArmed()) {
        result(@"error",@"L2TP_INDEPENDENT_ROUTE_GUARD_REQUIRED");
        return 2;
    }
    SCNetworkConnectionRef conn=l2tpConnection();
    if (!conn) { result(@"error",@"L2TP_NATIVE_SERVICE_NOT_CONFIGURED"); return 2; }
    if (SCNetworkConnectionGetStatus(conn)!=kSCNetworkConnectionDisconnected) {
        result(@"error",@"L2TP_NATIVE_SERVICE_BUSY");
        CFRelease(conn);
        return 2;
    }
    // Credentials are in-memory only. The host/IP and username were
    // stored by prepare; no password or PSK is saved in preferences.
    NSDictionary *options=@{
        (__bridge NSString*)kSCEntNetPPP:@{
            (__bridge NSString*)kSCPropNetPPPAuthName:profile[@"username"],
            (__bridge NSString*)kSCPropNetPPPAuthPassword:profile[@"password"]
        },
        (__bridge NSString*)kSCEntNetL2TP:@{
            (__bridge NSString*)kSCPropNetL2TPIPSecSharedSecret:profile[@"psk"],
            (__bridge NSString*)kSCPropNetL2TPTransport:
                (__bridge NSString*)kSCValNetL2TPTransportIPSec
        },
        (__bridge NSString*)kSCEntNetIPSec:@{
            (__bridge NSString*)kSCPropNetIPSecAuthenticationMethod:
                (__bridge NSString*)kSCValNetIPSecAuthenticationMethodSharedSecret,
            (__bridge NSString*)kSCPropNetIPSecSharedSecret:profile[@"psk"]
        }
    };
    BOOL ok=SCNetworkConnectionStart(conn,(__bridge CFDictionaryRef)options,TRUE);
    if (!ok) {
        result(@"error",@"L2TP_NATIVE_START_REJECTED");
        CFRelease(conn);
        return 2;
    }
    // Establishing PPP is not proof of tunneled Internet. A separate guard
    // must test traffic and apply verified routing before UI shows Connected.
    result(@"starting",@"L2TP_NATIVE_HANDSHAKE_STARTED_NOT_CONNECTED");
    CFRelease(conn);
    return 0;
}

int main(int argc,const char *argv[]) {
    @autoreleasepool {
        if (argc!=2) {result(@"error",@"L2TP_OPERATION_NOT_ALLOWED");return 2;}
        NSString *arg=[NSString stringWithUTF8String:argv[1]];
        if ([arg isEqualToString:@"capabilities"]) return capabilities();
        if ([arg isEqualToString:@"selftest"]) return selftest();
        if ([arg isEqualToString:@"status"]) return currentStatus();
        if ([arg isEqualToString:@"stop"]) return stopService();
        if (![arg isEqualToString:@"prepare"] && ![arg isEqualToString:@"start"]) {
            result(@"error",@"L2TP_OPERATION_NOT_ALLOWED"); return 2;
        }
        NSDictionary *profile=readProfile();
        if (!profile) {result(@"error",@"L2TP_PROFILE_INVALID");return 2;}
        return [arg isEqualToString:@"prepare"] ?
            prepareService(profile) : connectService(profile);
    }
}
