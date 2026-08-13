#import "BroadcastBridge.h"
#import <CoreBluetooth/CoreBluetooth.h>

@interface BroadcastBridge () <CBPeripheralManagerDelegate>
@property CBPeripheralManager *manager;
@property NSString *name;
@property BOOL requested;
@property NSString *lastError;
@end

@implementation BroadcastBridge

+ (instancetype)shared {
    static BroadcastBridge *bridge;
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        void (^make)(void) = ^{
            bridge = [BroadcastBridge new];
        };
        if (NSThread.isMainThread) make();
        else dispatch_sync(dispatch_get_main_queue(), make);
    });
    return bridge;
}

- (instancetype)init {
    if (self = [super init]) {
        _name = @"Broadcast";
        _manager = [[CBPeripheralManager alloc]
            initWithDelegate:self
            queue:dispatch_get_main_queue()];
    }
    return self;
}

- (void)refresh {
    if (!self.requested ||
        self.manager.state != CBManagerStatePoweredOn)
        return;

    [self.manager stopAdvertising];
    [self.manager startAdvertising:@{
        CBAdvertisementDataLocalNameKey: self.name
    }];
}

- (void)advertiseName:(NSString *)name {
    dispatch_async(dispatch_get_main_queue(), ^{
        self.name = name.length ? name : @"Broadcast";
        self.requested = YES;
        self.lastError = nil;
        [self refresh];
    });
}

- (void)stopAdvertising {
    dispatch_async(dispatch_get_main_queue(), ^{
        self.requested = NO;
        [self.manager stopAdvertising];
    });
}

- (void)peripheralManagerDidUpdateState:
    (CBPeripheralManager *)peripheral
{
    [self refresh];
}

- (void)peripheralManagerDidStartAdvertising:
    (CBPeripheralManager *)peripheral
    error:(NSError *)error
{
    self.lastError = error.localizedDescription;
}

- (NSString *)statusLine {
    __block NSString *line;

    void (^read)(void) = ^{
        line = [NSString stringWithFormat:
            @"state=%ld advertising=%d name=%@ error=%@\n",
            (long)self.manager.state,
            self.manager.isAdvertising,
            self.name,
            self.lastError ?: @"none"];
    };

    if (NSThread.isMainThread)
        read();
    else
        dispatch_sync(dispatch_get_main_queue(), read);

    return line;
}

@end
