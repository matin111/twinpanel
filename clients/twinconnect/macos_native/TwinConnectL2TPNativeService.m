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
        svc=SCNetworkServiceCreate(prefs,iface);
        if (!svc) { result(@"error",@"L2TP_SERVICE_CREATE_FAILED"); break; }
        if (!SCNetworkServiceSetName(svc,(__bridge CFStringRef)ServiceName) ||
            !SCNetworkServiceEstablishDefaultConfiguration(svc)) {
            result(@"error",@"L2TP_SERVICE_DEFAULTS_FAILED"); break;
        }
        // No passwords or PSK in SystemConfiguration preferences.
        // Disable automatic full-tunnel route; external watchdog owns routing.
        NSDictionary *ppp=@{
            (__bridge NSString*)kSCPropNetPPPAuthName:profile[@"username"],
            (__bridge NSString*)kSCPropNetPPPCommRemoteAddress:profile[@"server"],
            (__bridge NSString*)kSCPropNetPPPOverridePrimary:@0
        };
        NSDictionary *ipsec=@{
            (__bridge NSString*)kSCPropNetIPSecAuthenticationMethod:
                (__bridge NSString*)kSCValNetIPSecAuthenticationMethodSharedSecret
        };
        if (!SCNetworkInterfaceSetConfiguration(iface,(__bridge CFDictionaryRef)ppp) ||
            !SCNetworkInterfaceSetExtendedConfiguration(iface,kSCEntNetIPSec,
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
    if (iface) CFRelease(iface);
    if (set) CFRelease(set);
    SCPreferencesUnlock(prefs);
    CFRelease(prefs);
    return code;
}

int main(int argc,const char *argv[]) {
    @autoreleasepool {
        if (argc!=2) {result(@"error",@"L2TP_OPERATION_NOT_ALLOWED");return 2;}
        NSString *arg=[NSString stringWithUTF8String:argv[1]];
        if ([arg isEqualToString:@"capabilities"]) return capabilities();
        if (![arg isEqualToString:@"prepare"]) {
            result(@"error",@"L2TP_OPERATION_NOT_ALLOWED"); return 2;
        }
        NSDictionary *profile=readProfile();
        if (!profile) {result(@"error",@"L2TP_PROFILE_INVALID");return 2;}
        return prepareService(profile);
    }
}
