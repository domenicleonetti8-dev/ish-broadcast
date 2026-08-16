#import "BroadcastBridge.h"
#import "BroadcastAudioRouter.h"
#import "BroadcastFingerTable.h"
#import "BroadcastHealth.h"

#import <AVFoundation/AVFoundation.h>
#import <CoreBluetooth/CoreBluetooth.h>
#import <math.h>

static NSString * const BroadcastSavedFingerIdentifiers =
    @"BroadcastSavedFingerIdentifiers";
static NSString * const BroadcastPrefersMultidevice =
    @"BroadcastPrefersMultidevice";
static NSString * const BroadcastLogicalName = @"broadcast";
static NSString * const BroadcastControlServiceUUID =
    @"B0ADC0DE-0000-4F1A-9000-000000000001";
static NSString * const BroadcastStatusCharacteristicUUID =
    @"B0ADC0DE-0000-4F1A-9000-000000000002";
static const NSUInteger BroadcastMaximumEvents = 64;

@interface BroadcastBridge () <CBPeripheralManagerDelegate> {
    struct broadcast_finger_table _fingers;
}
@property (nonatomic, strong) CBPeripheralManager *peripheralManager;
@property (nonatomic, strong) BroadcastAudioRouter *audioRouter;
@property (nonatomic, copy) NSString *name;
@property (nonatomic) BOOL requested;
@property (nonatomic) BOOL routeMonitoring;
@property (nonatomic, copy) NSString *lastError;
@property (nonatomic, strong) CBMutableService *controlService;
@property (nonatomic, strong) CBMutableCharacteristic *statusCharacteristic;
@property (nonatomic, strong) NSMutableDictionary<NSUUID *, NSData *> *statusReads;
@property (nonatomic) BOOL controlServiceReady;
@property (nonatomic, strong) NSMutableArray<NSDictionary<NSString *, id> *> *events;
@property (nonatomic, copy) NSString *lastProbeResult;
@property (nonatomic, strong) NSNumber *lastProbeTimestampMs;
@end

@implementation BroadcastBridge

+ (instancetype)shared {
    static BroadcastBridge *bridge;
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        bridge = [BroadcastBridge new];
    });
    return bridge;
}

- (instancetype)init {
    self = [super init];
    if (self) {
        _name = BroadcastLogicalName;
        _audioRouter = [BroadcastAudioRouter new];
        if ([NSUserDefaults.standardUserDefaults
            objectForKey:BroadcastPrefersMultidevice] != nil) {
            _audioRouter.prefersMultidevice =
                [NSUserDefaults.standardUserDefaults
                    boolForKey:BroadcastPrefersMultidevice];
        }
        broadcast_fingers_init(&_fingers);
        [self restoreSavedFingerRecords];
        _statusReads = [NSMutableDictionary dictionary];
        _events = [NSMutableArray array];
        _lastProbeResult = @"never";
        _peripheralManager = [[CBPeripheralManager alloc]
            initWithDelegate:self
            queue:dispatch_get_main_queue()
            options:@{
                CBPeripheralManagerOptionShowPowerAlertKey: @YES,
            }];
        [NSNotificationCenter.defaultCenter
            addObserver:self
               selector:@selector(audioRouteDidChange:)
                   name:AVAudioSessionRouteChangeNotification
                 object:AVAudioSession.sharedInstance];
        [NSNotificationCenter.defaultCenter
            addObserver:self
               selector:@selector(audioSessionInterrupted:)
                   name:AVAudioSessionInterruptionNotification
                 object:AVAudioSession.sharedInstance];
        [NSNotificationCenter.defaultCenter
            addObserver:self
               selector:@selector(audioMediaServicesReset:)
                   name:AVAudioSessionMediaServicesWereResetNotification
                 object:AVAudioSession.sharedInstance];
        [self recordEvent:@"bridge_initialized" detail:nil];
    }
    return self;
}

- (void)dealloc {
    [NSNotificationCenter.defaultCenter removeObserver:self];
}

- (uint64_t)nowMilliseconds {
    return (uint64_t)(NSProcessInfo.processInfo.systemUptime * 1000.0);
}

- (NSNumber *)wallClockMilliseconds {
    return @((uint64_t)(NSDate.date.timeIntervalSince1970 * 1000.0));
}

- (void)recordEvent:(NSString *)name detail:(NSString *)detail {
    if (!NSThread.isMainThread) {
        dispatch_async(dispatch_get_main_queue(), ^{
            [self recordEvent:name detail:detail];
        });
        return;
    }
    if (!name.length)
        return;
    NSMutableDictionary<NSString *, id> *event = [@{
        @"event": name,
        @"timestamp_ms": [self wallClockMilliseconds],
    } mutableCopy];
    if (detail.length)
        event[@"detail"] = detail;
    while (self.events.count >= BroadcastMaximumEvents)
        [self.events removeObjectAtIndex:0];
    [self.events addObject:event];
}

- (NSString *)bluetoothStateName {
    switch (self.peripheralManager.state) {
        case CBManagerStateUnknown: return @"unknown";
        case CBManagerStateResetting: return @"resetting";
        case CBManagerStateUnsupported: return @"unsupported";
        case CBManagerStateUnauthorized: return @"unauthorized";
        case CBManagerStatePoweredOff: return @"powered_off";
        case CBManagerStatePoweredOn: return @"powered_on";
    }
    return @"unknown";
}

- (NSString *)messageForFingerResult:(int)result {
    switch (result) {
        case BROADCAST_FINGER_NOT_FOUND: return @"unknown_audio_output";
        case BROADCAST_FINGER_LIMIT_REACHED: return @"finger_limit_reached";
        case BROADCAST_FINGER_TABLE_FULL: return @"audio_output_table_full";
        case BROADCAST_FINGER_INVALID: return @"invalid_finger_state";
        default: return @"finger_operation_failed";
    }
}

- (void)persistWantedFingers {
    NSMutableArray<NSString *> *identifiers = [NSMutableArray array];
    for (size_t i = 0; i < _fingers.count; i++) {
        struct broadcast_finger *finger = &_fingers.devices[i];
        if (finger->wanted)
            [identifiers addObject:
                [NSString stringWithUTF8String:finger->identifier]];
    }
    [NSUserDefaults.standardUserDefaults
        setObject:identifiers
        forKey:BroadcastSavedFingerIdentifiers];
}

- (void)restoreSavedFingerRecords {
    NSArray<NSString *> *saved = [NSUserDefaults.standardUserDefaults
        stringArrayForKey:BroadcastSavedFingerIdentifiers];
    for (NSString *identifier in saved) {
        if (!identifier.length)
            continue;
        broadcast_fingers_observe(
            &_fingers, identifier.UTF8String, "saved audio output"
        );
        broadcast_fingers_bind(&_fingers, identifier.UTF8String);
    }
}

- (BOOL)isExternalOutput:(AVAudioSessionPortDescription *)port {
    return ![port.portType isEqualToString:AVAudioSessionPortBuiltInSpeaker] &&
        ![port.portType isEqualToString:AVAudioSessionPortBuiltInReceiver];
}

- (NSSet<NSString *> *)activeOutputUIDs {
    NSMutableSet<NSString *> *identifiers = [NSMutableSet set];
    for (AVAudioSessionPortDescription *port in
         AVAudioSession.sharedInstance.currentRoute.outputs) {
        if (port.UID.length)
            [identifiers addObject:port.UID];
    }
    return identifiers;
}

- (void)synchronizeAudioRoute {
    if (!self.requested || !self.audioRouter.isRunning)
        return;

    NSArray<AVAudioSessionPortDescription *> *outputs =
        AVAudioSession.sharedInstance.currentRoute.outputs;
    NSMutableSet<NSString *> *active = [NSMutableSet set];
    BOOL changedWanted = NO;

    for (AVAudioSessionPortDescription *port in outputs) {
        if (!port.UID.length)
            continue;
        [active addObject:port.UID];
        BOOL known = broadcast_fingers_find(
            &_fingers, port.UID.UTF8String
        ) != NULL;
        int observeResult = broadcast_fingers_observe(
            &_fingers,
            port.UID.UTF8String,
            port.portName.UTF8String
        );
        if (observeResult != BROADCAST_FINGER_OK)
            continue;

        const struct broadcast_finger *finger = broadcast_fingers_find(
            &_fingers, port.UID.UTF8String
        );
        if (!known && [self isExternalOutput:port] &&
            finger && !finger->wanted &&
            broadcast_fingers_wanted_count(&_fingers) <
                BROADCAST_MAX_FINGERS) {
            if (broadcast_fingers_bind(
                &_fingers, port.UID.UTF8String
            ) == BROADCAST_FINGER_OK)
                changedWanted = YES;
        }
        finger = broadcast_fingers_find(&_fingers, port.UID.UTF8String);
        if (finger && finger->wanted)
            broadcast_fingers_connected(
                &_fingers, port.UID.UTF8String
            );
    }

    NSMutableSet<NSString *> *enabled = [NSMutableSet set];
    uint64_t now = [self nowMilliseconds];
    for (size_t i = 0; i < _fingers.count; i++) {
        struct broadcast_finger *finger = &_fingers.devices[i];
        if (!finger->wanted)
            continue;
        NSString *identifier = [NSString
            stringWithUTF8String:finger->identifier];
        if ([active containsObject:identifier]) {
            [enabled addObject:identifier];
        } else if (finger->state == BROADCAST_FINGER_BOUND ||
                   finger->state == BROADCAST_FINGER_CONNECTING) {
            broadcast_fingers_disconnected(
                &_fingers, finger->identifier, now
            );
        }
    }

    if (changedWanted)
        [self persistWantedFingers];
    [self.audioRouter setEnabledOutputUIDs:enabled];
    NSError *routeError = nil;
    if (![self.audioRouter rebuildRouteWithError:&routeError]) {
        self.lastError = routeError.localizedDescription;
        [self recordEvent:@"route_rebuild_failed"
                   detail:self.lastError];
    } else {
        self.lastError = nil;
        [self recordEvent:@"route_synchronized"
                   detail:[NSString stringWithFormat:
            @"active=%lu mapped_channels=%lu",
            (unsigned long)enabled.count,
            (unsigned long)self.audioRouter.mappedChannels]];
    }
}

- (void)refreshAdvertisement {
    if (!self.requested ||
        self.peripheralManager.state != CBManagerStatePoweredOn ||
        !self.controlServiceReady)
        return;

    [self.peripheralManager stopAdvertising];
    [self.peripheralManager startAdvertising:@{
        CBAdvertisementDataLocalNameKey: BroadcastLogicalName,
        CBAdvertisementDataServiceUUIDsKey: @[
            [CBUUID UUIDWithString:BroadcastControlServiceUUID]
        ],
    }];
}

- (void)configureControlService {
    self.controlServiceReady = NO;
    [self.statusReads removeAllObjects];
    [self.peripheralManager removeAllServices];
    CBUUID *statusUUID = [CBUUID
        UUIDWithString:BroadcastStatusCharacteristicUUID];
    self.statusCharacteristic = [[CBMutableCharacteristic alloc]
        initWithType:statusUUID
          properties:CBCharacteristicPropertyRead
               value:nil
         permissions:CBAttributePermissionsReadable];
    self.controlService = [[CBMutableService alloc]
        initWithType:[CBUUID UUIDWithString:BroadcastControlServiceUUID]
             primary:YES];
    self.controlService.characteristics = @[self.statusCharacteristic];
    [self.peripheralManager addService:self.controlService];
}

- (void)advertiseName:(NSString *)name {
    (void)name;
    [self startBroadcast];
}

- (void)startBroadcast {
    void (^start)(void) = ^{
        self.name = BroadcastLogicalName;
        self.requested = YES;
        self.routeMonitoring = YES;
        self.lastError = nil;
        [self recordEvent:@"broadcast_start_requested" detail:nil];
        [self refreshAdvertisement];

        NSError *audioError = nil;
        if (![self.audioRouter startWithError:&audioError]) {
            self.lastError = audioError.localizedDescription;
            [self recordEvent:@"audio_start_failed"
                       detail:self.lastError];
            self.requested = NO;
            self.routeMonitoring = NO;
            [self.peripheralManager stopAdvertising];
            return;
        }
        [self synchronizeAudioRoute];
        if (self.audioRouter.isRunning) {
            [self recordEvent:@"broadcast_started"
                       detail:self.audioRouter.sessionMode];
        } else {
            [self recordEvent:@"broadcast_start_incomplete"
                       detail:self.lastError];
        }
    };
    if (NSThread.isMainThread)
        start();
    else
        dispatch_sync(dispatch_get_main_queue(), start);
}

- (void)stopAdvertising {
    void (^stop)(void) = ^{
        self.requested = NO;
        self.routeMonitoring = NO;
        [self.peripheralManager stopAdvertising];
        [self.audioRouter stop];
        [self recordEvent:@"broadcast_stopped" detail:nil];
    };
    if (NSThread.isMainThread)
        stop();
    else
        dispatch_sync(dispatch_get_main_queue(), stop);
}

- (void)startScan {
    void (^start)(void) = ^{
        self.routeMonitoring = YES;
        if (self.requested)
            [self synchronizeAudioRoute];
    };
    if (NSThread.isMainThread)
        start();
    else
        dispatch_sync(dispatch_get_main_queue(), start);
}

- (void)stopScan {
    void (^stop)(void) = ^{
        self.routeMonitoring = NO;
    };
    if (NSThread.isMainThread)
        stop();
    else
        dispatch_sync(dispatch_get_main_queue(), stop);
}

- (BOOL)bindFinger:(NSString *)identifier error:(NSString **)error {
    __block BOOL accepted = NO;
    void (^bind)(void) = ^{
        int result = broadcast_fingers_bind(
            &self->_fingers, identifier.UTF8String
        );
        if (result != BROADCAST_FINGER_OK) {
            if (error) *error = [self messageForFingerResult:result];
            return;
        }
        [self persistWantedFingers];
        [self synchronizeAudioRoute];
        [self recordEvent:@"finger_bound" detail:identifier];
        accepted = YES;
    };
    if (NSThread.isMainThread)
        bind();
    else
        dispatch_sync(dispatch_get_main_queue(), bind);
    return accepted;
}

- (BOOL)unbindFinger:(NSString *)identifier error:(NSString **)error {
    __block BOOL accepted = NO;
    void (^unbind)(void) = ^{
        int result = broadcast_fingers_unbind(
            &self->_fingers, identifier.UTF8String
        );
        if (result != BROADCAST_FINGER_OK) {
            if (error) *error = [self messageForFingerResult:result];
            return;
        }
        [self persistWantedFingers];
        [self synchronizeAudioRoute];
        [self recordEvent:@"finger_unbound" detail:identifier];
        accepted = YES;
    };
    if (NSThread.isMainThread)
        unbind();
    else
        dispatch_sync(dispatch_get_main_queue(), unbind);
    return accepted;
}

- (BOOL)playConnectionTest:(NSString **)error {
    __block BOOL accepted = NO;
    void (^play)(void) = ^{
        if (!self.requested || !self.audioRouter.isRunning) {
            if (error) *error = @"broadcast_not_running";
            return;
        }
        if (self.audioRouter.mappedChannels == 0) {
            if (error) *error = @"no_bound_audio_outputs";
            return;
        }

        const NSUInteger frames = 36000;
        NSMutableData *tone = [NSMutableData dataWithLength:frames * 4];
        int16_t *samples = tone.mutableBytes;
        for (NSUInteger frame = 0; frame < frames; frame++) {
            double phase = 2.0 * M_PI * 440.0 *
                (double)frame / 48000.0;
            int16_t sample = (int16_t)(sin(phase) * 9000.0);
            samples[frame * 2] = sample;
            samples[frame * 2 + 1] = sample;
        }
        NSError *audioError = nil;
        if (![self.audioRouter writePCM16Stereo:tone.bytes
                                         length:tone.length
                                          error:&audioError]) {
            if (error) *error = audioError.localizedDescription;
            [self recordEvent:@"test_tone_failed"
                       detail:audioError.localizedDescription];
            return;
        }
        [self recordEvent:@"test_tone_queued"
                   detail:[NSString stringWithFormat:@"frames=%lu",
            (unsigned long)frames]];
        accepted = YES;
    };
    if (NSThread.isMainThread)
        play();
    else
        dispatch_sync(dispatch_get_main_queue(), play);
    return accepted;
}

- (BOOL)runSignalPathProbe:(NSString **)error {
    __block BOOL accepted = NO;
    void (^probe)(void) = ^{
        self.lastProbeTimestampMs = [self wallClockMilliseconds];
        if (!self.requested || !self.audioRouter.isRunning) {
            self.lastProbeResult = @"broadcast_not_running";
            if (error) *error = self.lastProbeResult;
            [self recordEvent:@"signal_probe_failed"
                       detail:self.lastProbeResult];
            return;
        }
        if (self.audioRouter.mappedChannels == 0) {
            self.lastProbeResult = @"no_bound_audio_outputs";
            if (error) *error = self.lastProbeResult;
            [self recordEvent:@"signal_probe_failed"
                       detail:self.lastProbeResult];
            return;
        }

        const NSUInteger frames = 480;
        NSData *silence = [NSMutableData dataWithLength:frames * 4];
        if (!silence) {
            self.lastProbeResult = @"probe_buffer_allocation_failed";
            if (error) *error = self.lastProbeResult;
            [self recordEvent:@"signal_probe_failed"
                       detail:self.lastProbeResult];
            return;
        }
        NSError *audioError = nil;
        if (![self.audioRouter writePCM16Stereo:silence.bytes
                                         length:silence.length
                                          error:&audioError]) {
            self.lastProbeResult = audioError.localizedDescription ?: @"probe_failed";
            if (error) *error = self.lastProbeResult;
            [self recordEvent:@"signal_probe_failed"
                       detail:self.lastProbeResult];
            return;
        }
        self.lastProbeResult = @"passed";
        [self recordEvent:@"signal_probe_passed"
                   detail:[NSString stringWithFormat:@"frames=%lu",
            (unsigned long)frames]];
        accepted = YES;
    };
    if (NSThread.isMainThread)
        probe();
    else
        dispatch_sync(dispatch_get_main_queue(), probe);
    return accepted;
}

- (BOOL)setMultideviceMode:(BOOL)enabled error:(NSString **)error {
    __block BOOL configured = NO;
    void (^change)(void) = ^{
        BOOL wasRunning = self.requested;
        if (self.audioRouter.isRunning)
            [self.audioRouter stop];
        self.audioRouter.prefersMultidevice = enabled;
        [NSUserDefaults.standardUserDefaults
            setBool:enabled forKey:BroadcastPrefersMultidevice];
        if (!wasRunning) {
            [self recordEvent:@"mode_changed"
                       detail:enabled ? @"multi" : @"compatible"];
            configured = YES;
            return;
        }
        NSError *audioError = nil;
        if (![self.audioRouter startWithError:&audioError]) {
            self.lastError = audioError.localizedDescription;
            if (error) *error = self.lastError;
            [self recordEvent:@"mode_change_failed"
                       detail:self.lastError];
            return;
        }
        [self synchronizeAudioRoute];
        [self recordEvent:@"mode_changed"
                   detail:enabled ? @"multi" : @"compatible"];
        configured = YES;
    };
    if (NSThread.isMainThread)
        change();
    else
        dispatch_sync(dispatch_get_main_queue(), change);
    return configured;
}

- (BOOL)writePCM16Stereo:(const void *)bytes
                  length:(NSUInteger)length
                   error:(NSString **)error
{
    __block BOOL written = NO;
    void (^write)(void) = ^{
        if (self.audioRouter.mappedChannels == 0) {
            if (error) *error = @"no_bound_audio_outputs";
            return;
        }
        NSError *audioError = nil;
        written = [self.audioRouter writePCM16Stereo:bytes
                                              length:length
                                               error:&audioError];
        if (!written && error)
            *error = audioError.localizedDescription;
    };
    if (NSThread.isMainThread)
        write();
    else
        dispatch_sync(dispatch_get_main_queue(), write);
    return written;
}

- (void)audioRouteDidChange:(NSNotification *)notification {
    (void)notification;
    dispatch_async(dispatch_get_main_queue(), ^{
        if (!self.requested || !self.routeMonitoring)
            return;
        if (!self.audioRouter.isRunning) {
            NSError *audioError = nil;
            if (![self.audioRouter startWithError:&audioError]) {
                self.lastError = audioError.localizedDescription;
                return;
            }
        }
        [self synchronizeAudioRoute];
    });
}

- (void)audioSessionInterrupted:(NSNotification *)notification {
    NSNumber *typeValue = notification.userInfo[
        AVAudioSessionInterruptionTypeKey
    ];
    AVAudioSessionInterruptionType type = typeValue.unsignedIntegerValue;
    dispatch_async(dispatch_get_main_queue(), ^{
        if (type == AVAudioSessionInterruptionTypeBegan) {
            [self.audioRouter stop];
            if (self.requested) {
                self.lastError = @"audio_interrupted";
                [self recordEvent:@"audio_interrupted" detail:nil];
            }
            return;
        }
        if (!self.requested)
            return;
        NSError *audioError = nil;
        if (![self.audioRouter startWithError:&audioError]) {
            self.lastError = audioError.localizedDescription;
            [self recordEvent:@"interruption_recovery_failed"
                       detail:self.lastError];
            return;
        }
        [self synchronizeAudioRoute];
        [self recordEvent:@"interruption_recovered" detail:nil];
    });
}

- (void)audioMediaServicesReset:(NSNotification *)notification {
    (void)notification;
    dispatch_async(dispatch_get_main_queue(), ^{
        [self.audioRouter stop];
        if (!self.requested)
            return;
        NSError *audioError = nil;
        if (![self.audioRouter startWithError:&audioError]) {
            self.lastError = audioError.localizedDescription;
            [self recordEvent:@"media_reset_recovery_failed"
                       detail:self.lastError];
            return;
        }
        [self synchronizeAudioRoute];
        [self recordEvent:@"media_services_recovered" detail:nil];
    });
}

- (void)peripheralManagerDidUpdateState:
    (CBPeripheralManager *)peripheral
{
    [self recordEvent:@"bluetooth_state_changed"
               detail:[self bluetoothStateName]];
    if (peripheral.state == CBManagerStatePoweredOn)
        [self configureControlService];
    else
        self.controlServiceReady = NO;
}

- (void)peripheralManager:(CBPeripheralManager *)peripheral
            didAddService:(CBService *)service
                    error:(NSError *)error
{
    (void)peripheral;
    if (error) {
        self.lastError = error.localizedDescription;
        [self recordEvent:@"control_service_failed"
                   detail:self.lastError];
        return;
    }
    if ([service.UUID isEqual:[CBUUID
        UUIDWithString:BroadcastControlServiceUUID]]) {
        self.controlServiceReady = YES;
        [self recordEvent:@"control_service_ready" detail:nil];
        [self refreshAdvertisement];
    }
}

- (void)peripheralManager:(CBPeripheralManager *)peripheral
    didReceiveReadRequest:(CBATTRequest *)request
{
    if (![request.characteristic.UUID isEqual:[CBUUID
        UUIDWithString:BroadcastStatusCharacteristicUUID]]) {
        [peripheral respondToRequest:request
                         withResult:CBATTErrorAttributeNotFound];
        return;
    }
    NSUUID *centralIdentifier = request.central.identifier;
    NSData *status = self.statusReads[centralIdentifier];
    if (request.offset == 0 || !status) {
        if (self.statusReads.count >= 16)
            [self.statusReads removeAllObjects];
        status = [[self statusLine]
            dataUsingEncoding:NSUTF8StringEncoding];
        if (status)
            self.statusReads[centralIdentifier] = status;
    }
    if (!status) {
        [peripheral respondToRequest:request
                         withResult:CBATTErrorUnlikelyError];
        return;
    }
    if (request.offset > status.length) {
        [peripheral respondToRequest:request
                         withResult:CBATTErrorInvalidOffset];
        return;
    }
    request.value = [status subdataWithRange:NSMakeRange(
        request.offset, status.length - request.offset
    )];
    [peripheral respondToRequest:request withResult:CBATTErrorSuccess];
}

- (void)peripheralManagerDidStartAdvertising:
    (CBPeripheralManager *)peripheral
    error:(NSError *)error
{
    (void)peripheral;
    if (error) {
        self.lastError = error.localizedDescription;
        [self recordEvent:@"advertising_failed"
                   detail:self.lastError];
    } else {
        [self recordEvent:@"advertising_started"
                   detail:BroadcastLogicalName];
    }
}

- (NSDictionary<NSString *, id> *)statusSnapshot {
    __block NSDictionary<NSString *, id> *snapshot;
    void (^read)(void) = ^{
        NSSet<NSString *> *active = [self activeOutputUIDs];
        NSMutableArray<NSDictionary<NSString *, id> *> *devices =
            [NSMutableArray array];
        for (size_t i = 0; i < self->_fingers.count; i++) {
            const struct broadcast_finger *finger =
                &self->_fingers.devices[i];
            NSString *identifier = [NSString
                stringWithUTF8String:finger->identifier];
            [devices addObject:@{
                @"id": identifier,
                @"name": [NSString stringWithUTF8String:finger->name],
                @"active_route": @([active containsObject:identifier]),
                @"finger": @(finger->wanted),
                @"finger_state": [NSString stringWithUTF8String:
                    broadcast_finger_state_name(finger->state)],
                @"reconnect_attempts": @(finger->reconnect_attempts),
            }];
        }

        NSArray<NSDictionary<NSString *, id> *> *audioOutputs =
            [self.audioRouter outputStatus];
        NSUInteger activeFingers = 0;
        for (NSDictionary<NSString *, id> *output in audioOutputs) {
            if ([output[@"enabled"] boolValue])
                activeFingers++;
        }
        BOOL dualRoute = [self.audioRouter.sessionMode
            isEqualToString:@"dualRoute"];
        NSUInteger maximumActiveRoutes = dualRoute ? 2 : 1;
        NSUInteger rememberedFingers = broadcast_fingers_wanted_count(
            &self->_fingers
        );

        struct broadcast_health_input healthInput = {
            .broadcast_requested = self.requested,
            .bluetooth_ready = self.peripheralManager.state ==
                CBManagerStatePoweredOn,
            .control_service_ready = self.controlServiceReady,
            .advertising = self.peripheralManager.isAdvertising,
            .audio_engine_running = self.audioRouter.isRunning,
            .remembered_fingers = rememberedFingers,
            .active_fingers = activeFingers,
            .mapped_channels = self.audioRouter.mappedChannels,
        };
        struct broadcast_health_result health = {
            .state = BROADCAST_HEALTH_INVALID,
        };
        broadcast_health_evaluate(&healthInput, &health);
        NSString *healthState = [NSString stringWithUTF8String:
            broadcast_health_state_name(health.state)];
        NSString *healthAction = [NSString stringWithUTF8String:
            broadcast_health_action(health.state)];

        NSDictionary<NSString *, id> *probe = @{
            @"result": self.lastProbeResult ?: @"never",
            @"timestamp_ms": self.lastProbeTimestampMs ?: [NSNull null],
            @"scope": @"software signal path; physical sound requires listening",
        };
        NSBundle *bundle = NSBundle.mainBundle;

        snapshot = @{
            @"name": BroadcastLogicalName,
            @"captured_at_ms": [self wallClockMilliseconds],
            @"app_version": [bundle objectForInfoDictionaryKey:
                @"CFBundleShortVersionString"] ?: @"unknown",
            @"build": [bundle objectForInfoDictionaryKey:
                @"CFBundleVersion"] ?: @"unknown",
            @"running": @(self.requested && self.audioRouter.isRunning),
            @"broadcast_requested": @(self.requested),
            @"advertising": @(self.peripheralManager.isAdvertising),
            @"bluetooth_state": [self bluetoothStateName],
            @"control_service_ready": @(self.controlServiceReady),
            @"control_service_uuid": BroadcastControlServiceUUID,
            @"status_characteristic_uuid":
                BroadcastStatusCharacteristicUUID,
            @"route_monitoring": @(self.routeMonitoring),
            @"maximum_fingers": @(BROADCAST_MAX_FINGERS),
            @"maximum_active_routes": @(maximumActiveRoutes),
            @"route_limit": dualRoute
                ? @"built-in plus one eligible bidirectional secondary device"
                : @"one system-selected audio output",
            @"fingers": @(rememberedFingers),
            @"active_fingers": @(activeFingers),
            @"devices": devices,
            @"audio_outputs": audioOutputs,
            @"audio_session_mode": self.audioRouter.sessionMode,
            @"multidevice_requested":
                @(self.audioRouter.prefersMultidevice),
            @"audio_engine_running": @(self.audioRouter.isRunning),
            @"audio_format": @"s16le stereo 48000Hz",
            @"mapped_channels": @(self.audioRouter.mappedChannels),
            @"queued_frames": @(self.audioRouter.queuedFrames),
            @"source_frames": @(self.audioRouter.sourceFrames),
            @"health_state": healthState,
            @"health_action": healthAction,
            @"health_ready": @(health.ready),
            @"can_run_audio_probe": @(health.can_run_audio_probe),
            @"signal_path_probe": probe,
            @"hardware_audio_confirmation": @"required",
            @"events": [self.events copy],
            @"error": self.lastError ?: [NSNull null],
        };
    };

    if (NSThread.isMainThread)
        read();
    else
        dispatch_sync(dispatch_get_main_queue(), read);
    return snapshot ?: @{};
}

- (NSString *)statusLine {
    NSData *json = [NSJSONSerialization
        dataWithJSONObject:[self statusSnapshot] options:0 error:nil];
    NSString *line = json ? [[NSString alloc]
        initWithData:json encoding:NSUTF8StringEncoding] : @"{}";
    return [line stringByAppendingString:@"\n"];
}

- (NSString *)diagnosticReport {
    NSData *json = [NSJSONSerialization
        dataWithJSONObject:[self statusSnapshot]
                   options:NSJSONWritingPrettyPrinted
                     error:nil];
    return json ? [[NSString alloc]
        initWithData:json encoding:NSUTF8StringEncoding] : @"{}";
}

@end
