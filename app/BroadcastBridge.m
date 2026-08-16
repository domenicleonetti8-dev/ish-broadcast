#import "BroadcastBridge.h"
#import <CoreBluetooth/CoreBluetooth.h>
#import <AVFoundation/AVFoundation.h>

static const NSUInteger BroadcastMaximumFingers = 5;

@interface BroadcastBridge () <CBPeripheralManagerDelegate, CBCentralManagerDelegate>
@property CBPeripheralManager *peripheralManager;
@property CBCentralManager *centralManager;
@property NSString *name;
@property BOOL requested;
@property NSString *lastError;
@property NSMutableDictionary<NSUUID *, CBPeripheral *> *discovered;
@property NSMutableOrderedSet<NSUUID *> *fingerIdentifiers;
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
        _discovered = [NSMutableDictionary dictionary];
        _fingerIdentifiers = [NSMutableOrderedSet orderedSet];
        _peripheralManager = [[CBPeripheralManager alloc]
            initWithDelegate:self
            queue:dispatch_get_main_queue()];
        _centralManager = [[CBCentralManager alloc]
            initWithDelegate:self
            queue:dispatch_get_main_queue()];
    }
    return self;
}

- (void)refresh {
    if (!self.requested ||
        self.peripheralManager.state != CBManagerStatePoweredOn)
        return;

    [self.peripheralManager stopAdvertising];
    [self.peripheralManager startAdvertising:@{
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
        [self.peripheralManager stopAdvertising];
    });
}

- (void)startScan {
    dispatch_async(dispatch_get_main_queue(), ^{
        if (self.centralManager.state != CBManagerStatePoweredOn) {
            self.lastError = @"bluetooth_not_powered_on";
            return;
        }
        self.lastError = nil;
        [self.centralManager scanForPeripheralsWithServices:nil options:@{
            CBCentralManagerScanOptionAllowDuplicatesKey: @NO
        }];
    });
}

- (void)stopScan {
    dispatch_async(dispatch_get_main_queue(), ^{
        [self.centralManager stopScan];
    });
}

- (BOOL)bindFinger:(NSString *)identifier error:(NSString **)error {
    __block BOOL accepted = NO;
    void (^bind)(void) = ^{
        NSUUID *uuid = [[NSUUID alloc] initWithUUIDString:identifier];
        CBPeripheral *device = uuid ? self.discovered[uuid] : nil;
        if (!device) {
            if (error) *error = @"unknown_device";
            return;
        }
        if (![self.fingerIdentifiers containsObject:uuid] &&
            self.fingerIdentifiers.count >= BroadcastMaximumFingers) {
            if (error) *error = @"finger_limit_reached";
            return;
        }
        [self.fingerIdentifiers addObject:uuid];
        [self.centralManager connectPeripheral:device options:nil];
        accepted = YES;
    };
    if (NSThread.isMainThread) bind();
    else dispatch_sync(dispatch_get_main_queue(), bind);
    return accepted;
}

- (BOOL)unbindFinger:(NSString *)identifier error:(NSString **)error {
    __block BOOL accepted = NO;
    void (^unbind)(void) = ^{
        NSUUID *uuid = [[NSUUID alloc] initWithUUIDString:identifier];
        CBPeripheral *device = uuid ? self.discovered[uuid] : nil;
        if (!uuid || ![self.fingerIdentifiers containsObject:uuid]) {
            if (error) *error = @"finger_not_bound";
            return;
        }
        [self.fingerIdentifiers removeObject:uuid];
        if (device) [self.centralManager cancelPeripheralConnection:device];
        accepted = YES;
    };
    if (NSThread.isMainThread) unbind();
    else dispatch_sync(dispatch_get_main_queue(), unbind);
    return accepted;
}

- (void)peripheralManagerDidUpdateState:
    (CBPeripheralManager *)peripheral
{
    [self refresh];
}

- (void)centralManagerDidUpdateState:(CBCentralManager *)central {
    if (central.state == CBManagerStatePoweredOn)
        self.lastError = nil;
}

- (void)centralManager:(CBCentralManager *)central
 didDiscoverPeripheral:(CBPeripheral *)peripheral
     advertisementData:(NSDictionary<NSString *, id> *)advertisementData
                  RSSI:(NSNumber *)RSSI
{
    self.discovered[peripheral.identifier] = peripheral;
}

- (void)centralManager:(CBCentralManager *)central
    didFailToConnectPeripheral:(CBPeripheral *)peripheral
                         error:(NSError *)error
{
    self.lastError = error.localizedDescription ?: @"connect_failed";
    if ([self.fingerIdentifiers containsObject:peripheral.identifier])
        [central connectPeripheral:peripheral options:nil];
}

- (void)centralManager:(CBCentralManager *)central
 didDisconnectPeripheral:(CBPeripheral *)peripheral
                    error:(NSError *)error
{
    if (error) self.lastError = error.localizedDescription;
    if ([self.fingerIdentifiers containsObject:peripheral.identifier])
        [central connectPeripheral:peripheral options:nil];
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
        NSMutableArray *devices = [NSMutableArray array];
        for (NSUUID *uuid in self.discovered) {
            CBPeripheral *device = self.discovered[uuid];
            [devices addObject:@{
                @"id": uuid.UUIDString,
                @"name": device.name ?: @"unknown",
                @"state": @(device.state),
                @"finger": @([self.fingerIdentifiers containsObject:uuid])
            }];
        }
        AVAudioSessionRouteDescription *route = AVAudioSession.sharedInstance.currentRoute;
        NSMutableArray *outputs = [NSMutableArray array];
        for (AVAudioSessionPortDescription *port in route.outputs)
            [outputs addObject:@{
                @"name": port.portName ?: @"unknown",
                @"type": port.portType ?: @"unknown"
            }];
        NSDictionary *status = @{
            @"name": self.name,
            @"advertising": @(self.peripheralManager.isAdvertising),
            @"scanning": @(self.centralManager.isScanning),
            @"maximum_fingers": @(BroadcastMaximumFingers),
            @"fingers": @(self.fingerIdentifiers.count),
            @"devices": devices,
            @"audio_outputs": outputs,
            @"error": self.lastError ?: [NSNull null]
        };
        NSData *json = [NSJSONSerialization dataWithJSONObject:status options:0 error:nil];
        line = [[NSString alloc] initWithData:json encoding:NSUTF8StringEncoding];
        line = [line stringByAppendingString:@"\n"];
    };

    if (NSThread.isMainThread)
        read();
    else
        dispatch_sync(dispatch_get_main_queue(), read);

    return line;
}

@end
